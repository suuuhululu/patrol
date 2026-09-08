"""
Publish RobotStatus and PatrolReport from isolated AMR state modules.

Implemented inputs are the internal battery observation and the process-shared
mission snapshot. Terminal mission results are drained from a persistent local
outbox into the fixed public PatrolReport contract.

``safety_state`` is a required parameter because TBD-IF-003 has not assigned
its enum numbers. The node transports the explicitly supplied uint8 but does
not attach an invented meaning to it.
"""

import math
import os
from pathlib import Path
import time

from patrol_amr import robot_status_state as rss
from patrol_amr.mission_status_store import (
    MissionStatusStore, MissionStatusStoreError)
from patrol_amr.patrol_report_adapter import (
    PatrolReportDrain, PatrolReportPublishError)
from patrol_amr.patrol_report_outbox import (
    PatrolReportOutbox, PatrolReportOutboxError)
from patrol_amr.status_mission_bridge import MissionStatusBridge


UINT64_MAX = 0xFFFFFFFFFFFFFFFF


def runtime_file(robot_id, configured_path, file_name):
    """Resolve a robot-specific state file, honoring ROS_HOME in tests."""
    if configured_path:
        return Path(configured_path).expanduser()
    ros_home = Path(
        os.environ.get('ROS_HOME', str(Path.home() / '.ros'))).expanduser()
    return ros_home / 'patrol_amr' / robot_id / file_name


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

    def next_value(self) -> int:
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
    from patrol_interfaces.msg import PatrolReport, RobotStatus
    from sensor_msgs.msg import BatteryState
    from std_msgs.msg import UInt8

    class StatusReporter(Node):
        """Publish robot status snapshots and terminal mission reports."""

        TICK_SECONDS = 0.02

        def __init__(self):
            super().__init__('status_reporter')
            self.declare_parameter('robot_id', '')
            self.declare_parameter('source_session_id', '')
            self.declare_parameter('safety_state', -1)
            self.declare_parameter('mission_status_path', '')
            self.declare_parameter('report_outbox_path', '')

            robot_id = self.get_parameter('robot_id').value
            source_session_id = self.get_parameter('source_session_id').value
            safety_state = self.get_parameter('safety_state').value
            validate_configuration(robot_id, source_session_id, safety_state)
            mission_status_path = runtime_file(
                robot_id,
                self.get_parameter('mission_status_path').value,
                'mission_status.json',
            )
            report_outbox_path = runtime_file(
                robot_id,
                self.get_parameter('report_outbox_path').value,
                'patrol_report_outbox.json',
            )

            self._source_session_id = source_session_id
            self._state = rss.RobotStatusState(robot_id)
            self._state.update_states(safety_state=safety_state)
            self._gate = PublicationGate()
            self._sequence = StatusSequence()
            self._battery_soc = float('nan')
            self._battery_timestamp = Time()
            self._mission_bridge = MissionStatusBridge(
                MissionStatusStore(mission_status_path))
            self._mission_read_error = ''
            self._report_error = ''

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
            report_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=20,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            self._report_publisher = self.create_publisher(
                PatrolReport, f'/{robot_id}/patrol_report', report_qos)
            self._report_drain = PatrolReportDrain(
                PatrolReportOutbox(report_outbox_path),
                self._report_publisher,
                PatrolReport,
                lambda: self.get_clock().now().to_msg(),
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
            self.create_timer(self.TICK_SECONDS, self._tick)
            self.create_timer(0.1, self._poll_mission_and_reports)
            self.get_logger().info(
                f'status reporter ready: robot_id={robot_id} '
                f'source_session_id={source_session_id!r}'
            )

        def _poll_mission_and_reports(self) -> None:
            try:
                if self._mission_bridge.refresh(self._state):
                    self._gate.note_change()
                self._mission_read_error = ''
            except (MissionStatusStoreError, ValueError) as exc:
                error = str(exc)
                if error != self._mission_read_error:
                    self.get_logger().error(error)
                    self._mission_read_error = error
            try:
                count = self._report_drain.publish_pending()
                if count:
                    self.get_logger().info(
                        f'published {count} pending PatrolReport message(s)')
                self._report_error = ''
            except (PatrolReportOutboxError, PatrolReportPublishError) as exc:
                error = str(exc)
                if error != self._report_error:
                    self.get_logger().error(error)
                    self._report_error = error

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
            message.status_sequence = self._sequence.next_value()
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

            # Odometry and accepted-token status need their own agreed source.
            message.linear_velocity = float('nan')
            message.angular_velocity = float('nan')
            message.motion_stopped = False
            message.accepted_token_id = ''
            message.token_valid = False
            message.battery_soc = self._battery_soc
            message.battery_timestamp = self._battery_timestamp

            mission = self._mission_bridge.snapshot
            message.active_command_id = mission.command_id
            message.active_mission_id = mission.mission_id
            message.current_waypoint_id = (
                '' if mission.waypoint_index < 0
                else f'W{mission.waypoint_index + 1}'
            )
            message.scan_state = ''
            message.reason_code = mission.reason_code
            message.reason = mission.reason

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
