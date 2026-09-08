"""ROS 2 adapter for the integrated command-control domain module."""

from __future__ import annotations

from functools import partial

from patrol_control.command_control import CommandControl
from patrol_control.command_control import CommandIdFactory
from patrol_control.command_control import CommandValidationError
from patrol_control.command_control import RetryActionType
from patrol_control.command_control import TrackingDisposition

from patrol_interfaces.msg import CommandCheck, MissionCommand, PatrolReport

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile
from rclpy.qos import ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions


ROBOT_IDS = ('robot1', 'robot6')


def _reliable_qos(depth: int) -> QoSProfile:
    return QoSProfile(
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
        history=HistoryPolicy.KEEP_LAST,
        depth=depth,
    )


class CommandControlNode(Node):
    """Publish MissionCommand and correlate CommandCheck and PatrolReport."""

    def __init__(self) -> None:
        """Create per-robot command publishers and result subscriptions."""
        super().__init__('command_control')
        self._control = CommandControl(CommandIdFactory.new_session())
        self._command_publishers = {
            robot_id: self.create_publisher(
                MissionCommand,
                f'/{robot_id}/mission_command',
                _reliable_qos(10),
            )
            for robot_id in ROBOT_IDS
        }
        self._command_subscriptions = []
        for robot_id in ROBOT_IDS:
            self._command_subscriptions.append(
                self.create_subscription(
                    CommandCheck,
                    f'/{robot_id}/command_check',
                    partial(
                        self._on_command_check,
                        expected_robot_id=robot_id,
                    ),
                    _reliable_qos(10),
                )
            )
            self._command_subscriptions.append(
                self.create_subscription(
                    PatrolReport,
                    f'/{robot_id}/patrol_report',
                    partial(
                        self._on_patrol_report,
                        expected_robot_id=robot_id,
                    ),
                    _reliable_qos(20),
                )
            )
        self._retry_timer = self.create_timer(0.1, self._on_retry_timer)
        self.get_logger().info(
            'command control ready: session=%s'
            % self._control.id_factory.control_session_id
        )

    def submit_command(
        self,
        *,
        robot_id: str,
        command: int,
        mission_id: str = '',
        target_id: str = '',
        issued_by: str = 'control',
    ) -> str:
        """Validate and publish a command from a future control-owned API."""
        now_ns = self.get_clock().now().nanoseconds
        try:
            envelope = self._control.create_command(
                robot_id=robot_id,
                command=command,
                now_ns=now_ns,
                mission_id=mission_id,
                target_id=target_id,
                issued_by=issued_by,
            )
        except (CommandValidationError, ValueError) as exc:
            self.get_logger().error(f'command rejected before publish: {exc}')
            raise
        self._publish(envelope)
        return envelope.command_id

    def record_control_shutdown(self) -> None:
        """Record graceful shutdown pending the operation-event topic."""
        self.get_logger().warning(
            'CONTROL_SHUTDOWN event_type=control-shutdown; '
            'token revoke is owned by the future safety-control node'
        )

    def _publish(self, envelope) -> None:
        message = MissionCommand()
        message.header.stamp.sec = envelope.issued_at_ns // 1_000_000_000
        message.header.stamp.nanosec = envelope.issued_at_ns % 1_000_000_000
        message.command_id = envelope.command_id
        message.mission_id = envelope.mission_id
        message.robot_id = envelope.robot_id
        message.command = int(envelope.command)
        message.target_id = envelope.target_id
        message.issued_by = envelope.issued_by
        self._command_publishers[envelope.robot_id].publish(message)

    def _on_command_check(
        self, message: CommandCheck, *, expected_robot_id: str
    ) -> None:
        if message.robot_id != expected_robot_id:
            self.get_logger().warning(
                'discard CommandCheck: topic robot and payload robot differ'
            )
            return
        result = self._control.handle_check(
            command_id=message.command_id,
            mission_id=message.mission_id,
            robot_id=message.robot_id,
            check_state=message.check_state,
            reason_code=message.reason_code,
            reason=message.reason,
        )
        if result is None:
            self.get_logger().warning(
                'discard CommandCheck: unknown command_id'
            )
            return
        self._log_tracking_result('CommandCheck', message.command_id, result)

    def _on_patrol_report(
        self, message: PatrolReport, *, expected_robot_id: str
    ) -> None:
        if message.robot_id != expected_robot_id:
            self.get_logger().warning(
                'discard PatrolReport: topic robot and payload robot differ'
            )
            return
        result = self._control.handle_report(
            report_id=message.report_id,
            command_id=message.command_id,
            mission_id=message.mission_id,
            robot_id=message.robot_id,
            result=message.result,
            reason_code=message.reason_code,
            reason=message.reason,
        )
        if result is None:
            self.get_logger().warning(
                'discard PatrolReport: unknown command_id'
            )
            return
        self._log_tracking_result('PatrolReport', message.command_id, result)

    def _on_retry_timer(self) -> None:
        for action in self._control.poll_retries(
            self.get_clock().now().nanoseconds
        ):
            if action.action is RetryActionType.RETRANSMIT:
                self._publish(action.envelope)
                self.get_logger().warning(
                    'MissionCommand retry %d/2: %s'
                    % (action.retransmission, action.envelope.command_id)
                )
                continue
            if action.action is RetryActionType.POLICY_PENDING:
                self.get_logger().error(
                    'ACCEPTED_MISSING retry policy is pending AMR '
                    'agreement: %s'
                    % action.envelope.command_id
                )
                continue
            self.get_logger().error(
                'COMMAND_CHECK_TIMEOUT: %s' % action.envelope.command_id
            )

    def _log_tracking_result(
        self, source: str, command_id: str, result
    ) -> None:
        if result.disposition is TrackingDisposition.DISCARDED:
            self.get_logger().warning(
                f'discard {source} for {command_id}: {result.detail}'
            )
            return
        for warning in result.warnings:
            self.get_logger().warning(f'{warning}: {command_id}')
        self.get_logger().info(
            f'{source} {result.disposition.value}: '
            f'{command_id} -> {result.lifecycle.value}'
        )


def main(args=None) -> None:
    """Run the command-control node."""
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = CommandControlNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.record_control_shutdown()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
