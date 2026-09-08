"""ROS 2 RobotStatus publisher using the stage-7 state model.

Implemented inputs are limited to contracts that exist in this workspace:
the internal ``battery_status`` enum and raw ``battery_state`` observation.
Mission, docking, localization validity, odometry, and accepted-token state
do not yet have agreed AMR-internal source topics in the repository, so this
node reports their safe unknown/empty values instead of inventing topic names.

``safety_state`` is a required parameter because TBD-IF-003 has not assigned
its enum numbers. The node transports the explicitly supplied uint8 but does
not attach an invented meaning to it.
"""

import math
import time

from patrol_amr import robot_status_state as rss


UINT64_MAX = 0xFFFFFFFFFFFFFFFF


def stamp_to_seconds(stamp) -> float:
    """builtin_interfaces/Time to the float seconds the state model uses."""
    return stamp.sec + stamp.nanosec / 1e9


def validate_configuration(robot_id, source_session_id, safety_state):
    """Validate values that must be explicit before a status can be emitted."""
    if robot_id not in rss.ROBOT_IDS:
        raise ValueError(f'robot_id must be one of {rss.ROBOT_IDS}')
    if not isinstance(source_session_id, str) or not source_session_id:
        raise ValueError('source_session_id must be a non-empty str')
    if isinstance(safety_state, bool) or not isinstance(safety_state, int):
        raise ValueError('safety_state must be an int')
    if not 0 <= safety_state <= rss.UINT8_MAX:
        raise ValueError('safety_state must fit in uint8')


class PublicationGate:
    """Q-02: periodic 2 Hz and changed-status publication at max 10 Hz."""

    PERIOD_SECONDS = 0.5
    MIN_CHANGE_INTERVAL_SECONDS = 0.1

    def __init__(self):
        self._last_published_at = None
        self._change_pending = True

    def note_change(self):
        self._change_pending = True

    def due(self, now: float) -> bool:
        self._validate_time(now)
        if self._last_published_at is None:
            return True
        elapsed = now - self._last_published_at
        if elapsed < 0.0:
            raise ValueError('now must not precede the last publication')
        if self._change_pending:
            return elapsed >= self.MIN_CHANGE_INTERVAL_SECONDS
        return elapsed >= self.PERIOD_SECONDS

    def mark_published(self, now: float):
        self._validate_time(now)
        if self._last_published_at is not None and now < self._last_published_at:
            raise ValueError('now must not precede the last publication')
        self._last_published_at = float(now)
        self._change_pending = False

    @staticmethod
    def _validate_time(now):
        if isinstance(now, bool) or not isinstance(now, (int, float)):
            raise ValueError('now must be a real number')
        if not math.isfinite(now):
            raise ValueError('now must be finite')


class StatusSequence:
    """Generate public status_sequence values starting at one per process."""

    def __init__(self):
        self._value = 0

    def next(self) -> int:
        if self._value >= UINT64_MAX:
            raise OverflowError('status_sequence exhausted uint64')
        self._value += 1
        return self._value


def create_node_class():
    """Import ROS lazily so timing/configuration tests need no ROS setup."""
    import rclpy
    from rclpy.duration import Duration
    from rclpy.node import Node
    from rclpy.qos import (
        DurabilityPolicy,
        HistoryPolicy,
        QoSProfile,
        ReliabilityPolicy,
        qos_profile_sensor_data,
    )
    from builtin_interfaces.msg import Time
    from nav_msgs.msg import Odometry
    from patrol_interfaces.msg import RobotStatus
    from sensor_msgs.msg import BatteryState
    from std_msgs.msg import UInt8

    class StatusReporter(Node):
        """Publish /{robot}/robot_status from currently implemented inputs."""

        TICK_SECONDS = 0.02

        def __init__(self):
            super().__init__('status_reporter')
            self.declare_parameter('robot_id', '')
            self.declare_parameter('source_session_id', '')
            self.declare_parameter('safety_state', -1)

            robot_id = self.get_parameter('robot_id').value
            source_session_id = self.get_parameter('source_session_id').value
            safety_state = self.get_parameter('safety_state').value
            validate_configuration(robot_id, source_session_id, safety_state)

            self._source_session_id = source_session_id
            self._state = rss.RobotStatusState(robot_id)
            self._state.update_states(safety_state=safety_state)
            self._gate = PublicationGate()
            self._sequence = StatusSequence()
            self._battery_soc = float('nan')
            self._battery_timestamp = Time()

            status_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=5,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
                deadline=Duration(seconds=0.5),
            )
            internal_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            self._publisher = self.create_publisher(
                RobotStatus, f'/{robot_id}/robot_status', status_qos
            )
            self.create_subscription(
                UInt8, 'battery_status', self._on_battery_status, internal_qos
            )
            self.create_subscription(
                BatteryState,
                'battery_state',
                self._on_battery_observation,
                qos_profile_sensor_data,
            )
            # 14단계: odometry 는 로봇 드라이버가 내는 센서 스트림이므로
            # battery_state 와 같은 sensor data QoS 를 쓴다.
            self.create_subscription(
                Odometry, 'odom', self._on_odometry, qos_profile_sensor_data
            )
            self.create_timer(self.TICK_SECONDS, self._tick)
            self.get_logger().info(
                f'status reporter ready: robot_id={robot_id} '
                f'source_session_id={source_session_id!r}'
            )

        def _on_odometry(self, message) -> None:
            """Feed measured velocity into the motion_stopped judgment.

            This deliberately does NOT call note_change(). Q-02 lists the
            enum axes and pose_valid as the fields whose change forces an
            immediate publication; velocity is not among them, and it moves
            on every sample, so treating it as a change trigger would push
            the reporter past the 10 Hz change limit for no benefit.
            """
            try:
                self._state.observe_odometry(
                    message.twist.twist.linear.x,
                    message.twist.twist.angular.z,
                    stamp_to_seconds(message.header.stamp),
                )
            except ValueError as error:
                self.get_logger().warning(f'ignored odometry sample: {error}')

        def _on_battery_status(self, message) -> None:
            try:
                changed = self._state.update_states(battery_state=message.data)
            except ValueError:
                self.get_logger().warning(
                    f'ignored invalid battery_status value: {message.data}'
                )
                return
            if changed:
                self._gate.note_change()

        def _on_battery_observation(self, message) -> None:
            percentage = message.percentage
            if (
                message.present
                and math.isfinite(percentage)
                and 0.0 <= percentage <= 1.0
            ):
                self._battery_soc = float(percentage)
                self._battery_timestamp = message.header.stamp
            else:
                self._battery_soc = float('nan')
                self._battery_timestamp = Time()

        def _tick(self) -> None:
            monotonic_now = time.monotonic()
            if not self._gate.due(monotonic_now):
                return
            self._publish(monotonic_now)

        def _publish(self, monotonic_now: float) -> None:
            ros_now = self.get_clock().now()
            snapshot = self._state.snapshot(ros_now.nanoseconds / 1e9)
            message = RobotStatus()
            message.header.stamp = ros_now.to_msg()
            message.robot_id = snapshot.robot_id
            message.source_session_id = self._source_session_id
            message.status_sequence = self._sequence.next()
            message.operational_state = int(snapshot.operational_state)
            message.mission_state = int(snapshot.mission_state)
            message.docking_state = int(snapshot.docking_state)
            message.battery_state = int(snapshot.battery_state)
            message.safety_state = snapshot.safety_state

            if snapshot.pose is not None:
                message.pose = snapshot.pose.value
            message.pose_valid = snapshot.pose_valid
            if snapshot.last_valid_pose is not None:
                message.last_valid_pose = snapshot.last_valid_pose.value

            message.linear_velocity = snapshot.linear_velocity
            message.angular_velocity = snapshot.angular_velocity
            message.motion_stopped = snapshot.motion_stopped

            # No agreed token/mission source is connected yet.
            message.accepted_token_id = ''
            message.token_valid = False
            message.battery_soc = self._battery_soc
            message.battery_timestamp = self._battery_timestamp

            self._publisher.publish(message)
            self._gate.mark_published(monotonic_now)

    return StatusReporter, rclpy


def main(args=None):
    StatusReporter, rclpy = create_node_class()
    rclpy.init(args=args)
    node = StatusReporter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

