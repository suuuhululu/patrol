#!/usr/bin/env python3
"""Gate CCTV 노드: 입구 차량 ENTERING/EXITED 판정 후 CameraState 발행."""
import time
from collections import deque
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

def crossed(prev_x, curr_x, line_x):
    # 이전 x좌표와 현재 x좌표 사이에 line_x가 끼어 있으면(양방향) 교차로 판정
    return (prev_x < line_x <= curr_x) or (prev_x > line_x >= curr_x)

class GateCam(Node):
    def __init__(self):
        super().__init__('gate_cam')

        self.publisher_ = self.create_publisher(CameraState, '/vision/cctv/gate_event', CCTV_EVENT_QOS)
        self.image_publisher_ = self.create_publisher(                # 대시보드용 영상 스트림 발행자 생성
            CompressedImage, '/vision/cctv/gate_image/compressed', IMAGE_STREAM_QOS)

        self.model = YOLO("/home/hv-06/patrol/data/car_data/car_best_v2.pt")  # YOLO 가중치 경로(설치된 실제 장비 기준)
        self.cap = cv2.VideoCapture(2, cv2.CAP_V4L2)                  # 게이트 카메라 장치 인덱스(설치 완료, 고정값)
        if not self.cap.isOpened():
            self.get_logger().error('camera_source=2 열기 실패')

        restart_sequence = load_and_bump_restart_sequence(            # 이번 실행의 재시작 순번
            'gate_cam', "/home/hv-06/patrol/state")                   # camera_id / 카운터 파일 저장 폴더
        self._source_session_id = build_source_session_id('gate_cam', restart_sequence)  # 이번 실행 세션 id
        self._source_sequence = 0                                     # 이번 세션 내 이벤트 순번(0부터 시작, 발행 시 +1)
        self.get_logger().info(f'gate_cam: source_session_id={self._source_session_id}')

        self._last_cx = None                                          # 직전 프레임의 차량 중심 x좌표
        self._crossing_history = deque(maxlen=2)                      # 최근 라인 교차 순서(L/R) 최대 2개
        self._pending = None                                          # 확정 대기 중인 상태 {'state','side','confs','start_time'}
        self._last_event_time = 0.0                                   # 마지막 이벤트 발행 시각(wall-clock, cooldown용)
        self._last_state_text = 'WAITING'                             # 디버그 화면 표시용 현재 상태 문구

        self._last_ok_read_time = time.time()                         # 마지막으로 프레임 읽기에 성공한 시각
        self._camera_fault = False                                    # 카메라 장애 여부 플래그
        self._image_frame_count = 0                                   # 영상 스트림 발행 주기 조절용(30Hz -> 10Hz)
        self._last_annotated_frame = None                             # ROI 음영+판정선+박스+상태 텍스트가 그려진 최신 프레임(스트림용)

        self.create_timer(1.0 / 30.0, self._process_frame)            # 30Hz로 프레임 처리 반복

    # ---- 프레임 읽기 & 장애 판단 ----
    def _process_frame(self):
        ok, frame = self.cap.read()                                   # 카메라에서 프레임 한 장 읽기
        now = time.time()

        if not ok:                                                    # 읽기 실패한 경우
            self.get_logger().warning('gate_cam: 프레임 읽기 실패')
            if not self._camera_fault and now - self._last_ok_read_time >= 3.0:  # 3초 연속 실패 = 장애 판단 기준
                self._camera_fault = True                             # 3초 연속 실패 시 장애로 확정
                self.get_logger().error(
                    'gate_cam: 3초 연속 프레임 읽기 실패 - 카메라 장애로 판단')
            return                                                    # 이번 tick은 여기서 종료(탐지 안 함)

        self._last_ok_read_time = now                                 # 성공 시각 갱신
        if self._camera_fault:
            self._camera_fault = False                                # 장애 상태였다면 복구 처리
            self.get_logger().info('gate_cam: 카메라 복구됨')

        self._detect_and_track(frame)                                 # 정상 프레임이면 탐지 로직 실행

        # 30Hz 프레임을 그대로 다 보내면 대역폭 낭비라 3프레임마다(약 10Hz) 한 번만
        # 대시보드용으로 압축 발행한다(탐지 판정 자체는 이 주기와 무관하게 매 프레임 실행됨).
        self._image_frame_count += 1
        if self._image_frame_count % 3 == 0:
            self._publish_image()

    # ---- 탐지: 이번 프레임에서 conf가 가장 높은 박스 1개만 사용 ----
    def _detect_and_track(self, frame):
        h, w = frame.shape[:2]                                        # 프레임 크기
        roi_top = h * 0.45                                            # 판정 영역 상단(프레임 높이의 45% 지점, 설치 기준 확정값)
        roi_bottom = h * 0.95                                         # 판정 영역 하단(프레임 높이의 95% 지점, 설치 기준 확정값)
        left_x = w * 0.32                                             # 왼쪽 판정선(프레임 폭의 32% 지점, 설치 기준 확정값)
        right_x = w * 0.70                                            # 오른쪽 판정선(프레임 폭의 70% 지점, 설치 기준 확정값)

        results = self.model.predict(                                 # YOLO 추론 실행
            frame,
            imgsz=512,          # YOLO 추론 입력 크기
            conf=0.7,           # YOLO 자체 conf 임계값(이 값 미만 박스는 애초에 안 나옴)
            classes=[0],         # 탐지할 클래스 id(차량)
            verbose=False,
        )
        result = results[0]                                           # 프레임 1장 결과

        best_box = None                                               # 최종 선택된 박스(디버그 표시용)
        best_cx = None                                                # 최종 선택된 박스의 중심 x
        best_conf = -1.0                                              # 지금까지 찾은 최고 conf
        if result.boxes is not None and len(result.boxes) > 0:
            boxes = result.boxes.xyxy.cpu().numpy()                   # 박스 좌표 배열
            confs = result.boxes.conf.cpu().numpy()                   # 박스별 conf 배열
            for box, conf in zip(boxes, confs):
                x1, y1, x2, y2 = box
                cx = (x1 + x2) / 2                                    # 박스 중심 x
                cy = (y1 + y2) / 2                                    # 박스 중심 y
                if not (0 <= cx <= w and roi_top <= cy <= roi_bottom):
                    continue                                          # 판정 영역 밖 박스는 무시
                if conf > best_conf:                                  # 영역 안 박스 중 conf 최고값 갱신
                    best_conf = float(conf)
                    best_cx = cx
                    best_box = box

        if best_cx is None:                                           # 영역 안에 탐지된 차량이 없으면
            self._on_no_detection()
        else:                                                         # 있으면 위치·conf로 상태 판정
            self._on_detection(w, best_cx, best_conf)

        self._debug_draw(frame, left_x, right_x, roi_top, roi_bottom, best_box, best_conf)

    # YOLO가 이번 프레임에서 판정 영역 안에 차량을 하나도 못 찾았을 때 호출된다.
    # 확정 대기(pending) 중이 아니면 할 일이 없다(원래도 대기 상태였을 뿐).
    # 확정 대기 중이었다면, 차량을 놓쳤다는 뜻이므로 지금까지 쌓아온 대기 상태를
    # 전부 버리고 처음(WAITING)부터 다시 시작한다 - 잠깐 가려졌다고 봐주지 않는다.
    def _on_no_detection(self):
        # 확정 대기(pending) 중에 미검출이 오면 즉시 취소(가려짐 관용 없음)
        if self._pending is not None:
            self._pending = None                                      # 대기 상태 초기화
            self._crossing_history.clear()                            # 교차 이력도 초기화
            self._last_state_text = 'WAITING'

    # "차가 들어왔다/나갔다"를 판정하는 핵심 함수. 크게 두 갈래로 나뉜다:
    # self._pending이 없으면(아직 대기 중인 판정이 없으면) 아래쪽 "선 교차 감지" 코드로 가고,
    # self._pending이 있으면(방금 선을 넘어서 확정 대기 중이면) 바로 아래 if문에서 확정 여부만 본다.
    def _on_detection(self, w, cx, conf):
        left_x = w * 0.32                                             # 왼쪽 판정선(프레임 폭의 32% 지점)
        right_x = w * 0.70                                            # 오른쪽 판정선(프레임 폭의 70% 지점)
        prev_cx = self._last_cx                                       # 직전 프레임 위치 저장해두고
        self._last_cx = cx                                            # 이번 프레임 위치로 갱신
        now = time.monotonic()                                        # 0.2초 확정 판단은 monotonic 기준

        # ---- [갈래 1] 확정 대기 중(self._pending 있음): 아래 "선 교차 감지"는 이미 끝났고,
        # 지금은 "그 방향에 0.2초간 안정적으로 머무는지"만 확인하는 단계다. 여기서 바로
        # return하기 때문에, 대기 중일 때는 밑에 있는 교차 감지 코드가 실행되지 않는다.
        if self._pending is not None:
            side = self._pending['side']                              # 확정에 필요한 목표 방향(left/right)
            consistent = (cx > right_x) if side == 'right' else (cx < left_x)  # 계속 그 방향에 있는지
            if consistent:
                # 아직 그 방향에 잘 있음 -> conf 누적하고 0.2초 다 채웠는지만 확인
                self._pending['confs'].append(conf)                   # 평균 계산용 conf 누적
                elapsed = now - self._pending['start_time']            # 대기 시작 후 경과 시간
                self._last_state_text = self._pending['state']         # 확정 대기 중에도 목표 상태 표시
                if elapsed >= 0.2:                                     # 0.2초(CONFIRM_SECONDS) 다 채웠으면 확정 발행
                    avg_conf = sum(self._pending['confs']) / len(self._pending['confs'])  # 구간 평균 conf
                    self._publish_state(self._pending['state'], avg_conf)  # 이벤트 발행
                    self._last_event_time = time.time()                # cooldown 기준 시각 갱신
                    self._last_state_text = self._pending['state']
                    self._pending = None                                # 대기 상태 종료
                    self._crossing_history.clear()                     # 다음 판정을 위해 이력 초기화
            else:
                # 차가 다시 반대 방향으로 돌아감(오탐 or 유턴) -> 0.2초를 다 못 채웠으니
                # 지금까지 쌓은 대기 상태를 버리고 WAITING으로 되돌아간다. 봐주는 여지 없음.
                self._pending = None
                self._crossing_history.clear()
                self._last_state_text = 'WAITING'
            return                                                     # 대기 중이었으면 아래 교차 판정은 스킵

        # ---- [갈래 2] 확정 대기 중이 아님: 이번 프레임에서 선을 "막 넘었는지"부터 확인한다.
        if prev_cx is None:                                            # 첫 프레임(비교할 직전 위치가 없음)이면 대기
            return

        wall_now = time.time()
        if wall_now - self._last_event_time < 2.0:                     # 방금 이벤트 쐈으면(쿨다운 2.0초 중) 새 판정 시작 안 함
            return

        # 이번 프레임에서 왼쪽/오른쪽 선을 넘었으면 순서대로 기록해둔다(deque maxlen=2라
        # 최근 2개만 남음). 예: 왼쪽 선 넘고 → 오른쪽 선 넘으면 history=['L','R'] = 입차 방향.
        if crossed(prev_cx, cx, left_x) and 'L' not in self._crossing_history:
            self._crossing_history.append('L')                        # 왼쪽 선 교차 기록
        if crossed(prev_cx, cx, right_x) and 'R' not in self._crossing_history:
            self._crossing_history.append('R')                        # 오른쪽 선 교차 기록

        seq = list(self._crossing_history)
        if len(seq) >= 2:
            # 두 선을 순서대로 다 넘었다 = 방향이 확정됐다 -> 이제 그 방향에 0.2초간
            # 안정적으로 머무는지 확인하는 대기 상태(self._pending)를 시작한다.
            # (다음 프레임부터는 위쪽 "[갈래 1]"이 실행돼서 이 코드는 다시 안 타게 된다.)
            if seq[-2:] == ['L', 'R']:                                 # 왼쪽→오른쪽 순서 완성 = 입차 방향
                self._pending = {'state': 'ENTERING', 'side': 'right', 'confs': [conf], 'start_time': now}
            elif seq[-2:] == ['R', 'L']:                               # 오른쪽→왼쪽 순서 완성 = 출차 방향
                self._pending = {'state': 'EXITED', 'side': 'left', 'confs': [conf], 'start_time': now}

    def _publish_state(self, state: str, confidence: float):
        state_map = {                                                  # 문자열 상태 -> CameraState enum 값 변환표
            'ENTERING': CameraState.STATE_ENTERING,
            'EXITED': CameraState.STATE_EXITED,
        }
        self._source_sequence += 1                                    # 이번 세션 내 이벤트 순번 증가
        event_id = build_event_id(self._source_session_id, state, self._source_sequence)

        msg = CameraState()
        msg.header.stamp = self.get_clock().now().to_msg()            # 실제 판정(발행) 시각
        msg.event_id = event_id                                       # 구조화 이벤트 id
        msg.camera_id = 'gate_cam'                                    # CameraState.camera_id 고정값
        msg.source_session_id = self._source_session_id               # 이번 노드 실행 세션 id
        msg.source_sequence = self._source_sequence                   # 세션 내 순번
        msg.state = state_map[state]                                  # ENTERING 또는 EXITED
        msg.confidence = confidence                                   # 0.2초 확인 구간 평균 conf
        self.publisher_.publish(msg)                                  # 실제 발행
        self.get_logger().info(
            f'[GATE] state={state} conf={confidence:.2f} event_id={msg.event_id}')

    # 대시보드가 CCTV 화면을 실시간으로 띄울 수 있게 프레임을 JPEG로 압축해 발행한다.
    # _debug_draw가 그린 ROI 음영+판정선+박스+상태 텍스트 화면을 그대로 재사용한다(로컬 디버그창과 동일 화면).
    def _publish_image(self):
        if self._last_annotated_frame is None:                       # 아직 한 번도 탐지 로직이 안 돌았으면 스킵
            return
        ok, buf = cv2.imencode(
            '.jpg', self._last_annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])  # JPEG 압축(품질 70)
        if not ok:                                                    # 인코딩 실패 시 이번 프레임은 건너뜀
            return
        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()            # 촬영(발행) 시각
        msg.format = 'jpeg'
        msg.data = buf.tobytes()
        self.image_publisher_.publish(msg)

    # ---- 확인용 화면 (항상 표시) ----
    def _debug_draw(self, frame, left_x, right_x, roi_top, roi_bottom, best_box, best_conf):
        annotated = frame.copy()                                      # 원본 보존을 위해 복사본에 그림
        overlay = annotated.copy()
        cv2.rectangle(overlay, (0, int(roi_top)), (frame.shape[1], int(roi_bottom)), (70, 70, 70), -1)
        annotated = cv2.addWeighted(overlay, 0.18, annotated, 0.82, 0)  # 판정 영역 반투명 표시

        cv2.line(annotated, (int(left_x), int(roi_top)), (int(left_x), int(roi_bottom)), (255, 0, 0), 2)   # 왼쪽 라인
        cv2.line(annotated, (int(right_x), int(roi_top)), (int(right_x), int(roi_bottom)), (0, 255, 255), 2)  # 오른쪽 라인

        if best_box is not None:                                      # 탐지된 차량 박스가 있으면 표시
            x1, y1, x2, y2 = best_box
            cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            cv2.putText(annotated, f'car {best_conf:.2f}', (int(x1), max(20, int(y1) - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

        cv2.putText(annotated, f'STATE: {self._last_state_text}', (10, 30),          # 현재 상태 문구
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)

        self._last_annotated_frame = annotated                        # 대시보드 스트림용으로 재사용할 수 있게 저장
        cv2.imshow('gate_cam', annotated)                             # 화면에 표시
        cv2.waitKey(1)

def main():
    rclpy.init()                                                      # ROS2 초기화
    node = GateCam()                                                  # 노드 생성
    try:
        rclpy.spin(node)                                              # 콜백/타이머 반복 실행
    finally:
        node.cap.release()                                            # 카메라 리소스 해제
        cv2.destroyAllWindows()                                       # 디버그 창 정리
        node.destroy_node()                                           # ROS2 노드 정리
        rclpy.shutdown()

if __name__ == '__main__':
    main()