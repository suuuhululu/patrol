#!/usr/bin/env python3
"""Center CCTV 노드: 주차 구역 PARKED/EXITING 판정 후 CameraState 발행.

CR-관제_09-07_17-53_비전_CameraState와_permit_반영(P0) 반영판. TBD-VIS-001
확정값(비전팀 제안) 위에 관제팀 요청을 반영해 아래를 바꿨다.
- event_id를 UUID 대신 구조화 ID로 바꿨다(gate_cam.py와 동일 규칙):
  source_session_id = center_cam-<YYYYMMDDTHHMMSS>-<restart_sequence>
  event_id           = cam-<source_session_id>-<state>-<source_sequence>
  restart_sequence는 노드가 뜰 때마다 로컬 파일에서 읽어 +1 하고 다시 쓰는
  가벼운 카운터다(판단에 영향 없는 진단용 값이라 TBD-VIS-002의 "재시작 시
  상태 비영속화" 원칙과는 별개로 취급한다).
- camera_id를 'CENTER'에서 'center_cam'으로 바꿨다.
- EXITING 확정 기준을 "3프레임 연속"에서 "time.monotonic() 기준 0.2초
  연속 유지"로 바꿨다. PARKED는 기존처럼 ROI 5초 체류로 확정한다(이 부분은
  0.2초 확인이 아니므로 미검출 시 즉시 초기화 대상이 아니다 - 가려짐에 대한
  관용은 PARKED 5초 dwell에서는 그대로 유지).
- EXITING 확인 중 미검출 프레임이 오거나 ROI로 복귀하면 진행 중인 0.2초
  확인을 즉시 초기화한다.
- CameraState.confidence는, PARKED는 확정 직전 마지막 0.2초 구간의 평균,
  EXITING은 0.2초 확인 구간에 쓰인 프레임들의 평균이다.
- 카메라가 FAULT_TIMEOUT_SEC(3초) 연속 프레임을 못 읽으면 장애로 로그 남김.
- DEBUG_VIEW=True면 ROI·박스·상태 텍스트를 cv2.imshow로 계속 띄운다.
  실제 배포 시엔 False로.

문서 근거:
- 토픽/네임스페이스: interfaces.md 1절, architecture.md 2절 (/vision/cctv/center_event)
- QoS: interfaces.md 9절 (CCTV event: RELIABLE/VOLATILE/KEEP_LAST(20))
- state 허용값: vision.md 1절 (center_cam: PARKED, EXITING만)
- event_id·camera_id·0.2초 판정: CR-관제_09-07_17-53_비전_CameraState와_permit_반영,
  TBD-IF-005(확정 반영)

TBD:
- 장애를 관제/시스템 모니터에 실제로 알리는 공용 전달은 차기 버전 TBD-IF-010
"""
import os
import time
from datetime import datetime

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
CONFIRM_SECONDS = 0.2       # EXITING 확인 및 confidence 평균 구간 (FPS 무관)
FAULT_TIMEOUT_SEC = 3.0     # 장애 판단 기준
DEBUG_VIEW = True           # 확인용 화면 표시. 배포 시 False로 변경

CAMERA_ID = 'center_cam'
RESTART_SEQ_DIR = "/home/hv-06/patrol/state"

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


def load_and_bump_restart_sequence(camera_id: str, state_dir: str = RESTART_SEQ_DIR) -> int:
    """노드가 뜰 때마다 1씩 증가하는 카운터. 파일이 없거나 손상돼도 1로
    시작하는 안전한 폴백을 쓴다(patrol_allowed 판단에는 영향 없는 진단용 값).
    """
    path = os.path.join(state_dir, f'{camera_id}_restart_seq.txt')
    seq = 1
    try:
        os.makedirs(state_dir, exist_ok=True)
        if os.path.exists(path):
            with open(path, 'r') as f:
                seq = int(f.read().strip()) + 1
    except (OSError, ValueError):
        seq = 1
    try:
        with open(path, 'w') as f:
            f.write(str(seq))
    except OSError:
        pass
    return seq


def build_source_session_id(camera_id: str, restart_sequence: int, started_at: datetime = None) -> str:
    started_at = started_at or datetime.now()
    return f'{camera_id}-{started_at.strftime("%Y%m%dT%H%M%S")}-{restart_sequence:02d}'


def build_event_id(source_session_id: str, state: str, source_sequence: int) -> str:
    return f'cam-{source_session_id}-{state.lower()}-{source_sequence:04d}'


class CenterCam(Node):
    def __init__(self):
        super().__init__('center_cam')

        self.publisher_ = self.create_publisher(
            CameraState, '/vision/cctv/center_event', CCTV_EVENT_QOS)

        self.model = YOLO(MODEL_PATH)
        self.cap = cv2.VideoCapture(CAMERA_SOURCE, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            self.get_logger().error(f'camera_source={CAMERA_SOURCE} 열기 실패')

        restart_sequence = load_and_bump_restart_sequence(CAMERA_ID)
        self._source_session_id = build_source_session_id(CAMERA_ID, restart_sequence)
        self._source_sequence = 0
        self.get_logger().info(f'center_cam: source_session_id={self._source_session_id}')

        self._current_roi = None
        self._roi_enter_time = None
        self._confs_in_roi = []            # [(monotonic_ts, conf), ...]
        self._parked_confirmed = False
        self._exit_confirm_start = None    # monotonic 시작 시각
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
        # CR-관제 0907: EXITING 0.2초 확인 도중 미검출이 오면 즉시 초기화한다.
        # (PARKED 5초 dwell은 0.2초 확인이 아니므로 여기서 건드리지 않는다 -
        #  가려짐에 대한 관용은 dwell 쪽에서 그대로 유지.)
        if self._exit_confirm_start is not None:
            self._exit_confirm_start = None
            self._exit_confirm_confs = []
            self._last_state_text = 'WAITING (lost detection during EXITING confirm)'

    def _on_detection(self, current_roi, conf):
        now_wall = time.time()
        now_mono = time.monotonic()

        if current_roi is not None:
            # ROI 안에 있음 -> EXITING 확인 진행 중이었다면 초기화(복귀)
            if self._exit_confirm_start is not None:
                self._exit_confirm_start = None
                self._exit_confirm_confs = []

            if self._current_roi != current_roi:
                # 새 ROI 진입(또는 다른 ROI로 전환)
                self._current_roi = current_roi
                self._roi_enter_time = now_wall
                self._confs_in_roi = [(now_mono, conf)]
                self._parked_confirmed = False
            else:
                self._confs_in_roi.append((now_mono, conf))

            stay_time = now_wall - self._roi_enter_time
            self._last_state_text = f'{current_roi} stay={stay_time:.1f}s'

            if (not self._parked_confirmed
                    and stay_time >= PARKED_SECONDS
                    and now_wall - self._last_event_time >= EVENT_COOLDOWN_SECONDS):
                window = [c for t, c in self._confs_in_roi if now_mono - t <= CONFIRM_SECONDS]
                if not window:
                    window = [self._confs_in_roi[-1][1]]
                avg_conf = sum(window) / len(window)
                self._publish_state('PARKED', avg_conf)
                self._last_event_time = now_wall
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

        # PARKED 상태였는데 ROI 밖으로 보임 -> 0.2초 연속 확인 후 EXITING
        if self._exit_confirm_start is None:
            self._exit_confirm_start = now_mono
            self._exit_confirm_confs = [conf]
        else:
            self._exit_confirm_confs.append(conf)

        elapsed = now_mono - self._exit_confirm_start
        self._last_state_text = f'CONFIRMING EXITING ({elapsed:.2f}/{CONFIRM_SECONDS:.2f}s)'
        if elapsed >= CONFIRM_SECONDS:
            if now_wall - self._last_event_time >= EVENT_COOLDOWN_SECONDS:
                avg_conf = sum(self._exit_confirm_confs) / len(self._exit_confirm_confs)
                self._publish_state('EXITING', avg_conf)
                self._last_event_time = now_wall
                self._last_state_text = 'EXITING (published)'
            self._current_roi = None
            self._roi_enter_time = None
            self._confs_in_roi = []
            self._parked_confirmed = False
            self._exit_confirm_start = None
            self._exit_confirm_confs = []

    def _publish_state(self, state: str, confidence: float):
        self._source_sequence += 1
        event_id = build_event_id(self._source_session_id, state, self._source_sequence)

        msg = CameraState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.event_id = event_id
        msg.camera_id = CAMERA_ID
        msg.source_session_id = self._source_session_id
        msg.source_sequence = self._source_sequence
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
