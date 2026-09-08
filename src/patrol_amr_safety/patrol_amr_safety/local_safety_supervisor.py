"""local_safety_supervisor ROS node: gate drive candidates into cmd_vel.

Subscribes /control/drive_token (DriveToken) and /control/estop (EStop),
feeds them into one DriveTokenGuard + EStopGuard per robot, and owns the
robot's final velocity output. interfaces.md 7절: "local_safety_supervisor
는 로봇별 최종 속도 출력의 유일한 발행자다."

Two outputs, deliberately separate (11단계 split the gates):

* `cmd_vel` (Twist) is the *output* gate -- the arbitrated drive candidate
  passed through unchanged, or STOP. Published on every accepted candidate
  and on every recheck tick while blocked, so a stopped robot keeps seeing
  explicit zeros rather than an absent stream.
* `motion_allowed` (Bool) is the *permission* gate -- token and E-stop
  only, published on change. It stays exactly as 6단계 verified it and
  does not move when Nav2 candidates start or stop arriving, because
  "no candidate right now" is not "motion is not permitted".

12단계 scope (TBD-IF-009, 2026-09-08 AMR 확정):

* Candidate input is `cmd_vel_safe` (TwistStamped) -- Nav2's standard
  chain with collision_monitor's cmd_vel_out_topic pointed here.
* `cmd_vel_yaw` is reserved in the contract but NOT subscribed: choosing
  between two candidates is 주행 중재 (TBD-AMR-001), which belongs to
  mission_supervisor and is outside this assignment. One candidate in,
  one output out.
* Topic names are relative, so a `/robot1` or `/robot6` namespace makes
  them per-robot as architecture.md 2절 requires. 13단계 wires the launch.
* Speed limits, deceleration profiles and obstacle judgment stay absent
  (TBD-AMR-006). A permitted candidate passes through unshaped.

Import note: 9단계 turned src/patrol_amr into an installed ament_python
package, so the sibling guard modules below are imported as members of
patrol_amr. Run this node with `ros2 run patrol_amr local_safety_supervisor`;
running the file directly no longer resolves those imports.
"""

import math
import time
from typing import NamedTuple

from patrol_amr_safety import drive_token_guard as dtg
from patrol_amr_safety import estop_guard as eg
from patrol_amr_safety import motion_guard as mg
from patrol_amr import heartbeat_guard as hg


class TokenStatus(NamedTuple):
    """One atomic view for RobotStatus.accepted_token_id/token_valid."""

    accepted_token_id: str
    token_valid: bool


def estop_transition_event(previous_stopped, current_stopped, verdict):
    """Return the existing safety-log name for an accepted E-stop release."""
    if (
        verdict is eg.EStopVerdict.ACCEPTED
        and previous_stopped
        and not current_stopped
    ):
        return eg.EVENT_AUTO_RELEASED
    return None


class SafetyGate:
    """Pure composition of the three guards for one robot; no ROS dependency.

    The ROS node's subscription callbacks extract message fields and call
    observe_drive_token()/observe_estop()/observe_candidate(); its freshness
    timer calls blocked_reasons(now) to catch drive_token lease expiry even
    when no new message arrives (Q-01 lease elapses on the clock, not on
    message receipt), and output() to catch Q-17 candidate staleness the
    same way. EStopGuard has no such timer: it holds no lease and amr.md
    forbids adding an arbitrary local timeout for it (heartbeat/staleness
    is the separate, still-undecided TBD-IF-004).

    Two clocks reach this class and they are not interchangeable, so the
    caller passes both rather than letting this class pick one. Q-01 lease
    is measured on the local monotonic clock (immune to wall-clock steps);
    Q-17 candidate age is measured against the candidate's own ROS stamp,
    so it must use the same ROS clock the publisher stamped with.
    """

    def __init__(self, robot_id: str):
        self._token_guard = dtg.DriveTokenGuard(robot_id)
        self._estop_guard = eg.EStopGuard(robot_id)
        self._heartbeat_guard = hg.HeartbeatGuard()
        self._motion_guard = mg.MotionGuard()
        self._candidate = None
        self._candidate_stamp = None

    @property
    def robot_id(self) -> str:
        return self._token_guard.robot_id

    @property
    def estop_active(self) -> bool:
        """Current reflected E-stop state; True is the fail-safe default."""
        return self._estop_guard.stopped

    def token_status(self, now: float) -> TokenStatus:
        """Return the currently valid token, or the fail-safe empty state.

        An expired, revoked, invalid, or other-holder token is not accepted
        by this robot, so its public ID is empty as well as invalid. Keeping
        the two values in one view prevents a reporter from pairing a stale
        ID with a newer validity decision.
        """
        valid = (
            self._token_guard.authority(now) is dtg.DriveAuthority.GRANTED
        )
        return TokenStatus(
            self._token_guard.token_id if valid else '',
            valid,
        )

    def observe_drive_token(
        self,
        control_session_id,
        token_id,
        holder_robot_id,
        lease_seconds,
        message_sequence,
        now,
    ):
        """Apply one /control/drive_token observation; returns TokenVerdict."""
        return self._token_guard.observe(
            control_session_id,
            token_id,
            holder_robot_id,
            lease_seconds,
            message_sequence,
            now,
        )

    def observe_estop(
        self,
        target_robot_id,
        active,
        reason,
        sequence,
    ):
        """Apply one /control/estop observation; returns EStopVerdict."""
        return self._estop_guard.observe(
            target_robot_id,
            active,
            reason,
            sequence,
        )

    def observe_heartbeat(self, control_session_id, sequence, now):
        """Accept a heartbeat and revoke any token from an older session."""
        previous = self._heartbeat_guard.control_session_id
        verdict = self._heartbeat_guard.observe(
            control_session_id, sequence, now)
        if (
            verdict is hg.HeartbeatVerdict.ACCEPTED
            and control_session_id != previous
        ):
            self._token_guard.synchronize_control_session(
                control_session_id, now)
        return verdict

    def observe_candidate(self, linear, angular, stamp_seconds) -> bool:
        """Store one arbitrated drive candidate; False if it was rejected.

        The candidate is already arbitrated upstream (TBD-AMR-001); this
        only filters values that cannot be gated at all. A non-finite
        component or stamp is dropped instead of raising, because these
        arrive on a ROS callback and killing the node would remove the one
        thing keeping the robot stopped. A dropped sample leaves the
        previous candidate in place to age out under Q-17, so the failure
        direction stays STOP.
        """
        for value in (linear, angular, stamp_seconds):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False
            if not math.isfinite(value):
                return False
        self._candidate = (float(linear), float(angular))
        self._candidate_stamp = float(stamp_seconds)
        return True

    def output(self, monotonic_now: float, ros_now: float):
        """Return (final (linear, angular), blocked_reasons) for cmd_vel.

        `monotonic_now` drives the Q-01 lease, `ros_now` the Q-17 candidate
        age. Empty reasons means the stored candidate passes through
        unchanged; otherwise the output is MotionGuard.STOP.
        """
        drive_granted = (
            self._token_guard.authority(monotonic_now)
            is dtg.DriveAuthority.GRANTED
        )
        estop_active = self._estop_guard.stopped
        heartbeat_healthy = self._heartbeat_guard.healthy(monotonic_now)
        if self._candidate is None:
            return self._motion_guard.evaluate(
                drive_granted, estop_active, None, None, heartbeat_healthy
            )
        return self._motion_guard.evaluate(
            drive_granted,
            estop_active,
            self._candidate,
            ros_now - self._candidate_stamp,
            heartbeat_healthy,
        )

    def blocked_reasons(self, now: float):
        """Reasons motion is *permitted* to be blocked; empty means allowed.

        Token and E-stop only -- candidate freshness is not here on
        purpose. See motion_guard.MotionGuard.blocked_reasons().
        """
        drive_granted = (
            self._token_guard.authority(now) is dtg.DriveAuthority.GRANTED
        )
        estop_active = self._estop_guard.stopped
        heartbeat_healthy = self._heartbeat_guard.healthy(now)
        return self._motion_guard.blocked_reasons(
            drive_granted, estop_active, heartbeat_healthy)

    def motion_allowed(self, now: float) -> bool:
        return not self.blocked_reasons(now)


def create_node_class():
    """Import ROS dependencies lazily so SafetyGate tests need no ROS setup."""
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    from geometry_msgs.msg import Twist, TwistStamped
    from patrol_interfaces.msg import ControlHeartbeat, DriveToken, EStop
    from std_msgs.msg import Bool, String, UInt8

    def to_twist(pair):
        """Final output is unstamped Twist: the drive base takes no stamp.

        irobot_create_control 의 diffdrive_controller 는 use_stamped_vel:
        false 다. 후보는 Q-17 신선도 판정에 stamp 가 필요해 TwistStamped
        지만, 최종 출력은 구동부가 기대하는 형태로 되돌린다 (TBD-IF-009).
        """
        message = Twist()
        message.linear.x = pair[0]
        message.angular.z = pair[1]
        return message

    class LocalSafetySupervisor(Node):
        """Gate the drive candidate into cmd_vel; also report motion_allowed."""

        RECHECK_PERIOD_SECONDS = 0.1

        def __init__(self):
            super().__init__('local_safety_supervisor')
            self.declare_parameter('robot_id', '')
            robot_id = (
                self.get_parameter('robot_id').get_parameter_value().string_value
            )
            if robot_id not in dtg.ROBOT_IDS:
                raise ValueError(
                    "robot_id parameter must be one of "
                    f"{dtg.ROBOT_IDS}, got {robot_id!r}. Pass "
                    "--ros-args -p robot_id:=robot1 (or robot6)."
                )
            self._gate = SafetyGate(robot_id)
            self._last_published = None
            self._last_safety_state = None
            self._last_accepted_token_id = None
            self._last_output_reasons = None

            # 9절: drive_token은 BEST_EFFORT・VOLATILE・KEEP_LAST(3). 표의
            # "deadline 200ms, lifespan 500ms"는 실제 발행자(관제)가 지켜야
            # 할 발행 주기·보관 기한 설명으로 해석하고, 구독측 QoS에 요청
            # deadline 을 걸지 않는다. deadline 을 요청하면 그 값을 명시적
            # 으로 제공하지 않는 발행자와는 DDS 계층에서 아예 호환되지 않아
            # (RxO 규칙상 미지정 offered deadline 은 무한대로 취급되어 항상
            # 불일치) 메시지 자체가 도달하지 않는다 — 실제로 ros2 topic pub
            # 으로 재현해 확인했다. 신선도(끊김 감지)는 이미 구현된 Q-01
            # lease 만료(DriveTokenGuard.authority, 애플리케이션 계층)가
            # 담당하므로 DDS deadline 이 없어도 안전 방향은 유지된다.
            drive_token_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=3,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            heartbeat_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=3,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            # 9절: estop은 RELIABLE・TRANSIENT_LOCAL, "단일 상태, 정확한
            # depth TBD". depth=1은 이 노드(구독측)만의 로컬 선택이며 공용
            # 계약이 아니다 — "단일 상태" 문구를 그대로 따른 것뿐이다.
            estop_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            # motion_allowed는 battery_status와 같은 AMR 내부 신호다. 공용
            # BatteryEvent 계약을 추가하지 않은 2단계와 같은 이유로, 이
            # 토픽도 공용 인터페이스로 추가한 것이 아니다.
            output_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            # 12단계 최종 속도 경로 (TBD-IF-009, 2026-09-08 AMR 확정).
            # RELIABLE・VOLATILE・KEEP_LAST(1): 속도는 최신 표본만 의미가
            # 있으므로 depth 1 이고, 지난 값을 늦게 받아 봐야 위험하므로
            # TRANSIENT_LOCAL 을 쓰지 않는다. drive_token 에서 겪은 것과
            # 같은 이유로 구독측에 deadline·lifespan 을 요청하지 않는다 —
            # 그 값을 명시하지 않는 발행자와 DDS 계층에서 아예 매칭되지
            # 않는다. Nav2 의 TwistPublisher 기본값(RELIABLE・VOLATILE)과
            # 호환된다.
            velocity_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            self._publisher = self.create_publisher(
                Bool, 'motion_allowed', output_qos
            )
            self._safety_state_publisher = self.create_publisher(
                UInt8, 'safety_state', output_qos
            )
            # 16단계 AMR 내부 연결. 비어 있지 않은 값 하나가
            # RobotStatus의 accepted_token_id와 token_valid=true를 함께
            # 뜻한다. 두 독립 토픽으로 나누지 않아 서로 다른 시점의 ID와
            # validity가 한 snapshot에 섞이지 않는다.
            self._accepted_token_publisher = self.create_publisher(
                String, 'accepted_token_id', output_qos
            )
            self._cmd_vel_publisher = self.create_publisher(
                Twist, 'cmd_vel', velocity_qos
            )
            self.create_subscription(
                DriveToken,
                '/control/drive_token',
                self._on_drive_token,
                drive_token_qos,
            )
            self.create_subscription(
                EStop, '/control/estop', self._on_estop, estop_qos
            )
            self.create_subscription(
                ControlHeartbeat,
                '/control/heartbeat',
                self._on_heartbeat,
                heartbeat_qos,
            )
            # cmd_vel_yaw 는 계약에만 예약하고 구독하지 않는다: 두 후보
            # 사이의 선택은 주행 중재(TBD-AMR-001)이고 이 작업 범위 밖이다.
            self.create_subscription(
                TwistStamped, 'cmd_vel_safe', self._on_candidate, velocity_qos
            )
            self.create_timer(self.RECHECK_PERIOD_SECONDS, self._recheck)
            self._publish_if_changed()
            self._publish_token_status_if_changed()
            self._publish_output(always=True)

        def _on_drive_token(self, message) -> None:
            now = time.monotonic()
            lease_seconds = dtg.duration_to_seconds(
                message.lease_duration.sec, message.lease_duration.nanosec
            )
            self._gate.observe_drive_token(
                message.control_session_id,
                message.token_id,
                message.holder_robot_id,
                lease_seconds,
                message.message_sequence,
                now,
            )
            self._publish_if_changed()
            self._publish_token_status_if_changed()
            self._publish_output(always=False)

        def _on_estop(self, message) -> None:
            previous_stopped = self._gate.estop_active
            verdict = self._gate.observe_estop(
                message.target_robot_id,
                message.active,
                message.reason,
                message.sequence,
            )
            event = estop_transition_event(
                previous_stopped, self._gate.estop_active, verdict
            )
            if event is not None:
                self.get_logger().info(
                    f'{event} robot_id={self._gate.robot_id} '
                    f'target_robot_id={message.target_robot_id!r} '
                    f'sequence={message.sequence}'
                )
            self._publish_if_changed()
            # E-stop 활성은 "즉시 반영"이므로 재확인 타이머를 기다리지 않고
            # 이 콜백에서 바로 STOP 을 내보낸다 (amr.md 3절).
            self._publish_output(always=False)

        def _on_heartbeat(self, message) -> None:
            verdict = self._gate.observe_heartbeat(
                message.control_session_id,
                message.sequence,
                time.monotonic(),
            )
            if verdict is not hg.HeartbeatVerdict.ACCEPTED:
                self.get_logger().warning(
                    f'dropped heartbeat: {verdict.value} '
                    f'control_session_id={message.control_session_id!r} '
                    f'sequence={message.sequence}'
                )
            self._publish_if_changed()
            self._publish_token_status_if_changed()
            self._publish_output(always=False)

        def _on_candidate(self, message) -> None:
            accepted = self._gate.observe_candidate(
                message.twist.linear.x,
                message.twist.angular.z,
                self._stamp_seconds(message.header.stamp),
            )
            if not accepted:
                self.get_logger().warning(
                    'dropped non-finite drive candidate; keeping the previous '
                    'one to age out under Q-17'
                )
                return
            self._publish_output(always=True)

        def _recheck(self) -> None:
            """Catch lease expiry (Q-01) and candidate staleness (Q-17).

            Both elapse on a clock rather than on message receipt, so with
            no new message arriving nothing else would notice them.
            """
            self._publish_if_changed()
            self._publish_token_status_if_changed()
            self._publish_output(always=False)

        def _publish_token_status_if_changed(self) -> None:
            token_id = self._gate.token_status(
                time.monotonic()
            ).accepted_token_id
            if token_id == self._last_accepted_token_id:
                return
            self._last_accepted_token_id = token_id
            self._accepted_token_publisher.publish(String(data=token_id))

        def _publish_if_changed(self) -> None:
            now = time.monotonic()
            allowed = self._gate.motion_allowed(now)
            safety_state = 4 if self._gate.estop_active else (1 if allowed else 3)
            if safety_state != self._last_safety_state:
                self._last_safety_state = safety_state
                self._safety_state_publisher.publish(UInt8(data=safety_state))
            if allowed != self._last_published:
                self._last_published = allowed
                self._publisher.publish(Bool(data=allowed))
            else:
                return
            reasons = sorted(r.value for r in self._gate.blocked_reasons(now))
            self.get_logger().info(
                f'motion allowed: {allowed} blocked_reasons: {reasons}'
            )

        @staticmethod
        def _stamp_seconds(stamp) -> float:
            return stamp.sec + stamp.nanosec / 1e9

        def _publish_output(self, always: bool) -> None:
            """Publish the gated final velocity.

            `always=True` comes from an accepted candidate: the permitted
            stream is republished at the candidate's own rate, adding no
            latency of its own. `always=False` comes from the recheck timer
            and the token/E-stop callbacks, which publish only when the
            gate blocks -- a stopped robot must keep receiving explicit
            zeros, but a running one is already being fed by its candidate
            stream and does not need duplicates.
            """
            output, reasons = self._gate.output(
                time.monotonic(),
                self.get_clock().now().nanoseconds / 1e9,
            )
            reason_values = tuple(sorted(r.value for r in reasons))
            if reason_values != self._last_output_reasons:
                self._last_output_reasons = reason_values
                self.get_logger().info(
                    f'cmd_vel: {"STOP" if reasons else "candidate"} '
                    f'blocked_reasons: {list(reason_values)}'
                )
            if always or reasons:
                self._cmd_vel_publisher.publish(to_twist(output))

    return LocalSafetySupervisor, rclpy


def main(args=None):
    """Run the local_safety_supervisor ROS node."""
    LocalSafetySupervisor, rclpy = create_node_class()
    rclpy.init(args=args)
    node = LocalSafetySupervisor()
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
