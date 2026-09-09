"""command_gateway ROS node: receive MissionCommand, answer CommandCheck.

19단계. This is the ROS owner the pure modules were written for --
mission_ingress.py says as much in its own docstring ("shared by a future
ROS mission node"). It joins three of them:

* command_store.CommandStore -- durable command identity in SQLite, so a
  restart does not re-execute a command that already ran.
* mission_ingress.MissionIngress -- the fixed duplicate-handling contract
  turned into one decision per received command.
* command_check.CommandCheckFactory -- the ACCEPTED/EXECUTING/REJECTED
  answer on the public ``command_check`` topic.

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

* ``mission_dispatch`` (MissionCommand) -- run this command, once. Emitted
  only for a genuinely new command, never for a duplicate.
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

Answering the arbiter correctly and never running the same command twice
is a separable job, and it is the half whose contract is already fixed.

CommandCheck values and the command-ID conflict code follow the fixed
2026-09-08 interface contract rather than launch-time parameters.
"""

import os

from patrol_amr import command_check as cc
from patrol_amr import command_lifecycle as cl
from patrol_amr import command_store as cs
from patrol_amr import mission_ingress as mi
from patrol_amr import patrol_report as pr
from patrol_amr.mission_command_parser import (
    InvalidMissionCommand, MissionCommandParser)


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
    from patrol_interfaces.msg import CommandCheck, MissionCommand, PatrolReport
    from std_msgs.msg import String

    class CommandGateway(Node):
        """Answer every MissionCommand exactly once per command identity."""

        # Q-14 의 경계는 24시간이라 1초에 1초씩만 움직인다. 명령마다 DELETE 를
        # 돌리면 얻는 것 없이 쓰기만 늘고, 하루짜리 창에서 1분의 지연은 보존
        # 판정을 바꾸지 않는다. 계약 수치가 아니라 이 노드의 유지보수 주기다.
        PRUNE_PERIOD_SECONDS = 60.0

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

            command_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            # 내부 신호. battery_status·motion_allowed 와 같은 성격이며 공용
            # 인터페이스를 추가한 것이 아니다.
            #
            # durability 가 두 신호에서 다른 것은 의도한 것이다. 명령을 한 번만
            # 실행하라는 신호(dispatch)와 재전송하라는 신호(replay)를
            # TRANSIENT_LOCAL 로 두면 늦게 붙은 구독자에게 과거 신호가 다시
            # 전달되어 명령이 두 번 실행된다. 반대로 active_command 는 "지금
            # 어느 명령인가"라는 상태이므로, 늦게 뜬 status_reporter 도 마지막
            # 값을 받아야 RobotStatus 가 빈 ID 로 나가지 않는다.
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
            lifecycle_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=20,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            self._check_publisher = self.create_publisher(
                CommandCheck, 'command_check', cc.command_check_qos()
            )
            self._dispatch_publisher = self.create_publisher(
                MissionCommand, 'mission_dispatch', edge_qos
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
                String,
                'mission_lifecycle',
                self._on_mission_lifecycle,
                lifecycle_qos,
            )
            # 시작 시 한 번 — 저장소에는 지난 세션의 오래된 기록이 남아 있다.
            self._prune()
            self.create_timer(self.PRUNE_PERIOD_SECONDS, self._prune)

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
                self._dispatch_publisher.publish(message)

        def _on_mission_lifecycle(self, message) -> None:
            """Apply mission-owned execution facts to the gateway DB."""
            try:
                event = cl.from_json(message.data)
                state = self._store.validate_identity(
                    event.command_id, event.mission_id, event.robot_id)
                if event.kind is cl.LifecycleKind.EXECUTING:
                    self._store.mark_executing(event.command_id)
                    record = self._publish_check(
                        event.command_id,
                        event.mission_id,
                        cc.CheckMeaning.EXECUTING,
                        active=True,
                    )
                    self.get_logger().info(
                        'command execution started: '
                        f'command_id={event.command_id!r} '
                        f'sequence={record.sequence}'
                    )
                    return

                # A retained completion may be replayed after gateway restart
                # before the old EXECUTING event is available. Reconstruct the
                # required forward transition instead of losing completion.
                if state is cs.CommandState.ACCEPTED:
                    self._store.mark_executing(event.command_id)
                    self._publish_check(
                        event.command_id,
                        event.mission_id,
                        cc.CheckMeaning.EXECUTING,
                        active=True,
                    )
                self._store.complete_report(event.command_id, event.report)
                self.get_logger().info(
                    'command completion stored: '
                    f'command_id={event.command_id!r} '
                    f'report_id={event.report.report_id!r}'
                )
            except (KeyError, ValueError) as error:
                self.get_logger().error(
                    f'ignored invalid mission lifecycle event: {error}')

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
