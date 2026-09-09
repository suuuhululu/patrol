#!/usr/bin/env python3
"""cam_master: gate/center CameraState를 구독해 patrol_allowed(Bool) 발행."""
import time                                                         # monotonic 시간 측정용
import rclpy                                                         # ROS2 파이썬 클라이언트
from rclpy.duration import Duration                                  # QoS deadline 설정용
from rclpy.node import Node                                          # ROS2 노드 베이스 클래스
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy  # QoS 설정
from std_msgs.msg import Bool                                        # patrol_allowed 메시지 타입
from patrol_interfaces.msg import CameraState                        # 구독할 메시지 타입
from patrol_vision.cam_common import CCTV_EVENT_QOS                  # gate/center와 동일한 이벤트 QoS(중복 정의 방지)

# patrol_allowed QoS: 최근 1개만 유지, 500ms 이내 발행 보장(deadline)
PATROL_ALLOWED_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
    deadline=Duration(seconds=0, nanoseconds=500_000_000),
)

GATE_CAMERA_ID = 'gate_cam'          # gate_event 토픽에서 허용할 camera_id
CENTER_CAMERA_ID = 'center_cam'      # center_event 토픽에서 허용할 camera_id

GATE_ALLOWED_STATES = {CameraState.STATE_ENTERING, CameraState.STATE_EXITED}      # gate_event 허용 state
CENTER_ALLOWED_STATES = {CameraState.STATE_PARKED, CameraState.STATE_EXITING}     # center_event 허용 state

# vision.md 3절: 상태 -> patrol_allowed 매핑
PATROL_ALLOWED_BY_STATE = {
    CameraState.STATE_ENTERING: False,   # 입차 중: 순찰 중지
    CameraState.STATE_PARKED: True,      # 주차 완료: 순찰 재개
    CameraState.STATE_EXITING: False,    # 출차 중: 순찰 중지
    CameraState.STATE_EXITED: True,      # 출차 완료: 순찰 재개
}

EVENT_ID_TTL_SEC = 600.0          # Q-13: event_id 중복 판정 캐시를 10분간 유지
EVENT_TIMEOUT_WARN_SEC = 5.0      # 이 시간 이상 이벤트 미수신 시 경고 로그(값 자체는 유지)
PATROL_ALLOWED_PUBLISH_HZ = 5.0   # patrol_allowed를 값 변화와 무관하게 반복 발행하는 주기


class CamMaster(Node):
    def __init__(self):
        super().__init__('cam_master')                                # ROS2 노드 이름 등록

        self._patrol_allowed = True         # 현재 patrol_allowed 값, 초기값은 true(vision.md 3절)
        self._seen_event_ids = {}             # event_id -> 수신 시각(monotonic), 중복 판정용
        self._last_gate_time = None           # gate_event 마지막 수신 시각(monotonic)
        self._last_center_time = None         # center_event 마지막 수신 시각(monotonic)
        self._last_accepted_event_stamp = None  # 지금까지 반영한 이벤트 중 가장 최신 header.stamp(순서 역전 가드)

        self.publisher_ = self.create_publisher(                       # patrol_allowed 발행자 생성
            Bool, '/vision/cctv/patrol_allowed', PATROL_ALLOWED_QOS)

        self.create_subscription(                                      # gate_event 구독
            CameraState, '/vision/cctv/gate_event', self._on_gate_event, CCTV_EVENT_QOS)
        self.create_subscription(                                      # center_event 구독
            CameraState, '/vision/cctv/center_event', self._on_center_event, CCTV_EVENT_QOS)

        self._publish_patrol_allowed(self._patrol_allowed)              # 시작하자마자 초기값 1회 발행

        self.create_timer(1.0, self._check_timeouts)                    # 1Hz: 이벤트 미수신 감시
        self.create_timer(60.0, self._purge_old_event_ids)              # 60s: 오래된 event_id 캐시 정리
        self.create_timer(1.0 / PATROL_ALLOWED_PUBLISH_HZ, self._republish_patrol_allowed)  # 5Hz: 반복 발행

    def _on_gate_event(self, msg: CameraState):
        self._last_gate_time = time.monotonic()                        # 수신 시각 갱신(timeout 감시용)
        self._handle_event(msg, GATE_ALLOWED_STATES, 'gate', GATE_CAMERA_ID)

    def _on_center_event(self, msg: CameraState):
        self._last_center_time = time.monotonic()                      # 수신 시각 갱신(timeout 감시용)
        self._handle_event(msg, CENTER_ALLOWED_STATES, 'center', CENTER_CAMERA_ID)

    # gate_event/center_event로 들어온 메시지 하나를 검증 후 patrol_allowed에 반영하는 함수.
    # 아래 5개 검증을 순서대로 통과해야만 값이 바뀐다 - 하나라도 걸리면 그 즉시 return으로
    # 폐기되고, 그 이전 patrol_allowed 값은 그대로 유지된다.
    def _handle_event(self, msg: CameraState, allowed_states, topic_label: str, expected_camera_id: str):
        # 1) camera_id 검증: 이 콜백은 gate_event든 center_event든 똑같이 _handle_event를
        # 타는데, expected_camera_id로 "이 토픽에는 이 카메라만 보내야 한다"를 강제한다.
        # 엉뚱한 camera_id가 섞여 들어오는 걸(설정 실수, 오작동 등) 여기서 걸러낸다.
        if msg.camera_id != expected_camera_id:
            self.get_logger().warning(
                f'[{topic_label}] camera_id={msg.camera_id!r} (기대값 {expected_camera_id!r} 불일치) '
                f'event_id={msg.event_id} 폐기')
            return

        # 2) state 검증: gate_event엔 ENTERING/EXITED만, center_event엔 PARKED/EXITING만
        # 허용된다(allowed_states로 호출부에서 다르게 넘어옴). 이 조합을 벗어나면 코드
        # 버그거나 메시지가 오염된 것이므로 반영하지 않는다.
        if msg.state not in allowed_states:
            self.get_logger().warning(
                f'[{topic_label}] 허용되지 않은 state={msg.state} '
                f'event_id={msg.event_id} 폐기')
            return

        # 3) confidence 검증: 0~1 범위를 벗어나면 애초에 값 자체가 이상한 것이므로 방어적으로 폐기.
        if not (0.0 <= msg.confidence <= 1.0):
            self.get_logger().warning(
                f'[{topic_label}] confidence={msg.confidence} 범위 이상, '
                f'event_id={msg.event_id} 폐기')
            return

        # 4) 중복 검증: 같은 event_id가 이미 한 번 반영됐으면(네트워크 재전송 등) 또
        # 처리하지 않고 무시한다. 통과한 event_id는 아래에서 캐시에 기록해둔다.
        if msg.event_id in self._seen_event_ids:
            self.get_logger().info(
                f'[{topic_label}] 중복 event_id={msg.event_id} 재수신, 무시')
            return
        self._seen_event_ids[msg.event_id] = time.monotonic()          # 처음 보는 event_id면 캐시에 기록

        # 5) 순서 역전 검증: header.stamp는 카메라 노드가 "실제로 판정한 시각"이다.
        # 네트워크 지연 등으로 이벤트가 보낸 순서와 다르게 도착할 수 있는데, 지금까지
        # 반영한 것보다 과거 시각의 이벤트가 뒤늦게 와서 최신 상태를 덮어쓰면 안 되므로
        # 여기서 막는다(예: 이미 반영된 PARKED를 뒤늦게 도착한 옛 EXITING이 되돌리는 것 방지).
        event_stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if (self._last_accepted_event_stamp is not None
                and event_stamp < self._last_accepted_event_stamp):
            self.get_logger().warning(
                f'[{topic_label}] event_id={msg.event_id} 는 이미 반영한 '
                f'이벤트보다 과거 시각(순서 역전)이라 폐기')
            return

        # 5단계를 다 통과했다 -> 이제 실제로 state를 patrol_allowed 값으로 변환한다.
        new_allowed = PATROL_ALLOWED_BY_STATE.get(msg.state)           # state -> patrol_allowed 매핑
        if new_allowed is None:                                        # 매핑표에 없는 state(이론상 도달 안 함)
            self.get_logger().error(
                f'[{topic_label}] state={msg.state} 에 대한 permit 매핑 없음')
            return

        self._last_accepted_event_stamp = event_stamp                  # 이 이벤트를 "최신"으로 기록

        if new_allowed != self._patrol_allowed:                        # 값이 바뀌는 경우에만 즉시 발행
            self._patrol_allowed = new_allowed
            self._publish_patrol_allowed(self._patrol_allowed)
            self.get_logger().info(
                f'[{topic_label}] state={msg.state} -> patrol_allowed={self._patrol_allowed}')
        # 값이 그대로면 여기서 발행하지 않는다 - 5Hz 타이머가 이어서 반복 발행한다.

    def _publish_patrol_allowed(self, value: bool):
        msg = Bool()
        msg.data = value
        self.publisher_.publish(msg)                                   # 실제 발행

    def _republish_patrol_allowed(self):
        # 값이 바뀌지 않아도 5Hz로 계속 반복 발행한다(수신측이 최신 상태를 놓치지 않도록).
        self._publish_patrol_allowed(self._patrol_allowed)

    def _check_timeouts(self):
        # 경고 로그만 남기고 마지막 patrol_allowed 값은 그대로 유지한다(임의로 바꾸지 않음).
        now = time.monotonic()
        for label, last_time in (
                ('gate', self._last_gate_time),
                ('center', self._last_center_time)):
            if last_time is not None and now - last_time > EVENT_TIMEOUT_WARN_SEC:
                self.get_logger().warning(
                    f'[{label}] {EVENT_TIMEOUT_WARN_SEC:.1f}s 이상 이벤트 미수신, '
                    f'patrol_allowed 마지막 값 유지: {self._patrol_allowed}')

    def _purge_old_event_ids(self):
        now = time.monotonic()
        expired = [                                                     # 10분(TTL) 지난 event_id만 골라서
            eid for eid, t in self._seen_event_ids.items()
            if now - t > EVENT_ID_TTL_SEC
        ]
        for eid in expired:
            del self._seen_event_ids[eid]                               # 캐시에서 제거(메모리 무한 증가 방지)

def main():
    rclpy.init()                                                        # ROS2 초기화
    node = CamMaster()                                                  # 노드 생성
    try:
        rclpy.spin(node)                                                # 콜백/타이머 반복 실행
    finally:
        node.destroy_node()                                             # ROS2 노드 정리
        rclpy.shutdown()

if __name__ == '__main__':
    main()