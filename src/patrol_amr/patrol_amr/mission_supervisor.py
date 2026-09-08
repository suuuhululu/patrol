#!/usr/bin/env python3
"""ROS composition node for AMR mission and navigation integration."""

from __future__ import annotations

from patrol_amr.command_store import CommandStore
from patrol_amr.drive_token_callback import DriveTokenCallback
from patrol_amr.mission_arbiter import MissionArbiter
from patrol_amr.mission_command_callback import MissionCommandCallback
from patrol_amr.mission_command_parser import MissionCommandParser
from patrol_amr.mission_config import declare_parameters, load_config
from patrol_amr.mission_drive_token import MissionDriveTokenGuard
from patrol_amr.mission_reporter import MissionReporter
from patrol_amr.mission_state import MissionStateTracker
from patrol_amr.mission_status_store import MissionStatusStore
from patrol_amr.mission_worker import MissionWorker
from patrol_amr.motion_gate import MotionGate
from patrol_amr.motion_permission import MotionPermission
from patrol_amr.patrol_report_outbox import PatrolReportOutbox
from patrol_amr.robot_readiness_callbacks import RobotReadinessCallbacks
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy)
from std_msgs.msg import Bool

try:
    from patrol_interfaces.msg import DriveToken, MissionCommand
except ImportError:  # shared package lands independently of this feature branch
    DriveToken = None
    MissionCommand = None


MISSION_QOS = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
)

DRIVE_TOKEN_QOS = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=3,
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
)


class MissionSupervisor(Node):
    """Wire ROS input to small callback, arbitration, and worker components."""

    def __init__(self) -> None:
        if MissionCommand is None or DriveToken is None:
            raise RuntimeError(
                'patrol_interfaces MissionCommand and DriveToken are required; '
                'the legacy DriveToken/String mission-start path is unsupported')
        super().__init__('mission_supervisor')
        declare_parameters(self)
        self._config = load_config(self)
        self._store = CommandStore(self._config.command_store_path)
        self._state = MissionStateTracker()
        self._mission_status_store = MissionStatusStore(
            self._config.mission_status_path)
        self._mission_status_store.write(self._state.snapshot())
        self._report_outbox = PatrolReportOutbox(
            self._config.report_outbox_path)
        self._reporter = MissionReporter(
            lambda completion: self._report_outbox.enqueue(
                completion, self._config.source_session_id))
        self._readiness = RobotReadinessCallbacks(self)
        self._motion_gate = MotionGate(
            self._config.robot_id,
            self._config.safety_path_ready,
            self._config.hardware_test_mode,
            self._config.motion_enable_token,
            self._readiness.snapshot,
        )
        self._drive_token_guard = MissionDriveTokenGuard(self._config.robot_id)
        self._arbiter = MissionArbiter(self._motion_ready)
        self._arbiter.set_external_stop(True)
        self._motion_permission = MotionPermission(
            self._synchronize_motion_authority)
        parser = MissionCommandParser(self._config.robot_id)
        self._mission_command_callback = MissionCommandCallback(
            parser,
            self._arbiter,
            self.get_logger(),
            self._motion_summary,
        )
        self._subscription = self.create_subscription(
            MissionCommand,
            'mission_command',
            self._mission_command_callback,
            MISSION_QOS,
        )
        self._drive_token_callback = DriveTokenCallback(
            self._drive_token_guard,
            self._synchronize_motion_authority,
            self.get_logger(),
        )
        self._drive_token_subscription = self.create_subscription(
            DriveToken,
            '/control/drive_token',
            self._drive_token_callback,
            DRIVE_TOKEN_QOS,
        )
        self._motion_permission_subscription = self.create_subscription(
            Bool,
            'motion_allowed',
            self._motion_permission,
            QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            ),
        )
        self._motion_authority_was_valid = False
        self._drive_token_timer = self.create_timer(
            0.05, self._synchronize_motion_authority)
        self._worker = MissionWorker(
            self._config,
            self.get_namespace(),
            self._store,
            self._arbiter,
            self._state,
            self.get_logger(),
            rclpy.ok,
            self._motion_ready,
            reporter=self._reporter,
            state_sink=self._mission_status_store.write,
            now_ns=lambda: self.get_clock().now().nanoseconds,
        )
        self._worker.start()
        if not self._config.initialize_navigation:
            self.get_logger().error(
                f'motion disabled: {self._motion_gate.summary()}')
        elif self._config.hardware_test_mode:
            self.get_logger().warn(
                'hardware_test_mode=true: using the TurtleBot4 Nav2 '
                'velocity_smoother and collision_monitor drive path')
        self.get_logger().info(
            'AMR-07 result persistence ready: '
            f'outbox={self._config.report_outbox_path}')

    def _motion_ready(self) -> bool:
        """Require both robot readiness and a live DriveToken lease."""
        return (
            self._motion_gate.ready()
            and self._drive_token_guard.valid()
            and self._motion_permission.allowed()
        )

    def _motion_summary(self) -> str:
        """Combine static/sensor and DriveToken blockers for command logs."""
        blockers = list(self._motion_gate.blocking_reasons())
        token = self._drive_token_guard.snapshot()
        if not token.valid:
            blockers.append(token.blocking_reason)
        if not self._motion_permission.allowed():
            blockers.append('LOCAL_SAFETY_BLOCKED')
        return 'READY' if not blockers else ','.join(blockers)

    def _synchronize_motion_authority(self) -> None:
        """Cancel work when either token or local-safety permission is lost."""
        token = self._drive_token_guard.snapshot()
        valid = token.valid and self._motion_permission.allowed()
        self._arbiter.set_external_stop(not valid)
        if valid != self._motion_authority_was_valid:
            if valid:
                self.get_logger().info(
                    'motion authority ready; waiting for MissionCommand')
            else:
                reason = (
                    token.blocking_reason
                    if not token.valid
                    else 'LOCAL_SAFETY_BLOCKED'
                )
                self.get_logger().warn(
                    f'motion authority unavailable ({reason}); motion canceled')
            self._motion_authority_was_valid = valid

    def mission_state_snapshot(self):
        """Provide internal state without inventing a ROS topic contract."""
        return self._state.snapshot()

    def close(self) -> None:
        self._worker.close()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = None
    executor = None
    try:
        node = MissionSupervisor()
        # TurtleBot4Navigator spins its own node on rclpy's global executor
        # from the mission worker thread.  Keep this composition node on a
        # dedicated executor so both nodes never try to spin the same
        # executor concurrently.
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        if executor is not None:
            executor.shutdown(timeout_sec=2.0)
        if node is not None:
            node.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
