"""local_safety_supervisor ROS node: combine drive_token/estop guards.

Subscribes /control/drive_token (DriveToken) and /control/estop (EStop),
feeds them into one DriveTokenGuard + EStopGuard per robot, and republishes
an AMR-internal `motion_allowed` signal whenever the combined verdict
changes -- the same "internal, not a public contract" pattern
battery_monitor uses for `battery_status`.

Scope note (2026-09-07, confirmed with user before implementation): this
node does not yet publish a final per-robot velocity output.
interfaces.md 7절 gives local_safety_supervisor sole ownership of that
output, but the final topic/type is TBD-IF-009, and there is no built
candidate source -- Nav2/yaw arbitration (TBD-AMR-001) belongs to
mission_supervisor, which is outside this AMR assignment's 7-file/3-node
scope per the handoff. motion_guard.py's MotionGuard.evaluate() already
implements the gate itself and is ready to receive a real candidate once
both exist; this node exercises only the allowed/blocked-reasons side,
which does not depend on a candidate value (MotionGuard.blocked_reasons()).

Import note: src/patrol_amr has no package.xml/setup.py/__init__.py yet
(9단계 scope). The plain sibling-module imports below rely on Python
adding this script's own directory to sys.path when run directly
(`python3 local_safety_supervisor.py`), the same way battery_monitor.py is
run today. Revisit these imports when 9단계 turns this into an installed
package.
"""

import time

import drive_token_guard as dtg
import estop_guard as eg
import motion_guard as mg


class SafetyGate:
    """Pure composition of the three guards for one robot; no ROS dependency.

    The ROS node's subscription callbacks extract message fields and call
    observe_drive_token()/observe_estop(); its freshness timer calls
    blocked_reasons(now) to catch drive_token lease expiry even when no new
    message arrives (Q-01 lease elapses on the clock, not on message
    receipt). EStopGuard has no such timer: it holds no lease and amr.md
    forbids adding an arbitrary local timeout for it (heartbeat/staleness
    is the separate, still-undecided TBD-IF-004).
    """

    def __init__(self, robot_id: str):
        self._token_guard = dtg.DriveTokenGuard(robot_id)
        self._estop_guard = eg.EStopGuard()
        self._motion_guard = mg.MotionGuard()

    @property
    def robot_id(self) -> str:
        return self._token_guard.robot_id

    def observe_drive_token(
        self, token, holder_robot_id, lease_seconds, sequence, now
    ):
        """Apply one /control/drive_token observation; returns TokenVerdict."""
        return self._token_guard.observe(
            token, holder_robot_id, lease_seconds, sequence, now
        )

    def observe_estop(
        self,
        active,
        cause,
        physical,
        source,
        sequence,
        activated_at_seconds,
        release_condition_started_at_seconds,
    ):
        """Apply one /control/estop observation; returns EStopVerdict."""
        return self._estop_guard.observe(
            active,
            cause,
            physical,
            source,
            sequence,
            activated_at_seconds,
            release_condition_started_at_seconds,
        )

    def blocked_reasons(self, now: float):
        """Reasons motion is blocked right now; empty means allowed."""
        drive_granted = (
            self._token_guard.authority(now) is dtg.DriveAuthority.GRANTED
        )
        estop_active = self._estop_guard.stopped
        return self._motion_guard.blocked_reasons(drive_granted, estop_active)

    def motion_allowed(self, now: float) -> bool:
        return not self.blocked_reasons(now)


def create_node_class():
    """Import ROS dependencies lazily so SafetyGate tests need no ROS setup."""
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    from patrol_interfaces.msg import DriveToken, EStop
    from std_msgs.msg import Bool

    class LocalSafetySupervisor(Node):
        """Reflect /control/drive_token and /control/estop into motion_allowed."""

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
            self._publisher = self.create_publisher(
                Bool, 'motion_allowed', output_qos
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
            self.create_timer(self.RECHECK_PERIOD_SECONDS, self._recheck)
            self._publish_if_changed()

        def _on_drive_token(self, message) -> None:
            now = time.monotonic()
            lease_seconds = dtg.duration_to_seconds(
                message.lease_duration.sec, message.lease_duration.nanosec
            )
            self._gate.observe_drive_token(
                message.token,
                message.holder_robot_id,
                lease_seconds,
                message.sequence,
                now,
            )
            self._publish_if_changed()

        def _on_estop(self, message) -> None:
            self._gate.observe_estop(
                message.active,
                message.cause,
                message.physical,
                message.source,
                message.sequence,
                eg.time_to_seconds(
                    message.activated_at.sec, message.activated_at.nanosec
                ),
                eg.time_to_seconds(
                    message.release_condition_started_at.sec,
                    message.release_condition_started_at.nanosec,
                ),
            )
            self._publish_if_changed()

        def _recheck(self) -> None:
            """Catch drive_token lease expiry with no new message (Q-01)."""
            self._publish_if_changed()

        def _publish_if_changed(self) -> None:
            now = time.monotonic()
            allowed = self._gate.motion_allowed(now)
            if allowed == self._last_published:
                return
            self._last_published = allowed
            self._publisher.publish(Bool(data=allowed))
            reasons = sorted(r.value for r in self._gate.blocked_reasons(now))
            self.get_logger().info(
                f'motion allowed: {allowed} blocked_reasons: {reasons}'
            )

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
