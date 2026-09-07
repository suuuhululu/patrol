#!/usr/bin/env python3
"""Gate CCTV 노드: 입구 차량 ENTERING/EXITED 판정 후 CameraState 발행.

TBD-VIS-001 확정값 반영판. 이전 버전과 달라진 점:
- track_id 기반 다중 트랙 관리를 없애고, 매 프레임 conf가 가장 높은 박스
  1개만 "그 차"로 취급한다(차량 한 대 전제, vision.md 2절).
- 라인 교차가 감지돼도 즉시 발행하지 않고, 반대편에 CONFIRM_FRAMES(3)
  프레임 연속으로 머무는지 재확인한 뒤 발행한다(순간 좌표 흔들림 오탐 방지).
- CameraState.confidence는 그 확인 프레임들의 평균 conf를 담는다.
- 카메라가 FAULT_TIMEOUT_SEC(3초) 연속 프레임을 못 읽으면 장애로 로그 남김.
- DEBUG_VIEW=True면 원래 테스트 스크립트(gate_vertical_line_detector.py)처럼
  라인·박스·상태 텍스트를 cv2.imshow로 계속 띄운다. 실제 배포 시엔 False로.

문서 근거:
- 토픽/네임스페이스: interfaces.md 1절, architecture.md 2절 (/vision/cctv/gate_event)
- QoS: interfaces.md 9절 (CCTV event: RELIABLE/VOLATILE/KEEP_LAST(20))
- state 허용값: vision.md 1절 (gate_cam: ENTERING, EXITED만)

TBD (아래 상수들은 비전팀 확정 제안, 관제팀 최종 확인 전 — TBD-VIS-001):
- 장애를 관제/모니터링에 실제로 어떻게 알릴지(별도 토픽 등)는 TBD-IF-008
- event_id 생성 규칙(uuid4), state 정수 매핑은 TBD-IF-005
"""
import time
import uuid
from collections import deque

import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from ultralytics import YOLO

from patrol_interfaces.msg import CameraState

# ---- 설정값: 실제 장비에 맞춰 여기만 수정 ----
CAMERA_SOURCE = 2
MODEL_PATH = "/home/hv-06/patrol/car_data/car_best.pt"
IMG_SIZE = 512
CONFIDENCE = 0.7
CAR_CLASS_ID = 0
LINE_LEFT_RATIO = 0.32
LINE_RIGHT_RATIO = 0.70
ROI_TOP_RATIO = 0.45
ROI_BOTTOM_RATIO = 0.95
EVENT_COOLDOWN_SECONDS = 2.0
CONFIRM_FRAMES = 3          # 연속 프레임 확정 기준
FAULT_TIMEOUT_SEC = 3.0     # 장애 판단 기준
DEBUG_VIEW = True           # 확인용 화면 표시. 배포 시 False로 변경

# interfaces.md 9절: CCTV event QoS
CCTV_EVENT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=20,
)

STATE_MAP = {
    'ENTERING': CameraState.STATE_ENTERING,
    'EXITED': CameraState.STATE_EXITED,
}


def crossed(prev_x, curr_x, line_x):
    return (prev_x < line_x <= curr_x) or (prev_x > line_x >= curr_x)


class GateCam(Node):
    def __init__(self):
        super().__init__('gate_cam')

        self.publisher_ = self.create_publisher(
            CameraState, '/vision/cctv/gate_event', CCTV_EVENT_QOS)

        self.model = YOLO(MODEL_PATH)
        self.cap = cv2.VideoCapture(CAMERA_SOURCE, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            self.get_logger().error(f'camera_source={CAMERA_SOURCE} 열기 실패')

        self._last_cx = None
        self._crossing_history = deque(maxlen=2)
        self._pending = None  # {'state', 'side', 'confs'}
        self._last_event_time = 0.0
        self._last_state_text = 'WAITING'

        self._last_ok_read_time = time.time()
        self._camera_fault = False

        self.create_timer(1.0 / 30.0, self._process_frame)

    # ---- 프레임 읽기 & 장애 판단 ----
    def _process_frame(self):
        ok, frame = self.cap.read()
        now = time.time()

        if not ok:
            self.get_logger().warning('gate_cam: 프레임 읽기 실패')
            if not self._camera_fault and now - self._last_ok_read_time >= FAULT_TIMEOUT_SEC:
                self._camera_fault = True
                self.get_logger().error(
                    f'gate_cam: {FAULT_TIMEOUT_SEC:.0f}초 연속 프레임 읽기 실패 - 카메라 장애로 판단')
            return

        self._last_ok_read_time = now
        if self._camera_fault:
            self._camera_fault = False
            self.get_logger().info('gate_cam: 카메라 복구됨')

        self._detect_and_track(frame)

    # ---- 탐지: 이번 프레임에서 conf가 가장 높은 박스 1개만 사용 ----
    def _detect_and_track(self, frame):
        h, w = frame.shape[:2]
        roi_top = h * ROI_TOP_RATIO
        roi_bottom = h * ROI_BOTTOM_RATIO
        left_x = w * LINE_LEFT_RATIO
        right_x = w * LINE_RIGHT_RATIO

        results = self.model.predict(
            frame,
            imgsz=IMG_SIZE,
            conf=CONFIDENCE,
            classes=[CAR_CLASS_ID],
            verbose=False,
        )
        result = results[0]

        best_box = None
        best_cx = None
        best_conf = -1.0
        if result.boxes is not None and len(result.boxes) > 0:
            boxes = result.boxes.xyxy.cpu().numpy()
            confs = result.boxes.conf.cpu().numpy()
            for box, conf in zip(boxes, confs):
                x1, y1, x2, y2 = box
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                if not (0 <= cx <= w and roi_top <= cy <= roi_bottom):
                    continue
                if conf > best_conf:
                    best_conf = float(conf)
                    best_cx = cx
                    best_box = box

        if best_cx is None:
            self._on_no_detection()
        else:
            self._on_detection(w, best_cx, best_conf)

        if DEBUG_VIEW:
            self._debug_draw(frame, left_x, right_x, roi_top, roi_bottom, best_box, best_conf)

    def _on_no_detection(self):
        # 잠깐 놓친 프레임: 진행 중인 확인은 깨지 않고 그냥 넘어간다(가려짐 대비).
        pass

    def _on_detection(self, w, cx, conf):
        left_x = w * LINE_LEFT_RATIO
        right_x = w * LINE_RIGHT_RATIO
        prev_cx = self._last_cx
        self._last_cx = cx

        # 확인(confirm) 진행 중이면: 반대편에 계속 있는지만 본다.
        if self._pending is not None:
            side = self._pending['side']
            consistent = (cx > right_x) if side == 'right' else (cx < left_x)
            if consistent:
                self._pending['confs'].append(conf)
                self._last_state_text = (
                    f"CONFIRMING {self._pending['state']} "
                    f"({len(self._pending['confs'])}/{CONFIRM_FRAMES})")
                if len(self._pending['confs']) >= CONFIRM_FRAMES:
                    avg_conf = sum(self._pending['confs']) / len(self._pending['confs'])
                    self._publish_state(self._pending['state'], avg_conf)
                    self._last_event_time = time.time()
                    self._last_state_text = f"{self._pending['state']} (published)"
                    self._pending = None
                    self._crossing_history.clear()
            else:
                # 흔들림 등으로 다시 넘어와버림 -> 오탐으로 보고 취소
                self._pending = None
                self._crossing_history.clear()
                self._last_state_text = 'WAITING (confirm canceled)'
            return

        if prev_cx is None:
            return

        now = time.time()
        if now - self._last_event_time < EVENT_COOLDOWN_SECONDS:
            return

        if crossed(prev_cx, cx, left_x) and 'L' not in self._crossing_history:
            self._crossing_history.append('L')
        if crossed(prev_cx, cx, right_x) and 'R' not in self._crossing_history:
            self._crossing_history.append('R')

        seq = list(self._crossing_history)
        if len(seq) >= 2:
            if seq[-2:] == ['L', 'R']:
                self._pending = {'state': 'ENTERING', 'side': 'right', 'confs': [conf]}
            elif seq[-2:] == ['R', 'L']:
                self._pending = {'state': 'EXITED', 'side': 'left', 'confs': [conf]}

    def _publish_state(self, state: str, confidence: float):
        msg = CameraState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.event_id = str(uuid.uuid4())
        msg.camera_id = 'GATE'
        msg.state = STATE_MAP[state]
        msg.confidence = confidence
        self.publisher_.publish(msg)
        self.get_logger().info(
            f'[GATE] state={state} conf={confidence:.2f} event_id={msg.event_id}')

    # ---- 확인용 화면 (DEBUG_VIEW=True일 때만) ----
    def _debug_draw(self, frame, left_x, right_x, roi_top, roi_bottom, best_box, best_conf):
        annotated = frame.copy()
        overlay = annotated.copy()
        cv2.rectangle(overlay, (0, int(roi_top)), (frame.shape[1], int(roi_bottom)), (70, 70, 70), -1)
        annotated = cv2.addWeighted(overlay, 0.18, annotated, 0.82, 0)

        cv2.line(annotated, (int(left_x), int(roi_top)), (int(left_x), int(roi_bottom)), (255, 0, 0), 2)
        cv2.line(annotated, (int(right_x), int(roi_top)), (int(right_x), int(roi_bottom)), (0, 255, 255), 2)
        cv2.putText(annotated, 'LINE L', (int(left_x) + 5, int(roi_top) + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
        cv2.putText(annotated, 'LINE R', (int(right_x) + 5, int(roi_top) + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        if best_box is not None:
            x1, y1, x2, y2 = best_box
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            cv2.circle(annotated, (cx, cy), 5, (0, 0, 255), -1)
            cv2.putText(annotated, f'car {best_conf:.2f}', (int(x1), max(20, int(y1) - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

        cv2.putText(annotated, f'STATE: {self._last_state_text}', (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
        cv2.putText(annotated, 'left -> right: ENTERING | right -> left: EXITED',
                    (10, frame.shape[0] - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        cv2.imshow('gate_cam (DEBUG_VIEW)', annotated)
        cv2.waitKey(1)


def main():
    rclpy.init()
    node = GateCam()
    try:
        rclpy.spin(node)
    finally:
        node.cap.release()
        if DEBUG_VIEW:
            cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
