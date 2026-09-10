"""interfaces.md 5절 QoS 계약을 rclpy 객체로 만든다."""


def _qos_profiles():
    """현재 활성화한 토픽 QoS를 rclpy 객체로 만든다."""
    from rclpy.duration import Duration
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

    map_qos = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )
    image = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.VOLATILE,
    )
    costmap = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )
    reliable_events = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=20,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )
    # [permit 발행 계약] interfaces.md의 KEEP_LAST(1)·deadline 500 ms 그대로다.
    permit_writer = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )
    permit_writer.deadline = Duration(seconds=0.5)
    # [permit 수신] 모니터는 permit 변경을 모두 이력에 남겨야 한다.
    # 수신 큐가 1이면 영상·costmap 콜백을 처리하는 동안 도착한 Bool이 최신값으로 덮여
    # 변경이 기록되지 않는다. 큐 깊이는 수신 측 자원 설정이라 발행 계약과 충돌하지 않는다.
    permit = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=10,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )
    permit.deadline = Duration(seconds=0.5)
    state_snapshot = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )
    # [Action 숨은 토픽] rcl_action 기본값에 맞춘다. 피드백은 RELIABLE·VOLATILE·KEEP_LAST(10),
    # 상태는 RELIABLE·TRANSIENT_LOCAL이라 늦게 켜도 보존 중인 목표 상태를 바로 받는다.
    action_feedback = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=10,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )
    action_status = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )
    # [배터리] Create 3는 센서용 BEST_EFFORT로 발행한다. BEST_EFFORT 구독은 RELIABLE 발행과도 맞는다.
    battery = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.VOLATILE,
    )
    return {
        "patrol_feedback": action_feedback,
        "patrol_goal_status": action_status,
        "battery_state": battery,
        # [상태 유지] 늦게 접속한 관제도 마지막 E-stop 상태를 즉시 받는다.
        "estop": state_snapshot,
        "patrol_allowed_writer": permit_writer,
        "map": map_qos,
        "camera_frame": image, "costmap": costmap,
        "camera_state": reliable_events,
        "patrol_allowed": permit,
    }
