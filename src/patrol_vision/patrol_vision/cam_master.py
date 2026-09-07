#!/usr/bin/env python3
"""cam_master: gate/center CameraState를 구독해 patrol_allowed(Bool) 발행.

CR-관제_09-07_17-53_비전_CameraState와_permit_반영(P0) 반영판. 이전 버전과
달라진 점:
- topic-camera_id 일치 검증을 추가했다. gate_event 토픽엔 camera_id='gate_cam',
  center_event 토픽엔 camera_id='center_cam'만 허용하고 그 외는 폐기+진단 로그.
- patrol_allowed 발행 방식을 "값이 바뀔 때만 발행"에서 "값이 바뀌면 즉시
  발행 + 바뀌지 않아도 5Hz로 계속 반복 발행"으로 바꿨다.

문서 근거:
- 토픽/네임스페이스: interfaces.md 1절, architecture.md 2절 (/vision/cctv/patrol_allowed)
- QoS: interfaces.md 9절 (patrol_allowed: RELIABLE/VOLATILE/KEEP_LAST(1), deadline 500ms)
- 상태→permit 매핑, 초기값 true: vision.md 3절
- topic별 허용 enum·camera_id만 수락, 그 외 폐기+진단 로그: vision.md 4절,
  CR-관제_09-07_17-53_비전_CameraState와_permit_반영
- event_id를 Q-13(10분) 동안 보관해 같은 이벤트 1회만 처리: interfaces.md 9절 Q-13
- 통신 timeout 시 마지막 patrol_allowed 값 유지, 임의로 false로 바꾸지 않음: vision.md 3절
- permit 5Hz 반복 발행: CR-관제_09-07_17-53_비전_CameraState와_permit_반영 4절

gate_cam.py/center_cam.py(P0 반영판)는 이제 event_id를 구조화 ID(cam-<source_
session_id>-<state>-<source_sequence>)로, confidence 필드에 "0.2초 확인
구간(또는 PARKED는 확정 직전 마지막 0.2초 구간) 평균 conf"를 담아 보낸다.
cam_master는 event_id 문자열을 파싱하지 않고 그 값의 계산 방식도 몰라도
되지만, confidence가 0~1 범위를 벗어나면 잘못된 값이므로 방어적으로 폐기한다.

TBD-VIS-002 확정판(2026-09-07, 비전팀):
- 순서 역전: header.stamp(실제 감지 시각)가 지금까지 반영한 것 중 가장 최신
  시각보다 과거인 이벤트는 폐기한다("과거 사건이 최신 상태를 못 뒤집는다").
  event_id가 다른 정상 이벤트라도 이 검증을 통과 못 하면 permit에 반영하지
  않는다.
- 늦게 도착한 이벤트: 위 순서 검증 하나로 처리하고, 별도의 "몇 초 이상
  지연이면 무조건 폐기" 규칙은 두지 않는다.
- 재시작 시 patrol_allowed: 그대로 True로 초기화한다(영속 저장 안 함).
- 재시작 시 event_id 캐시: 그대로 메모리 초기화한다(영속 저장 안 함).

TBD (관제팀과 확인 필요):
- TBD-IF-010: 나머지 부분(RobotStatus 변경 발행 rate 제한 등)은 이 CR로
  해결되지 않았고 여전히 OPEN이다. permit 5Hz·관제 5초 timeout 부분만
  이번 CR로 결정됐다.
"""
import time
from collections import OrderedDict

import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool

from patrol_interfaces.msg import CameraState

CCTV_EVENT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=20,
)

PATROL_ALLOWED_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
    deadline=Duration(seconds=0, nanoseconds=500_000_000),
)

GATE_CAMERA_ID = 'gate_cam'
CENTER_CAMERA_ID = 'center_cam'

GATE_ALLOWED_STATES = {CameraState.STATE_ENTERING, CameraState.STATE_EXITED}
CENTER_ALLOWED_STATES = {CameraState.STATE_PARKED, CameraState.STATE_EXITING}

# vision.md 3절: 상태 -> patrol_allowed
PATROL_ALLOWED_BY_STATE = {
    CameraState.STATE_ENTERING: False,
    CameraState.STATE_PARKED: True,
    CameraState.STATE_EXITING: False,
    CameraState.STATE_EXITED: True,
}

EVENT_ID_TTL_SEC = 600.0  # Q-13: 10분
EVENT_TIMEOUT_WARN_SEC = 5.0  # TBD-IF-010 확정 전 임시값(비전 이벤트 미수신 경고, 관제 permit timeout과는 별개)
PATROL_ALLOWED_PUBLISH_HZ = 5.0  # CR-관제 0907: permit 5Hz 반복 발행


class CamMaster(Node):
    def __init__(self):
        super().__init__('cam_master')

        self._patrol_allowed = True  # vision.md 3절: 초기값 true
        self._seen_event_ids = OrderedDict()  # event_id -> 수신 시각(monotonic)
        self._last_gate_time = None
        self._last_center_time = None
        self._last_accepted_event_stamp = None  # TBD-VIS-002: 순서 역전 가드

        self.publisher_ = self.create_publisher(
            Bool, '/vision/cctv/patrol_allowed', PATROL_ALLOWED_QOS)

        self.create_subscription(
            CameraState, '/vision/cctv/gate_event', self._on_gate_event, CCTV_EVENT_QOS)
        self.create_subscription(
            CameraState, '/vision/cctv/center_event', self._on_center_event, CCTV_EVENT_QOS)

        self._publish_patrol_allowed(self._patrol_allowed)

        self.create_timer(1.0, self._check_timeouts)
        self.create_timer(60.0, self._purge_old_event_ids)
        # CR-관제 0907: 값이 바뀌지 않아도 5Hz로 patrol_allowed를 계속 반복 발행한다.
        self.create_timer(1.0 / PATROL_ALLOWED_PUBLISH_HZ, self._republish_patrol_allowed)

    def _on_gate_event(self, msg: CameraState):
        self._last_gate_time = time.monotonic()
        self._handle_event(msg, GATE_ALLOWED_STATES, 'gate', GATE_CAMERA_ID)

    def _on_center_event(self, msg: CameraState):
        self._last_center_time = time.monotonic()
        self._handle_event(msg, CENTER_ALLOWED_STATES, 'center', CENTER_CAMERA_ID)

    def _handle_event(self, msg: CameraState, allowed_states, topic_label: str, expected_camera_id: str):
        if msg.camera_id != expected_camera_id:
            self.get_logger().warning(
                f'[{topic_label}] camera_id={msg.camera_id!r} (기대값 {expected_camera_id!r} 불일치) '
                f'event_id={msg.event_id} 폐기')
            return

        if msg.state not in allowed_states:
            self.get_logger().warning(
                f'[{topic_label}] 허용되지 않은 state={msg.state} '
                f'event_id={msg.event_id} 폐기')
            return

        if not (0.0 <= msg.confidence <= 1.0):
            self.get_logger().warning(
                f'[{topic_label}] confidence={msg.confidence} 범위 이상, '
                f'event_id={msg.event_id} 폐기')
            return

        if msg.event_id in self._seen_event_ids:
            self.get_logger().info(
                f'[{topic_label}] 중복 event_id={msg.event_id} 재수신, 무시')
            return
        self._seen_event_ids[msg.event_id] = time.monotonic()

        # TBD-VIS-002: 순서 역전 가드 - 이미 반영한 것보다 과거 시각의
        # 이벤트가 뒤늦게 도착하면 현재 상태를 뒤집지 못하게 폐기한다.
        event_stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if (self._last_accepted_event_stamp is not None
                and event_stamp < self._last_accepted_event_stamp):
            self.get_logger().warning(
                f'[{topic_label}] event_id={msg.event_id} 는 이미 반영한 '
                f'이벤트보다 과거 시각(순서 역전)이라 폐기')
            return

        new_allowed = PATROL_ALLOWED_BY_STATE.get(msg.state)
        if new_allowed is None:
            self.get_logger().error(
                f'[{topic_label}] state={msg.state} 에 대한 permit 매핑 없음')
            return

        self._last_accepted_event_stamp = event_stamp

        if new_allowed != self._patrol_allowed:
            self._patrol_allowed = new_allowed
            self._publish_patrol_allowed(self._patrol_allowed)
            self.get_logger().info(
                f'[{topic_label}] state={msg.state} -> patrol_allowed={self._patrol_allowed}')

    def _publish_patrol_allowed(self, value: bool):
        msg = Bool()
        msg.data = value
        self.publisher_.publish(msg)

    def _republish_patrol_allowed(self):
        # 값이 바뀌지 않아도 5Hz로 계속 반복 발행한다(CR-관제 0907 4절).
        self._publish_patrol_allowed(self._patrol_allowed)

    def _check_timeouts(self):
        # TBD-IF-010(비전 이벤트 미수신 경고) 확정 전까지는 경고 로그만 남기고
        # 마지막 값을 그대로 유지한다. 관제 측 permit 5초 timeout·복구는
        # 별도 구현 범위다.
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
        expired = [
            eid for eid, t in self._seen_event_ids.items()
            if now - t > EVENT_ID_TTL_SEC
        ]
        for eid in expired:
            del self._seen_event_ids[eid]


def main():
    rclpy.init()
    node = CamMaster()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
