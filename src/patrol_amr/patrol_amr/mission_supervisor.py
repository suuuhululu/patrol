#!/usr/bin/env python3
"""ROS composition node for AMR mission and navigation integration."""

from __future__ import annotations
from patrol_amr import command_lifecycle
from patrol_amr.mission_arbiter import MissionArbiter
from patrol_amr.mission_command_callback import MissionCommandCallback
from patrol_amr.mission_command_parser import MissionCommandParser
from patrol_amr.mission_command_store import CommandStore
from patrol_amr.mission_config import declare_parameters, load_config
from patrol_amr.mission_reporter import MissionReporter
from patrol_amr.mission_state import MissionStateTracker
from patrol_amr.mission_status_store import MissionStatusStore
from patrol_amr.mission_worker import MissionWorker
from patrol_amr.motion_gate import MotionGate
from patrol_amr.motion_permission import MotionPermission
from patrol_amr.patrol_report_outbox import (
    PatrolReportOutbox, to_patrol_report_record)
from patrol_amr.robot_readiness_callbacks import RobotReadinessCallbacks
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy)
from std_msgs.msg import Bool, String

try:
    from patrol_interfaces.msg import MissionCommand
except ImportError:  # shared package lands independently of this feature branch
    MissionCommand = None


MISSION_QOS = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
)

MISSION_DISPATCH_TOPIC = 'mission_dispatch'


class MissionSupervisor(Node):
    """Wire ROS input to small callback, arbitration, and worker components."""

    def __init__(self) -> None:
        if MissionCommand is None:
            raise RuntimeError(
                'patrol_interfaces MissionCommand is required for the internal '
                'mission_dispatch path')
        super().__init__('mission_supervisor')
        declare_parameters(self)
        self._config = load_config(self)
        self._store = CommandStore(self._config.command_store_path)
        self._mission_status_store = MissionStatusStore(
            self._config.mission_status_path)
        previous_status = self._mission_status_store.read()
        next_revision = (
            0 if previous_status is None else previous_status.revision + 1)
        self._state = MissionStateTracker(starting_revision=next_revision)
        self._mission_status_store.write(self._state.snapshot())
        self._report_outbox = PatrolReportOutbox(
            self._config.report_outbox_path)
        lifecycle_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=20,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._lifecycle_publisher = self.create_publisher(
            String, 'mission_lifecycle', lifecycle_qos)
        self._reporter = MissionReporter(
            self._persist_completion)
        self._readiness = RobotReadinessCallbacks(self)
        self._motion_gate = MotionGate(
            self._config.robot_id,
            self._config.safety_path_ready,
            self._config.hardware_test_mode,
            self._config.motion_enable_token,
            self._readiness.snapshot,
        )
        self._arbiter = MissionArbiter(
            self._motion_ready,
            self._state.snapshot,
        )
        self._arbiter.set_external_stop(True)
        self._motion_permission = MotionPermission(
            self._synchronize_motion_authority)
        parser = MissionCommandParser(
            self._config.robot_id, self._config.patrol_plan_id)
        self._mission_command_callback = MissionCommandCallback(
            parser,
            self._arbiter,
            self.get_logger(),
            self._motion_summary,
        )
        self._mission_dispatch_subscription = self.create_subscription(
            MissionCommand,
                        MISSION_DISPATCH_TOPIC,
            self._mission_command_callback,
            MISSION_QOS,
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
            execution_started_sink=self._notify_execution_started,
            now_ns=lambda: self.get_clock().now().nanoseconds,
        )
        self._worker.start()
        self._replay_pending_completion_events()
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

    def _publish_lifecycle(self, event) -> None:
        self._lifecycle_publisher.publish(
            String(data=command_lifecycle.to_json(event)))

    def _notify_execution_started(self, request) -> None:
        """Tell the sole CommandCheck owner when worker execution begins."""
        self._publish_lifecycle(command_lifecycle.executing(request))

    def _persist_completion(self, completion):
        """Persist a result first, then notify the gateway with exact payload."""
        pending = self._report_outbox.enqueue(
            completion, self._config.source_session_id)
        report = to_patrol_report_record(pending)
        self._publish_lifecycle(command_lifecycle.completed(report))
        return pending

    def _replay_pending_completion_events(self) -> None:
        """Recover gateway completion state after a process restart."""
        for pending in self._report_outbox.pending():
            self._publish_lifecycle(command_lifecycle.completed(
                to_patrol_report_record(pending)))

    def _motion_ready(self) -> bool:
        """Require robot readiness and local safety's single authority view."""
        return (
            self._motion_gate.ready()
            and self._motion_permission.allowed()
        )

    def _motion_summary(self) -> str:
        """Combine static/sensor and local-safety blockers for command logs."""
        blockers = list(self._motion_gate.blocking_reasons())
        if not self._motion_permission.allowed():
            blockers.append('LOCAL_SAFETY_BLOCKED')
        return 'READY' if not blockers else ','.join(blockers)

    def _synchronize_motion_authority(self) -> None:
        """Cancel work whenever local safety revokes mission permission."""
        valid = self._motion_permission.allowed()
        self._arbiter.set_external_stop(not valid)
        if valid != self._motion_authority_was_valid:
            if valid:
                self.get_logger().info(
                    'motion authority ready; waiting for MissionCommand')
            else:
                self.get_logger().warn(
                    'motion authority unavailable (LOCAL_SAFETY_BLOCKED); '
                    'motion canceled')
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
