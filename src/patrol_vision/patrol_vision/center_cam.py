#!/usr/bin/env python3
"""Center CCTV 노드: 주차 구역 PARKED/EXITING 판정 후 CameraState 발행.

TBD-VIS-001 확정값 반영판. 이전 버전과 달라진 점:
- track_id 기반 다중 트랙 관리를 없애고, 매 프레임 conf가 가장 높은 박스
  1개만 "그 차"로 취급한다(차량 한 대 전제, vision.md 2절).
- PARKED는 기존처럼 ROI 5초 체류로 확정하되, EXITING은 ROI를 벗어난 게
  CONFIRM_FRAMES(3) 프레임 연속으로 확인돼야 발행한다(가려짐으로 인한
  일시적 미탐지를 출차로 오판하지 않기 위함).
- CameraState.confidence는 확정에 쓰인 프레임들의 평균 conf를 담는다.
- 카메라가 FAULT_TIMEOUT_SEC(3초) 연속 프레임을 못 읽으면 장애로 로그 남김.
- DEBUG_VIEW=True면 원래 테스트 스크립트(center_parking_detector.py)처럼
  ROI·박스·상태 텍스트를 cv2.imshow로 계속 띄운다. 실제 배포 시엔 False로.

문서 근거:
- 토픽/네임스페이스: interfaces.md 1절, architecture.md 2절 (/vision/cctv/center_event)
- QoS: interfaces.md 9절 (CCTV event: RELIABLE/VOLATILE/KEEP_LAST(20))
- state 허용값: vision.md 1절 (center_cam: PARKED, EXITING만)

TBD (아래 상수들은 비전팀 확정 제안, 관제팀 최종 확인 전 — TBD-VIS-001):
- 장애를 관제/모니터링에 실제로 어떻게 알릴지(별도 토픽 등)는 TBD-IF-008
- event_id 생성 규칙(uuid4), state 정수 매핑은 TBD-IF-005
"""
import time
import uuid

import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from ultralytics import YOLO

from patrol_interfaces.msg import CameraState

# ---- 설정값: 실제 장비에 맞춰 여기만 수정 ----
CAMERA_SOURCE = 4
MODEL_PATH = "/home/hv-06/patrol/car_data/car_best.pt"
IMG_SIZE = 512
CONFIDENCE = 0.7
CAR_CLASS_ID = 0
TOP_PARKING_ROI = (0.2, 0.15, 0.62, 0.32)
BOTTOM_PARKING_ROI = (0.05, 0.76, 0.7, 1.00)
PARKED_SECONDS = 5.0
EVENT_COOLDOWN_SECONDS = 2.0
CONFIRM_FRAMES = 3          # 연속 프레임 확정 기준 (EXITING 확인용)
FAULT_TIMEOUT_SEC = 3.0     # 장애 판단 기준
DEBUG_VIEW = True           # 확인용 화면 표시. 배포 시 False로 변경

CCTV_EVENT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=20,
)

STATE_MAP = {
    'PARKED': CameraState.STATE_PARKED,
    'EXITING': CameraState.STATE_EXITING,
}


def ratio_to_pixel_rect(rect, w, h):
    x1, y1, x2, y2 = rect
    return x1 * w, y1 * h, x2 * w, y2 * h


def is_inside_rect(x, y, rect):
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2


def get_current_roi(cx, cy, roi_dict):
    for roi_name, rect in roi_dict.items():
        if is_inside_rect(cx, cy, rect):
            return roi_name
    return None


class CenterCam(Node):
    def __init__(self):
        super().__init__('center_cam')

        self.publisher_ = self.create_publisher(
            CameraState, '/vision/cctv/center_event', CCTV_EVENT_QOS)

        self.model = YOLO(MODEL_PATH)
        self.cap = cv2.VideoCapture(CAMERA_SOURCE, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            self.get_logger().error(f'camera_source={CAMERA_SOURCE} 열기 실패')

        self._current_roi = None
        self._roi_enter_time = None
        self._confs_in_roi = []
        self._parked_confirmed = False
        self._exit_confirm_confs = []
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
            self.get_logger().warning('center_cam: 프레임 읽기 실패')
            if not self._camera_fault and now - self._last_ok_read_time >= FAULT_TIMEOUT_SEC:
                self._camera_fault = True
                self.get_logger().error(
                    f'center_cam: {FAULT_TIMEOUT_SEC:.0f}초 연속 프레임 읽기 실패 - 카메라 장애로 판단')
            return

        self._last_ok_read_time = now
        if self._camera_fault:
            self._camera_fault = False
            self.get_logger().info('center_cam: 카메라 복구됨')

        self._detect_and_track(frame)

    # ---- 탐지: 이번 프레임에서 conf가 가장 높은 박스 1개만 사용 ----
    def _detect_and_track(self, frame):
        h, w = frame.shape[:2]
        roi_dict = {
            'TOP': ratio_to_pixel_rect(TOP_PARKING_ROI, w, h),
            'BOTTOM': ratio_to_pixel_rect(BOTTOM_PARKING_ROI, w, h),
        }

        results = self.model.predict(
            frame,
            imgsz=IMG_SIZE,
            conf=CONFIDENCE,
            classes=[CAR_CLASS_ID],
            verbose=False,
        )
        result = results[0]

        best_box = None
        best_cx = best_cy = None
        best_conf = -1.0
        if result.boxes is not None and len(result.boxes) > 0:
            boxes = result.boxes.xyxy.cpu().numpy()
            confs = result.boxes.conf.cpu().numpy()
            for box, conf in zip(boxes, confs):
                if conf > best_conf:
                    x1, y1, x2, y2 = box
                    best_conf = float(conf)
                    best_cx = (x1 + x2) / 2
                    best_cy = (y1 + y2) / 2
                    best_box = box

        if best_cx is None:
            self._on_no_detection()
        else:
            current_roi = get_current_roi(best_cx, best_cy, roi_dict)
            self._on_detection(current_roi, best_conf)

        if DEBUG_VIEW:
            self._debug_draw(frame, roi_dict, best_box, best_conf)

    def _on_no_detection(self):
        # 잠깐 놓친 프레임: 진행 중인 상태를 깨지 않고 그냥 넘어간다(가려짐 대비).
        pass

    def _on_detection(self, current_roi, conf):
        now = time.time()

        if current_roi is not None:
            # ROI 안에 있음 -> EXITING 확인 카운트는 리셋
            self._exit_confirm_confs = []

            if self._current_roi != current_roi:
                # 새 ROI 진입(또는 다른 ROI로 전환)
                self._current_roi = current_roi
                self._roi_enter_time = now
                self._confs_in_roi = [conf]
                self._parked_confirmed = False
            else:
                self._confs_in_roi.append(conf)

            stay_time = now - self._roi_enter_time
            self._last_state_text = f'{current_roi} stay={stay_time:.1f}s'

            if (not self._parked_confirmed
                    and stay_time >= PARKED_SECONDS
                    and now - self._last_event_time >= EVENT_COOLDOWN_SECONDS):
                window = self._confs_in_roi[-CONFIRM_FRAMES:]
                avg_conf = sum(window) / len(window)
                self._publish_state('PARKED', avg_conf)
                self._last_event_time = now
                self._parked_confirmed = True
                self._last_state_text = f'PARKED {current_roi} (published)'
            return

        # ROI 밖
        if self._current_roi is None:
            self._last_state_text = 'WAITING'
            return  # 원래도 밖에 있었음, 할 일 없음

        if not self._parked_confirmed:
            # PARKED 확정 전에 ROI를 벗어남 -> 그냥 리셋(출차 이벤트 아님)
            self._current_roi = None
            self._roi_enter_time = None
            self._confs_in_roi = []
            self._last_state_text = 'WAITING (left before confirm)'
            return

        # PARKED 상태였는데 ROI 밖으로 보임 -> N프레임 연속 확인 후 EXITING
        self._exit_confirm_confs.append(conf)
        self._last_state_text = f'CONFIRMING EXITING ({len(self._exit_confirm_confs)}/{CONFIRM_FRAMES})'
        if len(self._exit_confirm_confs) >= CONFIRM_FRAMES:
            if now - self._last_event_time >= EVENT_COOLDOWN_SECONDS:
                avg_conf = sum(self._exit_confirm_confs) / len(self._exit_confirm_confs)
                self._publish_state('EXITING', avg_conf)
                self._last_event_time = now
                self._last_state_text = 'EXITING (published)'
            self._current_roi = None
            self._roi_enter_time = None
            self._confs_in_roi = []
            self._parked_confirmed = False
            self._exit_confirm_confs = []

    def _publish_state(self, state: str, confidence: float):
        msg = CameraState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.event_id = str(uuid.uuid4())
        msg.camera_id = 'CENTER'
        msg.state = STATE_MAP[state]
        msg.confidence = confidence
        self.publisher_.publish(msg)
        self.get_logger().info(
            f'[CENTER] state={state} conf={confidence:.2f} event_id={msg.event_id}')

    # ---- 확인용 화면 (DEBUG_VIEW=True일 때만) ----
    def _debug_draw(self, frame, roi_dict, best_box, best_conf):
        annotated = frame.copy()
        for roi_name, rect in roi_dict.items():
            x1, y1, x2, y2 = (int(v) for v in rect)
            overlay = annotated.copy()
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 255), -1)
            cv2.addWeighted(overlay, 0.18, annotated, 0.82, 0, annotated)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 255), 2)
            cv2.putText(annotated, f'{roi_name} ROI', (x1 + 8, max(25, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)

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
        cv2.putText(annotated, 'ROI 5s: PARKED | ROI -> ROAD: EXITING',
                    (10, frame.shape[0] - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        cv2.imshow('center_cam (DEBUG_VIEW)', annotated)
        cv2.waitKey(1)


def main():
    rclpy.init()
    node = CenterCam()
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
