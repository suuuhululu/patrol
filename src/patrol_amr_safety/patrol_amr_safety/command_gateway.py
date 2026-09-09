"""Durable MissionCommand admission gateway for one AMR namespace.

The gateway joins the public command contract to the AMR mission executor:

* command_store.CommandStore -- durable command identity in SQLite, so a
  restart does not re-execute a command that already ran.
* mission_ingress.MissionIngress -- the fixed duplicate-handling contract
  turned into one decision per received command.
* command_check.CommandCheckFactory -- public ``command_check`` responses.
* pending_dispatch -- the fixed four-second admission boundary.
* mission_execution_event -- validated facts returned by the executor.

What this node does NOT do, on purpose:

* **Execute the command.** Running a MissionCommand means Nav2 goals and
  belongs to mission_supervisor. ``mission_dispatch`` carries the complete,
  validated MissionCommand to that owner instead of being acted on here.
* **Publish PatrolReport.** AMR-07 owns ``/<robot>/patrol_report`` and is
  a different assignment. A completed command arriving again must have its
  retained report re-sent, but two publishers on one report topic is the
  same failure the single-publisher rule exists to prevent on cmd_vel, so
  this node emits ``report_replay_request`` with the command_id and lets
  the report owner send it.

Three internal topics leave this node, each with exactly one meaning:

* ``mission_dispatch`` (MissionCommand) -- ask the executor to admit a
  pending command. A still-pending command can be replayed after restart or
  retry; the executor must deduplicate it by ``command_id``.
* ``active_command`` (CommandCheck) -- which command identity is current,
  for status_reporter's ``active_command_id``/``active_mission_id``.
  Emitted for accepted and already-executing commands alike, because both
  mean "this is the command in play".
* ``report_replay_request`` (PatrolReport) -- re-send this command's exact
  retained terminal report through the sole public report owner.

Splitting dispatch from active matters: a duplicate of a running command
is still the active command but must not start a second run.

This node also owns Q-14 retention. ``CommandStore.prune`` implements the
rule -- keep everything from the last 24 hours, plus the newest 1,000
older records -- but nothing was calling it, so the store grew forever.
The gateway prunes once at startup and then on a slow timer.

CommandCheck values and the command-ID conflict code follow the fixed
2026-09-08 interface contract rather than launch-time parameters.
"""

import os

from patrol_amr import command_check as cc
from patrol_amr import command_store as cs
from patrol_amr import mission_ingress as mi
from patrol_amr import patrol_report as pr
from patrol_amr.mission_command_parser import (
    InvalidMissionCommand, MissionCommandParser)
from patrol_amr_safety import mission_execution_event as mee
from patrol_amr_safety import pending_dispatch as pd


ROBOT_IDS = ('robot1', 'robot6')
DEFAULT_DATABASE_NAME = 'command_store.sqlite3'


def default_database_path(robot_id: str) -> str:
    """Per-robot store under the user's state directory.

    Kept out of the install tree so a rebuild cannot silently discard the
    record of which commands already ran.
    """
    base = os.environ.get('XDG_STATE_HOME') or os.path.expanduser('~/.local/state')
    return os.path.join(base, 'patrol_amr', robot_id, DEFAULT_DATABASE_NAME)


def validate_configuration(
    robot_id,
    source_session_id,
):
    """Raise unless every value the wire contract needs was supplied."""
    if robot_id not in ROBOT_IDS:
        raise ValueError(
            f'robot_id parameter must be one of {ROBOT_IDS}, got {robot_id!r}'
        )
    if not isinstance(source_session_id, str) or not source_session_id:
        raise ValueError(
            'source_session_id parameter must be a non-empty string; change '
            'it on every run so consumers can tell one run from the next'
        )
    # 형식은 이미 확정된 구조화 ID 다. CommandCheckFactory 도 검사하지만,
    # 여기서 먼저 걸러야 실패 원인이 parameter 라는 것이 분명해진다.
    if not pr.SOURCE_SESSION_PATTERN.match(source_session_id):
        raise ValueError(
            'source_session_id must match <robot_id>-<YYYYMMDDTHHMMSS>'
            '[-<restart_sequence>], e.g. robot1-20260908T160000. '
            f'got {source_session_id!r}'
        )
    if not source_session_id.startswith(f'{robot_id}-'):
        raise ValueError(
            f'source_session_id must start with {robot_id!r}, '
            f'got {source_session_id!r}'
        )
    return cc.CheckStateMapping()


def create_node_class():
    """Import ROS lazily so the pure modules stay testable without it."""
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import (
        DurabilityPolicy,
        HistoryPolicy,
        QoSProfile,
        ReliabilityPolicy,
    )
    from patrol_interfaces.msg import (
        CommandCheck, MissionCommand, MissionExecutionEvent, PatrolReport)

    class CommandGateway(Node):
        """Answer every MissionCommand exactly once per command identity."""

        # Q-14 의 경계는 24시간이라 1초에 1초씩만 움직인다. 명령마다 DELETE 를
        # 돌리면 얻는 것 없이 쓰기만 늘고, 하루짜리 창에서 1분의 지연은 보존
        # 판정을 바꾸지 않는다. 계약 수치가 아니라 이 노드의 유지보수 주기다.
        PRUNE_PERIOD_SECONDS = 60.0
        PENDING_TICK_SECONDS = 0.1

        def __init__(self):
            super().__init__('command_gateway')
            self.declare_parameter('robot_id', '')
            self.declare_parameter('source_session_id', '')
            self.declare_parameter('database_path', '')
            self.declare_parameter('patrol_plan_id', '')

            robot_id = self.get_parameter('robot_id').value
            source_session_id = self.get_parameter('source_session_id').value
            mapping = validate_configuration(
                robot_id,
                source_session_id,
            )

            database_path = (
                self.get_parameter('database_path').value
                or default_database_path(robot_id)
            )
            os.makedirs(os.path.dirname(os.path.abspath(database_path)), exist_ok=True)
            self._store = cs.CommandStore(database_path, robot_id)
            self._ingress = mi.MissionIngress(self._store)
            patrol_plan_id = self.get_parameter('patrol_plan_id').value
            self._parser = MissionCommandParser(
                robot_id, patrol_plan_id or f'{robot_id}_default')
            self._checks = cc.CommandCheckFactory(
                robot_id, source_session_id, mapping
            )
            self._pending_replayed = set()

            command_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            dispatch_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            edge_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            state_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            event_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=20,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            self._check_publisher = self.create_publisher(
                CommandCheck, 'command_check', cc.command_check_qos()
            )
            self._dispatch_publisher = self.create_publisher(
                MissionCommand, 'mission_dispatch', dispatch_qos
            )
            # status_reporter 가 active_command_id·active_mission_id 를 채우는
            # 입력이다. CommandCheck 타입을 재사용해 새 메시지를 만들지 않았고,
            # 여기서 이미 판정이 끝났으므로 구독자는 check_state 정수 매핑
            # (TBD-IF-001)을 알 필요가 없다.
            self._active_publisher = self.create_publisher(
                CommandCheck, 'active_command', state_qos
            )
            self._replay_publisher = self.create_publisher(
                PatrolReport, 'report_replay_request', edge_qos
            )
            self.create_subscription(
                MissionCommand,
                'mission_command',
                self._on_mission_command,
                command_qos,
            )
            self.create_subscription(
                MissionExecutionEvent,
                'mission_execution_event',
                self._on_mission_execution_event,
                event_qos,
            )
            # 시작 시 한 번 — 저장소에는 지난 세션의 오래된 기록이 남아 있다.
            self._prune()
            self.create_timer(self.PRUNE_PERIOD_SECONDS, self._prune)
            self.create_timer(
                self.PENDING_TICK_SECONDS, self._maintain_pending_commands)

            self._command_check_type = CommandCheck
            self.get_logger().info(
                f'command gateway ready: robot_id={robot_id} '
                f'source_session_id={source_session_id!r} '
                f'database_path={database_path!r}'
            )

        def _publish_check(
            self,
            command_id: str,
            mission_id: str,
            meaning: cc.CheckMeaning,
            *,
            reason_code: int = 0,
            reason: str = '',
            active: bool = False,
        ):
            record = self._checks.create(
                command_id=command_id,
                mission_id=mission_id,
                meaning=meaning,
                reason_code=reason_code,
                reason=reason,
            )
            cc.publish_record(
                self._check_publisher,
                self._command_check_type,
                record,
                self._now(),
            )
            if active:
                cc.publish_record(
                    self._active_publisher,
                    self._command_check_type,
                    record,
                    self._now(),
                )
            return record

        def _now(self) -> pr.ReportTime:
            stamp = self.get_clock().now().to_msg()
            return pr.ReportTime(sec=stamp.sec, nanosec=stamp.nanosec)

        def _on_mission_command(self, message) -> None:
            try:
                # 1A: gateway가 public 명령의 유일한 검증 입구다. mission 쪽
                # parser를 같은 설정으로 사용해 target 규칙까지 통과한 원본만
                # 내부 mission_dispatch에 보낸다.
                self._parser.parse(message)
                fields = mi.mission_command_fields(
                    message,
                    received_at=self.get_clock().now().nanoseconds / 1e9,
                )
                decision = self._ingress.observe(**fields)
            except InvalidMissionCommand as error:
                self._publish_check(
                    str(getattr(message, 'command_id', '')),
                    str(getattr(message, 'mission_id', '')),
                    cc.CheckMeaning.REJECTED,
                    reason_code=error.reason_code,
                    reason=str(error),
                )
                self.get_logger().warning(
                    'rejected MissionCommand before persistence: '
                    f'{error}'
                )
                return
            except ValueError as error:
                # 저장조차 할 수 없는 payload 다. 조용히 버리면 관제가 재전송
                # 만 반복하므로 로그를 남긴다. CommandCheck 는 command_id 가
                # 없으면 보낼 대상이 없어 발행하지 않는다.
                self.get_logger().warning(
                    f'unusable MissionCommand payload: {error}'
                )
                return

            if decision.check_meaning is not None:
                record = self._publish_check(
                    message.command_id,
                    message.mission_id,
                    decision.check_meaning,
                    reason_code=decision.reason_code,
                    reason=decision.reason,
                    active=(
                        decision.check_meaning is not cc.CheckMeaning.REJECTED
                    ),
                )
                self.get_logger().info(
                    f'command_check {decision.check_meaning.value} '
                    f'command_id={message.command_id!r} '
                    f'sequence={record.sequence}'
                )
            if decision.replay_report is not None:
                # 이미 끝난 명령이 다시 왔다. 중복 실행 대신 기존 결과를
                # 되돌려줘야 하는데, PatrolReport 발행권은 AMR-07 소유이므로
                # 여기서는 요청만 낸다.
                pr.publish_record(
                    self._replay_publisher,
                    PatrolReport,
                    decision.replay_report,
                    self._now(),
                )
                self.get_logger().info(
                    'requested report replay for a completed command: '
                    f'report_id={decision.replay_report.report_id!r} '
                    f'command_id={message.command_id!r}'
                )

            if decision.dispatch_new:
                # A retry can arrive after the original four-second window
                # but before the maintenance timer's next callback. Check the
                # durable receive time here as well so that retry timing can
                # never reopen an expired command.
                observed = self._store.observation(message.command_id)
                action = pd.decide(
                    received_at=observed.received_at,
                    now=fields['received_at'],
                    replayed_since_start=True,
                )
                if action is pd.PendingAction.REJECT_TIMEOUT:
                    self._reject_dispatch_timeout(
                        message.command_id, message.mission_id)
                    return
                self._dispatch_publisher.publish(message)
                self._pending_replayed.add(message.command_id)

        def _on_mission_execution_event(self, message) -> None:
            """Apply validated mission admission and persistence facts."""
            try:
                event = mee.from_message(message)
                state = self._store.validate_identity(
                    event.command_id, event.mission_id, event.robot_id)
                if not self._apply_event(event, state):
                    return
                self._store.record_event(
                    event.command_id, int(event.event_type), event.report_id)
                self._pending_replayed.discard(event.command_id)
                self.get_logger().info(
                    'mission execution event applied: '
                    f'event={event.event_type.name} '
                    f'command_id={event.command_id!r} '
                    f'source_session_id={event.source_session_id!r} '
                    f'sequence={event.sequence}'
                )
            except (KeyError, ValueError) as error:
                self.get_logger().error(
                    f'ignored invalid mission execution event: {error}')

        def _apply_event(self, event: mee.ExecutionEvent, state) -> bool:
            """Apply one non-duplicate event, preserving public state order."""
            if self._store.event_recorded(
                event.command_id, int(event.event_type), event.report_id
            ):
                self.get_logger().warning(
                    'ignored duplicate mission execution event: '
                    f'event={event.event_type.name} '
                    f'command_id={event.command_id!r}'
                )
                return False

            terminal_states = {
                cs.CommandState.NONTERMINAL,
                cs.CommandState.REJECTED,
                cs.CommandState.COMPLETED,
                cs.CommandState.SUPERSEDED,
            }
            if (
                state is cs.CommandState.COMPLETED
                and event.event_type is mee.EventType.RESULT_STORED
            ):
                # Covers a crash after the report transaction but before the
                # event idempotency key transaction. Exact replay is safe;
                # a different report for the same command is rejected.
                self._store.complete_report(event.command_id, event.report)
                return True
            if state in terminal_states:
                self.get_logger().warning(
                    'ignored late mission execution event for terminal '
                    f'command: event={event.event_type.name} '
                    f'command_id={event.command_id!r} state={state.value}'
                )
                return True

            if event.event_type is mee.EventType.ADMITTED:
                if state is cs.CommandState.PENDING:
                    self._store.mark_accepted(event.command_id)
                    self._publish_check(
                        event.command_id, event.mission_id,
                        cc.CheckMeaning.ACCEPTED, active=True)
                return True

            if event.event_type is mee.EventType.REJECTED:
                self._store.mark_rejected(
                    event.command_id,
                    reason_code=event.reason_code,
                    reason=event.reason,
                )
                self._publish_check(
                    event.command_id, event.mission_id,
                    cc.CheckMeaning.REJECTED,
                    reason_code=event.reason_code,
                    reason=event.reason,
                )
                return True

            if state is cs.CommandState.PENDING:
                self._store.mark_accepted(event.command_id)
                self._publish_check(
                    event.command_id, event.mission_id,
                    cc.CheckMeaning.ACCEPTED, active=True)
                state = cs.CommandState.ACCEPTED
            if state is cs.CommandState.ACCEPTED:
                self._store.mark_executing(event.command_id)
                self._publish_check(
                    event.command_id, event.mission_id,
                    cc.CheckMeaning.EXECUTING, active=True)

            if event.event_type is mee.EventType.STARTED:
                return True
            if event.event_type is mee.EventType.NONTERMINAL_STORED:
                self._store.mark_nonterminal(
                    event.command_id,
                    reason_code=event.reason_code,
                    reason=event.reason,
                )
                return True
            if event.event_type is mee.EventType.RESULT_STORED:
                self._store.complete_report(event.command_id, event.report)
                return True
            raise ValueError(f'unhandled event type: {event.event_type}')

        def _maintain_pending_commands(self) -> None:
            """Replay unexpired restart state once and reject at four seconds."""
            now = self.get_clock().now().nanoseconds / 1e9
            for stored in self._store.pending_commands():
                action = pd.decide(
                    received_at=stored.received_at,
                    now=now,
                    replayed_since_start=(
                        stored.command_id in self._pending_replayed),
                )
                if action is pd.PendingAction.WAIT:
                    continue
                if action is pd.PendingAction.REDISPATCH:
                    message = mi.populate_mission_command(
                        MissionCommand(), stored)
                    self._dispatch_publisher.publish(message)
                    self._pending_replayed.add(stored.command_id)
                    self.get_logger().info(
                        'replayed pending command after gateway start: '
                        f'command_id={stored.command_id!r}')
                    continue
                self._reject_dispatch_timeout(
                    stored.command_id, stored.mission_id)

        def _reject_dispatch_timeout(
            self, command_id: str, mission_id: str,
        ) -> None:
            """Durably close one expired admission and publish its reason."""
            self._store.mark_rejected(
                command_id,
                reason_code=206,
                reason='MISSION_DISPATCH_TIMEOUT',
            )
            self._publish_check(
                command_id,
                mission_id,
                cc.CheckMeaning.REJECTED,
                reason_code=206,
                reason='MISSION_DISPATCH_TIMEOUT',
            )
            self._pending_replayed.discard(command_id)

        def _prune(self) -> None:
            """Apply Q-14 retention to the durable command store.

            The same ROS clock that stamped ``received_at`` measures the
            cutoff; mixing in a monotonic or wall clock here would compare
            two different time bases against one stored value.
            """
            try:
                deleted = self._store.prune(
                    self.get_clock().now().nanoseconds / 1e9
                )
            except ValueError as error:
                self.get_logger().warning(f'retention prune skipped: {error}')
                return
            if deleted:
                self.get_logger().info(
                    f'Q-14 retention removed {deleted} old command records; '
                    f'{self._store.count()} retained'
                )

        def destroy_node(self):
            self._store.close()
            return super().destroy_node()

    return CommandGateway, rclpy


def main(args=None):
    """Run the command_gateway ROS node."""
    CommandGateway, rclpy = create_node_class()
    rclpy.init(args=args)
    node = CommandGateway()
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
