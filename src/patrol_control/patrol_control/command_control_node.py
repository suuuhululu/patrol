"""Single ROS 2 control node for staged patrol-system integration."""

from __future__ import annotations

from functools import partial
from time import monotonic_ns

from patrol_control.command_control import CommandControl
from patrol_control.command_control import CommandIdFactory
from patrol_control.command_control import CommandValidationError
from patrol_control.command_control import RetryActionType
from patrol_control.command_control import TrackingDisposition
from patrol_control.control_state import DetectionDisposition
from patrol_control.control_state import DetectionEventTracker
from patrol_control.control_state import IntegrationProfile
from patrol_control.control_state import parse_profile
from patrol_control.control_state import PermitMonitor
from patrol_control.control_state import PROFILE_CAPABILITIES

from patrol_interfaces.msg import CommandCheck, DetectionEvent
from patrol_interfaces.msg import MissionCommand, PatrolReport

from rcl_interfaces.msg import ParameterDescriptor
import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile
from rclpy.qos import ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import Bool


ROBOT_IDS = ('robot1', 'robot6')


def _reliable_qos(depth: int) -> QoSProfile:
    return QoSProfile(
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
        history=HistoryPolicy.KEEP_LAST,
        depth=depth,
    )


def _permit_qos() -> QoSProfile:
    return QoSProfile(
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        deadline=Duration(nanoseconds=500_000_000),
    )


class PatrolControlNode(Node):
    """Own control state while enabling only the selected integration scope."""

    def __init__(self) -> None:
        """Create vision inputs and optional AMR command interfaces."""
        super().__init__('patrol_control_node')
        profile_value = self.declare_parameter(
            'integration_profile',
            IntegrationProfile.VISION_INTEGRATION.value,
            ParameterDescriptor(
                description='Startup-only patrol integration profile',
                read_only=True,
            ),
        ).value
        self._profile = parse_profile(profile_value)
        self._capabilities = PROFILE_CAPABILITIES[self._profile]
        if not self._capabilities.production_ready:
            raise RuntimeError(
                'full_system is reserved until AMR safety integration is '
                'implemented and verified'
            )

        now_ns = monotonic_ns()
        self._permit_monitor = PermitMonitor(now_ns)
        self._detection_tracker = DetectionEventTracker()
        self._permit_subscription = self.create_subscription(
            Bool,
            '/vision/cctv/patrol_allowed',
            self._on_patrol_allowed,
            _permit_qos(),
        )
        self._detection_subscriptions = [
            self.create_subscription(
                DetectionEvent,
                f'/{robot_id}/detection/event',
                partial(
                    self._on_detection_event,
                    expected_robot_id=robot_id,
                ),
                _reliable_qos(10),
            )
            for robot_id in ROBOT_IDS
        ]
        self._vision_timer = self.create_timer(
            0.1,
            self._on_vision_timer,
        )

        self._control = CommandControl(CommandIdFactory.new_session())
        self._command_publishers = {}
        self._command_subscriptions = []
        self._retry_timer = None
        if self._capabilities.amr_input or self._capabilities.amr_output:
            self._create_amr_interfaces()

        self.get_logger().info(
            'patrol control ready: profile=%s session=%s'
            % (
                self._profile.value,
                self._control.id_factory.control_session_id,
            )
        )

    def _create_amr_interfaces(self) -> None:
        """Create command interfaces only for a completed AMR profile."""
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
        if not self._capabilities.amr_output:
            raise RuntimeError(
                'AMR command output is disabled by integration_profile='
                f'{self._profile.value}'
            )
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
        if not self._capabilities.amr_output:
            raise RuntimeError('AMR command output is disabled')
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

    def _on_patrol_allowed(self, message: Bool) -> None:
        transition = self._permit_monitor.observe(
            message.data,
            monotonic_ns(),
        )
        if transition.recovered:
            self.get_logger().info(
                'CCTV_PERMIT_RECOVERED patrol_allowed=%s'
                % transition.patrol_allowed
            )
        elif transition.became_healthy:
            self.get_logger().info(
                'CCTV_PERMIT_HEALTHY patrol_allowed=%s'
                % transition.patrol_allowed
            )
        elif transition.value_changed:
            self.get_logger().info(
                'patrol_allowed=%s' % transition.patrol_allowed
            )

    def _on_vision_timer(self) -> None:
        transition = self._permit_monitor.check_timeout(monotonic_ns())
        if transition.became_timed_out:
            self.get_logger().warning(
                'CCTV_PERMIT_TIMEOUT: preserving patrol_allowed=%s'
                % transition.patrol_allowed
            )

    def _on_detection_event(
        self,
        message: DetectionEvent,
        *,
        expected_robot_id: str,
    ) -> None:
        result = self._detection_tracker.observe(
            expected_robot_id=expected_robot_id,
            robot_id=message.robot_id,
            message_id=message.message_id,
            event_id=message.event_id,
            event_type=message.event_type,
        )
        if result.disposition is DetectionDisposition.REJECTED:
            self.get_logger().warning(
                'discard DetectionEvent %s: %s'
                % (message.event_id, result.detail)
            )
            return
        if result.disposition is DetectionDisposition.DUPLICATE:
            self.get_logger().info(
                'duplicate DetectionEvent ignored: %s' % message.event_id
            )
            return
        self.get_logger().info(
            'DetectionEvent accepted: robot=%s event=%s type=%d; '
            'AMR action disabled in profile=%s'
            % (
                message.robot_id,
                message.event_id,
                message.event_type,
                self._profile.value,
            )
        )

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
    """Run the single patrol control node."""
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = PatrolControlNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.record_control_shutdown()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


# Import compatibility for code that used the stage-1 class name.  There is
# still only one ROS node and one console entry point.
CommandControlNode = PatrolControlNode


if __name__ == '__main__':
    main()
