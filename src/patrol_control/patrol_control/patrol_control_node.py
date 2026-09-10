"""ROS 2 Control Server node for the patrol_interfaces 2.0 contract."""

from __future__ import annotations

from functools import partial
from time import monotonic

from patrol_control.control_core import ControlCore
from patrol_control.control_core import ControlStateError

from patrol_interfaces.action import Patrol
from patrol_interfaces.msg import DriveToken, PatrolCommand

import rclpy
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile
from rclpy.qos import ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import Bool


DEFAULT_ROBOT_IDS = ('robot1', 'robot6')


def _reliable_qos(depth: int) -> QoSProfile:
    return QoSProfile(
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
        history=HistoryPolicy.KEEP_LAST,
        depth=depth,
    )


def _token_qos() -> QoSProfile:
    return QoSProfile(
        reliability=ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.VOLATILE,
        history=HistoryPolicy.KEEP_LAST,
        depth=3,
        deadline=Duration(seconds=0.2),
        lifespan=Duration(seconds=0.5),
    )


class PatrolControlNode(Node):
    """Coordinate one active Patrol Action and robot-specific Drive Tokens."""

    def __init__(self) -> None:
        super().__init__('patrol_control_node')

        robot_ids = tuple(
            self.declare_parameter('robot_ids', list(DEFAULT_ROBOT_IDS)).value
        )
        self._initial_robot_id = self.declare_parameter(
            'initial_robot_id', robot_ids[0]
        ).value
        self._auto_start = bool(
            self.declare_parameter('auto_start', False).value
        )
        token_publish_hz = float(
            self.declare_parameter('token_publish_hz', 5.0).value
        )
        self._token_lease_seconds = float(
            self.declare_parameter('token_lease_seconds', 1.0).value
        )
        if token_publish_hz <= 0.0:
            raise ValueError('token_publish_hz must be positive')
        if self._token_lease_seconds <= 0.0:
            raise ValueError('token_lease_seconds must be positive')
        if self._initial_robot_id not in robot_ids:
            raise ValueError('initial_robot_id must be in robot_ids')

        self._core = ControlCore(robot_ids)
        self._action_clients = {
            robot_id: ActionClient(
                self,
                Patrol,
                f'/{robot_id}/patrol_action',
            )
            for robot_id in robot_ids
        }
        self._command_publishers = {
            robot_id: self.create_publisher(
                PatrolCommand,
                f'/{robot_id}/patrol_command',
                _reliable_qos(10),
            )
            for robot_id in robot_ids
        }
        self._token_publishers = {
            robot_id: self.create_publisher(
                DriveToken,
                f'/{robot_id}/drive_token',
                _token_qos(),
            )
            for robot_id in robot_ids
        }
        self._permit_subscription = self.create_subscription(
            Bool,
            '/vision/cctv/patrol_allowed',
            self._on_patrol_allowed,
            _reliable_qos(1),
        )
        self._token_timer = self.create_timer(
            1.0 / token_publish_hz,
            self._on_token_timer,
        )

        self._goal_handles = {}
        self._pending_goal_robot_id = None
        self._auto_start_done = False
        self._last_server_wait_log = 0.0
        self.get_logger().info(
            'patrol control ready: robots=%s auto_start=%s initial_robot=%s'
            % (','.join(robot_ids), self._auto_start, self._initial_robot_id)
        )

    def start_patrol(self, robot_id: str) -> bool:
        """Start a Patrol Action for a future control-owned UI or API."""
        client = self._action_clients.get(robot_id)
        if client is None:
            self.get_logger().error(f'unknown robot_id: {robot_id}')
            return False
        if not client.server_is_ready():
            self._log_server_wait(robot_id)
            return False
        try:
            intent = self._core.prepare_goal(robot_id)
        except (ControlStateError, ValueError) as exc:
            self.get_logger().warning(f'patrol start rejected: {exc}')
            return False

        goal = Patrol.Goal()
        goal.command_id = intent.command_id
        goal.robot_id = intent.robot_id
        self._pending_goal_robot_id = robot_id
        future = client.send_goal_async(
            goal,
            feedback_callback=partial(
                self._on_patrol_feedback,
                robot_id=robot_id,
            ),
        )
        future.add_done_callback(
            partial(self._on_goal_response, robot_id=robot_id)
        )
        self.get_logger().info(
            f'Patrol Goal sent: robot={robot_id} command={intent.command_id}'
        )
        return True

    def cancel_active_patrol(self) -> bool:
        """Request Action cancellation and revoke Token immediately."""
        robot_id = self._core.active_robot_id
        if robot_id is None:
            return False
        goal_handle = self._goal_handles.get(robot_id)
        if goal_handle is None:
            return False
        self._core.revoke_drive(robot_id)
        self._publish_token_frames()
        goal_handle.cancel_goal_async()
        self.get_logger().warning(
            f'Patrol cancel requested; DriveToken revoked: robot={robot_id}'
        )
        return True

    def clear_fire_hold(self) -> None:
        """Clear fire hold through a future authenticated operator API."""
        self._core.clear_fire_hold()
        self.get_logger().warning('fire hold cleared by explicit operator call')

    def _on_patrol_allowed(self, message: Bool) -> None:
        commands = self._core.observe_permit(bool(message.data))
        self.get_logger().info(f'patrol_allowed={bool(message.data)}')
        for intent in commands:
            command = PatrolCommand()
            command.header.stamp = self.get_clock().now().to_msg()
            command.command_id = intent.command_id
            command.robot_id = intent.robot_id
            command.command = int(intent.command)
            self._command_publishers[intent.robot_id].publish(command)
            self.get_logger().info(
                'PatrolCommand published: robot=%s command=%s id=%s'
                % (intent.robot_id, intent.command.name, intent.command_id)
            )
        self._try_auto_start()

    def _on_token_timer(self) -> None:
        self._publish_token_frames()
        self._try_auto_start()

    def _publish_token_frames(self) -> None:
        """Publish the current grant or explicit revocation for each robot."""
        now = self.get_clock().now()
        total_ns = int(self._token_lease_seconds * 1_000_000_000)
        for frame in self._core.token_frames():
            message = DriveToken()
            message.header.stamp = now.to_msg()
            message.token = frame.token
            message.holder_robot_id = frame.robot_id
            message.lease_duration.sec = total_ns // 1_000_000_000
            message.lease_duration.nanosec = total_ns % 1_000_000_000
            message.sequence = frame.sequence
            self._token_publishers[frame.robot_id].publish(message)

    def _try_auto_start(self) -> None:
        if not self._auto_start or self._auto_start_done:
            return
        if self._core.patrol_allowed is not True:
            return
        if self.start_patrol(self._initial_robot_id):
            self._auto_start_done = True

    def _on_goal_response(self, future, *, robot_id: str) -> None:
        self._pending_goal_robot_id = None
        try:
            goal_handle = future.result()
        except Exception as exc:  # rclpy Future transports middleware errors.
            self.get_logger().error(
                f'Patrol Goal request failed: robot={robot_id} error={exc}'
            )
            self._finish_core_goal(robot_id)
            return
        if not goal_handle.accepted:
            self.get_logger().warning(f'Patrol Goal rejected: robot={robot_id}')
            self._finish_core_goal(robot_id)
            return

        self._goal_handles[robot_id] = goal_handle
        self._core.mark_goal_accepted(robot_id)
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            partial(self._on_patrol_result, robot_id=robot_id)
        )
        self.get_logger().info(
            f'Patrol Goal accepted; waiting for WAITING_FOR_TOKEN: {robot_id}'
        )

    def _on_patrol_feedback(self, feedback_message, *, robot_id: str) -> None:
        feedback = feedback_message.feedback
        effect = self._core.observe_feedback(
            robot_id,
            task_state=feedback.task_state,
            event_type=feedback.event_type,
            event_id=feedback.event_id,
        )
        if not effect.accepted:
            self.get_logger().warning(
                f'ignored Patrol Feedback: robot={robot_id} state={feedback.task_state}'
            )
            return
        if effect.token_granted:
            self.get_logger().info(
                f'DriveToken granted after WAITING_FOR_TOKEN: robot={robot_id}'
            )
        if effect.fire_hold_activated:
            self.get_logger().error(
                f'FIRE_HOLD activated: robot={robot_id} event={feedback.event_id}'
            )
        if feedback.task_state == Patrol.Feedback.WAYPOINT_REACHED:
            self.get_logger().info(
                f'waypoint reached: robot={robot_id} waypoint={feedback.current_waypoint_id}'
            )

    def _on_patrol_result(self, future, *, robot_id: str) -> None:
        try:
            wrapped = future.result()
            result = wrapped.result
            self.get_logger().info(
                'Patrol Result: robot=%s outcome=%d reason_code=%d reason=%s'
                % (robot_id, result.outcome, result.reason_code, result.reason)
            )
        except Exception as exc:  # rclpy Future transports middleware errors.
            self.get_logger().error(
                f'Patrol Result failed: robot={robot_id} error={exc}'
            )
        finally:
            self._goal_handles.pop(robot_id, None)
            self._finish_core_goal(robot_id)

    def _finish_core_goal(self, robot_id: str) -> None:
        if self._core.active_robot_id == robot_id:
            self._core.finish_goal(robot_id)

    def _log_server_wait(self, robot_id: str) -> None:
        now = monotonic()
        if now - self._last_server_wait_log >= 5.0:
            self.get_logger().warning(
                f'Patrol Action server not ready: /{robot_id}/patrol_action'
            )
            self._last_server_wait_log = now


def main(args=None) -> None:
    """Run the patrol Control Server node."""
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = PatrolControlNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.cancel_active_patrol()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
