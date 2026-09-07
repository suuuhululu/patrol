"""interfaces.md 5절 QoS 계약을 rclpy 객체로 만든다."""


def _qos_profiles():
    """interfaces.md v1.0에서 현재 활성화한 토픽 QoS를 rclpy 객체로 만든다."""
    from rclpy.duration import Duration
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

    robot_status = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=5,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )
    robot_status.deadline = Duration(seconds=0.5)
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
    state_latched = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )
    return {
        "patrol_visit": reliable_events,
        "patrol_report": reliable_events,
        # [상태 유지] 늦게 접속한 관제도 마지막 Keepout·E-stop 상태를 즉시 받는다.
        "keepout_status": state_latched,
        "estop": state_latched,
        "patrol_allowed_writer": permit_writer,
        "robot_status": robot_status, "map": map_qos,
        "camera_frame": image, "costmap": costmap,
        "detection_event": reliable_events,
        "evidence_chunk": reliable_events,
        "ingestion_ack": reliable_events,
        "camera_state": reliable_events,
        "patrol_allowed": permit,
    }
