#!/usr/bin/env python3
"""Center CCTV 노드: 주차 구역 PARKED/EXITING 판정 후 CameraState 발행."""
import time
import cv2
import rclpy
from rclpy.node import Node
from ultralytics import YOLO
from sensor_msgs.msg import CompressedImage
from patrol_interfaces.msg import CameraState
from patrol_vision.cam_common import (
    CCTV_EVENT_QOS,
    IMAGE_STREAM_QOS,
    build_event_id,
    build_source_session_id,
    load_and_bump_restart_sequence,
)

def ratio_to_pixel_rect(rect, w, h):
    # (x1,y1,x2,y2) 비율 좌표를 실제 프레임 픽셀 좌표로 변환
    x1, y1, x2, y2 = rect
    return x1 * w, y1 * h, x2 * w, y2 * h

def is_inside_rect(x, y, rect):
    # 점 (x,y)가 사각형 rect 안에 있는지 판정
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2

def get_current_roi(cx, cy, roi_dict):
    # 여러 ROI 중 점이 속한 ROI 이름 반환, 없으면 None
    for roi_name, rect in roi_dict.items():
        if is_inside_rect(cx, cy, rect):
            return roi_name
    return None

class CenterCam(Node):
    def __init__(self):
        super().__init__('center_cam')

        self.publisher_ = self.create_publisher(CameraState, '/vision/cctv/center_event', CCTV_EVENT_QOS)
        self.image_publisher_ = self.create_publisher(                 # 대시보드용 영상 스트림 발행자 생성
            CompressedImage, '/vision/cctv/center_image/compressed', IMAGE_STREAM_QOS)

        self.model = YOLO("/home/hv-06/patrol/data/car_data/car_best_v2.pt")   # YOLO 가중치 경로(설치된 실제 장비 기준)
        self.cap = cv2.VideoCapture(4, cv2.CAP_V4L2)                   # 센터 카메라 장치 인덱스(설치 완료, 고정값)
        if not self.cap.isOpened():
            self.get_logger().error('camera_source=4 열기 실패')

        restart_sequence = load_and_bump_restart_sequence(             # 이번 실행의 재시작 순번
            'center_cam', "/home/hv-06/patrol/state")                  # camera_id / 카운터 파일 저장 폴더
        self._source_session_id = build_source_session_id('center_cam', restart_sequence)  # 이번 실행 세션 id
        self._source_sequence = 0                                      # 이번 세션 내 이벤트 순번(0부터 시작, 발행 시 +1)
        self.get_logger().info(f'center_cam: source_session_id={self._source_session_id}')

        self._current_roi = None                                       # 현재 차량이 있는 ROI 이름(없으면 None)
        self._roi_enter_time = None                                    # 현재 ROI에 진입한 시각(wall-clock)
        self._confs_in_roi = []                                        # [(monotonic_ts, conf), ...] 체류 중 conf 기록
        self._parked_confirmed = False                                 # 이번 체류에서 PARKED를 이미 발행했는지
        self._exit_confirm_start = None                                # EXITING 확인 시작 시각(monotonic)
        self._exit_confirm_confs = []                                  # EXITING 확인 구간의 conf 목록
        self._last_event_time = 0.0                                    # 마지막 이벤트 발행 시각(cooldown 기준)
        self._last_state_text = 'WAITING'                              # 디버그 화면 표시용 현재 상태 문구

        self._last_ok_read_time = time.time()                          # 마지막으로 프레임 읽기에 성공한 시각
        self._camera_fault = False                                     # 카메라 장애 여부 플래그
        self._image_frame_count = 0                                    # 영상 스트림 발행 주기 조절용(30Hz -> 10Hz)

        self.create_timer(1.0 / 30.0, self._process_frame)             # 30Hz로 프레임 처리 반복

    # ---- 프레임 읽기 & 장애 판단 ----
    def _process_frame(self):
        ok, frame = self.cap.read()                                    # 카메라에서 프레임 한 장 읽기
        now = time.time()

        if not ok:                                                     # 읽기 실패한 경우
            self.get_logger().warning('center_cam: 프레임 읽기 실패')
            if not self._camera_fault and now - self._last_ok_read_time >= 3.0:  # 3초 연속 실패 = 장애 판단 기준
                self._camera_fault = True                              # 3초 연속 실패 시 장애로 확정
                self.get_logger().error(
                    'center_cam: 3초 연속 프레임 읽기 실패 - 카메라 장애로 판단')
            return                                                     # 이번 tick은 여기서 종료(탐지 안 함)

        self._last_ok_read_time = now                                  # 성공 시각 갱신
        if self._camera_fault:
            self._camera_fault = False                                 # 장애 상태였다면 복구 처리
            self.get_logger().info('center_cam: 카메라 복구됨')

        self._detect_and_track(frame)                                  # 정상 프레임이면 탐지 로직 실행

        # 30Hz 프레임을 그대로 다 보내면 대역폭 낭비라 3프레임마다(약 10Hz) 한 번만
        # 대시보드용으로 압축 발행한다(탐지 판정 자체는 이 주기와 무관하게 매 프레임 실행됨).
        self._image_frame_count += 1
        if self._image_frame_count % 3 == 0:
            self._publish_image(frame)

    # ---- 탐지: 이번 프레임에서 conf가 가장 높은 박스 1개만 사용 ----
    def _detect_and_track(self, frame):
        h, w = frame.shape[:2]                                         # 프레임 크기
        roi_dict = {                                                   # 비율 ROI를 픽셀 좌표로 변환
            'TOP': ratio_to_pixel_rect((0.25, 0.15, 0.62, 0.32), w, h),      # 상단 주차 ROI(설치 기준 확정값)
            'BOTTOM': ratio_to_pixel_rect((0.05, 0.76, 0.7, 1.00), w, h),   # 하단 주차 ROI(설치 기준 확정값)
        }

        results = self.model.predict(                                  # YOLO 추론 실행
            frame,
            imgsz=512,           # YOLO 추론 입력 크기
            conf=0.7,            # YOLO 자체 conf 임계값
            classes=[0],          # 탐지할 클래스 id(차량)
            verbose=False,
        )
        result = results[0]                                            # 프레임 1장 결과

        best_box = None                                                # 최종 선택된 박스(디버그 표시용)
        best_cx = best_cy = None                                       # 최종 선택된 박스의 중심 좌표
        best_conf = -1.0                                                # 지금까지 찾은 최고 conf
        if result.boxes is not None and len(result.boxes) > 0:
            boxes = result.boxes.xyxy.cpu().numpy()                    # 박스 좌표 배열
            confs = result.boxes.conf.cpu().numpy()                    # 박스별 conf 배열
            for box, conf in zip(boxes, confs):
                if conf > best_conf:                                   # conf 최고값 갱신(ROI 필터 없이 전체 중 최고)
                    x1, y1, x2, y2 = box
                    best_conf = float(conf)
                    best_cx = (x1 + x2) / 2
                    best_cy = (y1 + y2) / 2
                    best_box = box

        if best_cx is None:                                             # 탐지된 차량이 없으면
            self._on_no_detection()
        else:
            current_roi = get_current_roi(best_cx, best_cy, roi_dict)  # 어느 ROI에 있는지(없으면 None)
            self._on_detection(current_roi, best_conf)

        self._debug_draw(frame, roi_dict, best_box, best_conf)

    # YOLO가 이번 프레임에서 차량을 하나도 못 찾았을 때 호출된다.
    # 여기서 건드리는 건 딱 하나, "EXITING 확인 중"이었던 상태뿐이다. PARKED로 가는
    # 중이던 ROI 체류 기록(self._confs_in_roi 등)은 여기서 절대 손대지 않는다 - 주차된
    # 차가 잠깐 다른 차에 가려져서 한두 프레임 안 잡혀도 5초 체류 카운트가 끊기면 안 되기
    # 때문이다(반대로 gate_cam의 라인 통과 확인은 이런 관용을 안 준다 - 아래 _on_detection 참고).
    def _on_no_detection(self):
        # EXITING 확인(0.2초) 도중 미검출이 오면 즉시 초기화한다.
        # PARKED 5초 체류는 0.2초 확인이 아니므로 여기서 건드리지 않는다(가려짐 관용 유지).
        if self._exit_confirm_start is not None:
            self._exit_confirm_start = None                            # EXITING 확인 시작 시각 초기화
            self._exit_confirm_confs = []                              # 누적 conf도 초기화
            self._last_state_text = 'WAITING'

    # PARKED/EXITING을 판정하는 핵심 함수. current_roi가 있으면(ROI 안) [갈래 1]로,
    # None이면(ROI 밖) [갈래 2]로 간다.
    def _on_detection(self, current_roi, conf):
        now_wall = time.time()                                         # cooldown 등 wall-clock 비교용
        now_mono = time.monotonic()                                    # 0.2초 확인 등 구간 측정용

        # ---- [갈래 1] ROI 안에 있음: "오래 머무르면 PARKED"를 확인하는 단계.
        if current_roi is not None:
            # 방금 전까지 EXITING 확인 중이었다면, 다시 ROI로 돌아온 거니 그 확인은 무효.
            if self._exit_confirm_start is not None:
                self._exit_confirm_start = None
                self._exit_confirm_confs = []

            if self._current_roi != current_roi:                       # 새 ROI 진입(또는 다른 ROI로 전환)
                # 다른 ROI로 옮겼으니 체류 시간을 처음부터 다시 잰다(이전 ROI 체류는 무효).
                self._current_roi = current_roi
                self._roi_enter_time = now_wall                        # 체류 시작 시각 기록
                self._confs_in_roi = [(now_mono, conf)]                # conf 기록 새로 시작
                self._parked_confirmed = False                         # 이번 체류는 아직 PARKED 미확정
            else:
                self._confs_in_roi.append((now_mono, conf))            # 같은 ROI면 체류 계속 -> conf만 누적

            stay_time = now_wall - self._roi_enter_time                # 현재 ROI 체류 시간
            self._last_state_text = 'PARKED' if self._parked_confirmed else 'WAITING'

            # 체류 5초를 채웠고, 아직 이번 체류에서 PARKED를 발행한 적 없고, cooldown도
            # 지났으면 -> 지금이 바로 PARKED 확정 시점이다.
            if (not self._parked_confirmed                             # 아직 PARKED 미확정이고
                    and stay_time >= 5.0                               # 5.0초(PARKED_SECONDS) 이상 체류했고
                    and now_wall - self._last_event_time >= 2.0):      # 쿨다운(2.0초)도 지났으면
                window = [c for t, c in self._confs_in_roi if now_mono - t <= 0.2]  # 마지막 0.2초 구간
                if not window:
                    window = [self._confs_in_roi[-1][1]]               # 구간이 비면 최신 값 하나라도 사용
                avg_conf = sum(window) / len(window)                   # 구간 평균 conf
                self._publish_state('PARKED', avg_conf)                # PARKED 이벤트 발행
                self._last_event_time = now_wall                       # cooldown 기준 시각 갱신
                self._parked_confirmed = True                          # 이번 체류에서는 다시 발행 안 함
                self._last_state_text = 'PARKED'
            return

        # ---- [갈래 2] ROI 밖에 있음: "PARKED였던 차가 확정적으로 나갔는지" 확인하는 단계.
        if self._current_roi is None:
            # 원래도 ROI 밖이었던 경우(지나가던 차 등) -> 할 일 없음, 그냥 대기.
            self._last_state_text = 'WAITING'
            return

        if not self._parked_confirmed:
            # PARKED로 확정된 적 없는 차가 ROI를 벗어남 -> 애초에 주차한 적이 없으니
            # "출차"라는 개념 자체가 성립하지 않는다. 그냥 조용히 리셋만 한다.
            self._current_roi = None
            self._roi_enter_time = None
            self._confs_in_roi = []
            self._last_state_text = 'WAITING'
            return

        # PARKED였던 차량이 ROI 밖으로 보임 -> 진짜 나간 게 맞는지 0.2초 연속으로
        # 확인한다(아래 elapsed >= 0.2 조건까지). 확인 중 자세히 보면:
        if self._exit_confirm_start is None:
            self._exit_confirm_start = now_mono                        # 확인 시작
            self._exit_confirm_confs = [conf]
        else:
            self._exit_confirm_confs.append(conf)                      # 확인 구간 conf 누적

        elapsed = now_mono - self._exit_confirm_start                  # 확인 시작 후 경과 시간
        self._last_state_text = 'EXITING'
        if elapsed >= 0.2:                                             # 0.2초(CONFIRM_SECONDS) 이상 유지되면 확정
            if now_wall - self._last_event_time >= 2.0:                # 쿨다운(2.0초) 지났을 때만 실제 발행
                avg_conf = sum(self._exit_confirm_confs) / len(self._exit_confirm_confs)
                self._publish_state('EXITING', avg_conf)
                self._last_event_time = now_wall
                self._last_state_text = 'EXITING'
            # 쿨다운으로 발행을 못 했어도 이번 체류 상태는 여기서 전부 리셋한다.
            self._current_roi = None
            self._roi_enter_time = None
            self._confs_in_roi = []
            self._parked_confirmed = False
            self._exit_confirm_start = None
            self._exit_confirm_confs = []

    def _publish_state(self, state: str, confidence: float):
        state_map = {                                                  # 문자열 상태 -> CameraState enum 값 변환표
            'PARKED': CameraState.STATE_PARKED,
            'EXITING': CameraState.STATE_EXITING,
        }
        self._source_sequence += 1                                     # 이번 세션 내 이벤트 순번 증가
        event_id = build_event_id(self._source_session_id, state, self._source_sequence)

        msg = CameraState()
        msg.header.stamp = self.get_clock().now().to_msg()             # 실제 판정(발행) 시각
        msg.event_id = event_id                                        # 구조화 이벤트 id
        msg.camera_id = 'center_cam'                                   # CameraState.camera_id 고정값
        msg.source_session_id = self._source_session_id                # 이번 노드 실행 세션 id
        msg.source_sequence = self._source_sequence                    # 세션 내 순번
        msg.state = state_map[state]                                   # PARKED 또는 EXITING
        msg.confidence = confidence                                    # 확인 구간 평균 conf
        self.publisher_.publish(msg)                                   # 실제 발행
        self.get_logger().info(
            f'[CENTER] state={state} conf={confidence:.2f} event_id={msg.event_id}')

    # 대시보드가 CCTV 화면을 실시간으로 띄울 수 있게 원본 프레임을 JPEG로 압축해 발행한다.
    # 판정용 원본 프레임을 그대로 쓴다(라인·박스 등 디버그용 그림은 안 그린 순수 화면).
    def _publish_image(self, frame):
        ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])  # JPEG 압축(품질 70)
        if not ok:                                                     # 인코딩 실패 시 이번 프레임은 건너뜀
            return
        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()             # 촬영(발행) 시각
        msg.format = 'jpeg'
        msg.data = buf.tobytes()
        self.image_publisher_.publish(msg)

    # ---- 확인용 화면 (항상 표시) ----
    def _debug_draw(self, frame, roi_dict, best_box, best_conf):
        annotated = frame.copy()                                       # 원본 보존을 위해 복사본에 그림
        for roi_name, rect in roi_dict.items():                        # ROI들을 반투명 사각형으로 표시
            x1, y1, x2, y2 = (int(v) for v in rect)
            overlay = annotated.copy()
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 255), -1)
            cv2.addWeighted(overlay, 0.18, annotated, 0.82, 0, annotated)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 255), 2)

        if best_box is not None:                                       # 탐지된 차량 박스가 있으면 표시
            x1, y1, x2, y2 = best_box
            cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            cv2.putText(annotated, f'car {best_conf:.2f}', (int(x1), max(20, int(y1) - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

        cv2.putText(annotated, f'STATE: {self._last_state_text}', (10, 30),           # 현재 상태 문구
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)

        cv2.imshow('center_cam', annotated)                             # 화면에 표시
        cv2.waitKey(1)

def main():
    rclpy.init()                                                        # ROS2 초기화
    node = CenterCam()                                                  # 노드 생성
    try:
        rclpy.spin(node)                                                # 콜백/타이머 반복 실행
    finally:
        node.cap.release()                                              # 카메라 리소스 해제
        cv2.destroyAllWindows()                                         # 디버그 창 정리
        node.destroy_node()                                             # ROS2 노드 정리
        rclpy.shutdown()

if __name__ == '__main__':
    main()