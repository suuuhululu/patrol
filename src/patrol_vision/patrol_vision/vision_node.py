#!/usr/bin/env python3  # 이 파일을 Python3로 실행하도록 지정
# 핵심 내용: YOLO 모델로 이벤트 후보를 찾고, AMR 정렬 완료 후 1초 검증을 거쳐 최종 DetectionEvent 발행

from collections import defaultdict, deque  # 이벤트 해시 저장용 defaultdict, 최근 검출 시각 저장용 deque
from datetime import datetime  # 세션 ID에 현재 시각을 넣기 위해 사용
from enum import IntEnum  # 비전 노드 상태를 숫자 enum으로 관리하기 위해 사용
from pathlib import Path  # YOLO 모델 파일 경로를 안전하게 만들기 위해 사용
import time  # 후보/검증 시간 계산에 monotonic 시간을 사용

import cv2  # 이미지 디코딩, bbox 그리기, JPEG 압축, 화면 표시
import numpy as np  # ROS 이미지 byte 데이터를 OpenCV 배열로 변환
import rclpy  # ROS2 Python 클라이언트 라이브러리
from rclpy.node import Node  # ROS2 노드 클래스를 만들기 위한 기본 클래스
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy  # ROS2 QoS 설정
from sensor_msgs.msg import CompressedImage  # OAK-D 압축 영상과 최종 JPEG 증적 이미지 타입
from ultralytics import YOLO  # 학습한 YOLO 모델 로드 및 추론

from patrol_interfaces.msg import AlignmentStatus, DetectionCandidate, DetectionEvent  # 프로젝트 공용 메시지 타입


ROBOT_ID = "robot6"  # 이 비전 노드가 담당하는 로봇 ID

CAMERA_TOPIC = "/robot6/oakd/rgb/image_raw/compressed"  # OAK-D RGB 압축 영상 Subscribe 토픽
CANDIDATE_TOPIC = "/robot6/vision/detection_candidate"  # 비전 -> AMR Candidate Publish 토픽
ALIGNMENT_TOPIC = "/robot6/vision/alignment_status"  # AMR -> 비전 정렬 상태 Subscribe 토픽
EVENT_TOPIC = "/robot6/vision/detection_event"  # 최종 확정 이벤트 Publish 토픽

MODEL_PATH = Path(__file__).resolve().parent / "detection_best.pt"  # 현재 코드와 같은 폴더의 YOLO 모델 경로

YOLO_CONFIDENCE = 0.70  # YOLO confidence가 0.70 이상인 bbox만 유효 검출로 사용
YOLO_IMAGE_SIZE = 704  # YOLO 추론 입력 이미지 크기

CANDIDATE_WINDOW_SEC = 0.30  # Candidate 판정에 사용하는 최근 시간 창: 0.3초
CANDIDATE_MIN_HITS = 2  # 최근 0.3초 안에 최소 2회 검출되면 Candidate 확정
CANDIDATE_LOST_SEC = 0.60  # 대상이 0.6초 이상 안 보이면 현재 Candidate를 버림

VERIFY_DURATION_SEC = 1.00  # AMR 정렬 완료 후 최종 검증 시간: 1초
VERIFY_MAX_FRAME_GAP_SEC = 0.30  # 검증 중 프레임 간격이 0.3초 이상 벌어지면 연속 검증 실패

DEDUP_HASH_DISTANCE = 10  # dHash 차이가 10 이하이면 이전에 본 것과 유사한 이벤트로 판정


class VisionState(IntEnum):  # 비전 노드의 현재 단계 정의
    SEARCHING = 0  # 이벤트 후보를 찾는 중
    WAITING_ALIGNMENT = 1  # Candidate 확정 후 AMR 정렬 완료를 기다리는 중
    VERIFYING = 2  # 정렬 완료 후 1초 최종 검증 중
    DUPLICATE_SUPPRESSED = 3  # 이미 처리한 이벤트라 재발행을 막는 중


EVENT_TYPE = {  # YOLO class 이름을 DetectionEvent enum 값으로 변환
    "fire": DetectionEvent.FIRE,  # fire class -> FIRE enum
    "leak": DetectionEvent.LEAK,  # leak class -> LEAK enum
    "obstacle": DetectionEvent.OBSTACLE,  # obstacle class -> OBSTACLE enum
}

STATE_TEXT = {  # OpenCV 화면 좌측 상단에 보여줄 상태 문자열
    VisionState.SEARCHING: "SEARCHING",  # 탐색 중 표시
    VisionState.WAITING_ALIGNMENT: "WAITING ALIGNMENT",  # AMR 정렬 대기 표시
    VisionState.VERIFYING: "VERIFYING",  # 최종 검증 중 표시
    VisionState.DUPLICATE_SUPPRESSED: "DUPLICATE SUPPRESSED",  # 중복 억제 중 표시
}


def crop_dhash(frame, bbox):  # bbox 영역의 시각적 특징을 64-bit dHash로 만드는 함수
    if frame is None or bbox is None:  # 이미지나 bbox가 없으면
        return None  # 해시를 만들 수 없으므로 종료

    x1, y1, x2, y2 = bbox  # bbox 좌상단/우하단 좌표를 분리
    h, w = frame.shape[:2]  # 현재 이미지 높이와 너비를 가져옴
    x1 = max(0, min(w - 1, int(x1)))  # x1이 이미지 범위를 벗어나지 않도록 제한
    y1 = max(0, min(h - 1, int(y1)))  # y1이 이미지 범위를 벗어나지 않도록 제한
    x2 = max(0, min(w, int(x2)))  # x2가 이미지 범위를 벗어나지 않도록 제한
    y2 = max(0, min(h, int(y2)))  # y2가 이미지 범위를 벗어나지 않도록 제한

    if x2 <= x1 or y2 <= y1:  # bbox 넓이나 높이가 잘못된 경우
        return None  # 잘못된 bbox이므로 해시 생성 중단

    crop = frame[y1:y2, x1:x2]  # 원본 이미지에서 bbox 영역만 잘라냄
    if crop.size == 0:  # 잘라낸 이미지가 비어 있으면
        return None  # 해시 생성 중단

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)  # 색상 정보를 제거하고 grayscale로 변환
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)  # dHash 계산용으로 9x8 크기로 축소
    bits = small[:, 1:] > small[:, :-1]  # 인접 픽셀 밝기를 비교해 True/False 패턴 생성

    value = 0  # 최종 64-bit 정수 해시 초기값
    for bit in bits.flatten():  # 8x8 = 64개의 bool 값을 순서대로 읽음
        value = (value << 1) | int(bit)  # bit를 하나씩 붙여 하나의 정수 해시로 만듦
    return value  # 계산된 dHash 반환


class DetectingNode(Node):  # ROS2 메인 비전 노드 클래스
    def __init__(self):  # 노드 생성 시 한 번 실행되는 초기화 함수
        super().__init__("detecting_node")  # ROS2 노드 이름을 detecting_node로 생성

        if not MODEL_PATH.is_file():  # YOLO 모델 파일이 실제로 존재하는지 확인
            raise FileNotFoundError(f"Model not found: {MODEL_PATH}")  # 없으면 즉시 오류를 내고 종료

        best_effort = QoSProfile(  # 카메라/Candidate용 QoS 생성
            history=HistoryPolicy.KEEP_LAST,  # 최근 메시지만 보관
            depth=1,  # 가장 최신 메시지 1개만 유지
            reliability=ReliabilityPolicy.BEST_EFFORT,  # 손실 가능하지만 최신성 우선
            durability=DurabilityPolicy.VOLATILE,  # 늦게 들어온 subscriber에게 과거 메시지를 재전송하지 않음
        )
        reliable = QoSProfile(  # Alignment/Event용 QoS 생성
            history=HistoryPolicy.KEEP_LAST,  # 최근 메시지들만 보관
            depth=10,  # 최근 메시지 최대 10개 유지
            reliability=ReliabilityPolicy.RELIABLE,  # 중요한 상태/결과이므로 신뢰성 있게 전달
            durability=DurabilityPolicy.VOLATILE,  # 과거 메시지는 저장하지 않음
        )

        self.model = YOLO(str(MODEL_PATH))  # 학습한 YOLO 모델을 메모리에 한 번 로드
        self.session_id = f"{ROBOT_ID}-{datetime.now().strftime('%Y%m%dT%H%M%S')}"  # 노드 실행마다 고유 세션 ID 생성
        self.candidate_sequence = 0  # Candidate ID 증가용 번호 초기화
        self.event_sequence = 0  # 최종 Event ID 증가용 번호 초기화
        self.hits = deque()  # 최근 Candidate 검출 시각들을 저장
        self.verify_confidences = []  # 1초 Verification 동안 confidence들을 저장
        self.confirmed_hashes = defaultdict(list)  # event_type별 확정 이벤트 dHash 목록 저장
        self.reset_candidate()  # 현재 Candidate 관련 상태를 초기값으로 설정

        self.image_sub = self.create_subscription(  # OAK-D 영상 subscriber 생성
            CompressedImage, CAMERA_TOPIC, self.image_callback, best_effort  # 압축 영상을 image_callback으로 전달
        )
        self.candidate_pub = self.create_publisher(  # DetectionCandidate publisher 생성
            DetectionCandidate, CANDIDATE_TOPIC, best_effort  # 최신 horizontal_error를 AMR에 전달
        )
        self.alignment_sub = self.create_subscription(  # AlignmentStatus subscriber 생성
            AlignmentStatus, ALIGNMENT_TOPIC, self.alignment_callback, reliable  # AMR 정렬 상태를 callback으로 전달
        )
        self.event_pub = self.create_publisher(  # 최종 DetectionEvent publisher 생성
            DetectionEvent, EVENT_TOPIC, reliable  # 확정 이벤트 + JPEG 이미지를 발행
        )

        self.get_logger().info(  # 비전 노드 시작 상태를 터미널에 표시
            f"Vision READY | robot={ROBOT_ID} | classes={self.model.names}"  # 담당 로봇과 YOLO class 출력
        )
        self.get_logger().info(f"Candidate TX: {CANDIDATE_TOPIC}")  # Candidate 발행 토픽 출력
        self.get_logger().info(f"Alignment RX: {ALIGNMENT_TOPIC}")  # Alignment 수신 토픽 출력
        self.get_logger().info(f"Event TX: {EVENT_TOPIC}")  # 최종 Event 발행 토픽 출력

    def reset_candidate(self):  # 현재 Candidate 상태만 초기화하는 함수
        self.state = VisionState.SEARCHING  # 다시 새로운 이벤트 탐색 상태로 변경
        self.candidate_id = None  # 현재 Candidate ID 제거
        self.class_name = None  # 현재 추적 class 제거
        self.bbox = None  # 현재 bbox 제거
        self.last_seen = 0.0  # 마지막 검출 시각 초기화
        self.verify_start = 0.0  # Verification 시작 시각 초기화
        self.verify_last_frame = 0.0  # Verification 마지막 프레임 시각 초기화
        self.hits.clear()  # Candidate 검출 시각 기록 비움
        self.verify_confidences.clear()  # Verification confidence 기록 비움

    def start_candidate(self, detection, now):  # 새로운 대상 추적을 시작하는 함수
        self.candidate_sequence += 1  # Candidate 번호 1 증가
        self.candidate_id = (  # 새로운 Candidate ID 생성
            f"cand-{self.session_id}-{self.candidate_sequence:06d}"  # 세션 ID + 순번으로 고유 ID 구성
        )
        self.class_name, _, self.bbox = detection  # class와 bbox를 현재 추적 대상으로 저장하고 confidence는 여기선 사용하지 않음
        self.last_seen = now  # 방금 본 시간을 마지막 검출 시각으로 저장
        self.hits.clear()  # 이전 hit 기록 제거
        self.hits.append(now)  # 첫 번째 검출 시각 저장

    def image_callback(self, image_msg):  # OAK-D 영상이 들어올 때마다 실행되는 핵심 함수
        now = time.monotonic()  # 시스템 시간 변경 영향이 없는 경과시간용 현재 시각

        try:  # 영상 처리 중 오류가 나도 노드 전체가 바로 죽지 않도록 예외 처리
            frame = cv2.imdecode(  # ROS 압축 이미지를 OpenCV 이미지로 디코딩
                np.frombuffer(image_msg.data, dtype=np.uint8),  # byte 배열을 numpy uint8 배열로 변환
                cv2.IMREAD_COLOR,  # 컬러 이미지로 읽기
            )
            if frame is None:  # JPEG 디코딩에 실패하면
                return  # 해당 프레임만 버림

            result = self.model.predict(  # 현재 프레임에 YOLO 추론 수행
                source=frame,  # 입력 영상
                conf=YOLO_CONFIDENCE,  # confidence 0.70 이상만 결과로 사용
                imgsz=YOLO_IMAGE_SIZE,  # 추론 입력 크기 704
                verbose=False,  # YOLO 자체 로그 출력 최소화
            )[0]  # 첫 번째 추론 결과 사용

            detection = self.select_detection(result)  # 여러 bbox 중 지금 추적할 대상 하나 선택

            if self.state == VisionState.VERIFYING:  # 현재 1초 최종 검증 상태라면
                self.update_verification(detection, frame, image_msg, now)  # Verification 로직 수행
            else:  # SEARCHING / WAITING_ALIGNMENT / DUPLICATE 상태라면
                self.update_candidate(detection, frame, image_msg, now)  # Candidate 탐색/추적 로직 수행

            display = result.plot()  # YOLO bbox와 class가 그려진 디버깅 이미지 생성
            cv2.putText(  # 현재 비전 상태를 디버깅 화면에 표시
                display,  # 표시할 이미지
                STATE_TEXT[self.state],  # 현재 상태 문자열
                (10, 30),  # 표시 위치
                cv2.FONT_HERSHEY_SIMPLEX,  # 폰트
                0.7,  # 글자 크기
                (255, 255, 255),  # 흰색
                2,  # 글자 두께
            )
            cv2.imshow("AMR Vision", display)  # AMR Vision 디버깅 창에 표시

            if cv2.waitKey(1) & 0xFF == ord("q"):  # 사용자가 q를 누르면
                rclpy.shutdown()  # ROS2 종료 시작

        except Exception as error:  # 처리 중 예외가 발생하면
            self.get_logger().error(f"Vision error: {error}")  # 에러 내용을 로그로 출력

    def select_detection(self, result):  # 현재 추적할 YOLO detection 하나를 고르는 함수
        detections = []  # 사용 가능한 detection 목록

        if result.boxes is not None:  # YOLO bbox 결과가 존재하면
            for box in result.boxes:  # 검출된 bbox를 하나씩 확인
                class_id = int(box.cls[0])  # YOLO class 번호 추출
                class_name = str(self.model.names[class_id]).strip().lower()  # class 번호를 fire/leak/... 문자열로 변환

                if class_name not in EVENT_TYPE:  # 프로젝트에서 처리하지 않는 class이면
                    continue  # 해당 bbox 무시

                confidence = float(box.conf[0])  # bbox confidence 값 추출
                bbox = tuple(int(v) for v in box.xyxy[0].tolist())  # bbox를 (x1,y1,x2,y2) 정수 좌표로 변환
                detections.append((class_name, confidence, bbox))  # 처리 가능한 detection 목록에 추가

        if not detections:  # 유효 detection이 하나도 없으면
            return None  # 현재 프레임에 대상 없음

        if self.class_name is None:  # 아직 추적 중인 Candidate가 없다면
            return max(detections, key=lambda item: item[1])  # confidence가 가장 높은 객체를 선택

        same_class = [d for d in detections if d[0] == self.class_name]  # 현재 추적 class와 같은 detection만 추림
        if not same_class:  # 같은 class가 하나도 없으면
            return None  # 현재 추적 대상이 사라진 것으로 처리

        if self.bbox is None:  # 이전 bbox가 없는 예외 상황이면
            return max(same_class, key=lambda item: item[1])  # 같은 class 중 confidence 최고 객체 선택

        old_x1, old_y1, old_x2, old_y2 = self.bbox  # 이전 bbox 좌표 읽기
        old_cx = (old_x1 + old_x2) / 2.0  # 이전 bbox 중심 x 계산
        old_cy = (old_y1 + old_y2) / 2.0  # 이전 bbox 중심 y 계산

        def distance(item):  # 새 bbox와 이전 bbox 중심 간 거리를 계산하는 내부 함수
            x1, y1, x2, y2 = item[2]  # 새 bbox 좌표
            cx = (x1 + x2) / 2.0  # 새 bbox 중심 x
            cy = (y1 + y2) / 2.0  # 새 bbox 중심 y
            return (cx - old_cx) ** 2 + (cy - old_cy) ** 2  # 제곱거리 반환; sqrt는 비교에 필요 없어서 생략

        return min(same_class, key=distance)  # 이전 bbox 중심과 가장 가까운 같은 class 객체를 계속 추적

    def update_candidate(self, detection, frame, image_msg, now):  # Candidate 생성/유지/발행을 담당
        if detection is None:  # 현재 프레임에서 추적 대상이 안 보이면
            if (  # Candidate LOST 조건 확인
                self.candidate_id is not None  # 기존에 추적 중인 Candidate가 있고
                and now - self.last_seen > CANDIDATE_LOST_SEC  # 마지막 검출 후 0.6초가 지났다면
            ):
                if self.state == VisionState.DUPLICATE_SUPPRESSED:  # 중복 이벤트를 무시하던 상태였다면
                    self.get_logger().info(  # 중복 대상이 화면에서 사라졌다고 로그 출력
                        f"Duplicate target left view | type={self.class_name}"  # 어떤 class였는지 표시
                    )
                else:  # 일반 Candidate였다면
                    self.get_logger().info(  # Candidate LOST 로그 출력
                        f"Candidate LOST | id={self.candidate_id}"  # 사라진 Candidate ID 표시
                    )
                self.reset_candidate()  # 다시 SEARCHING으로 복귀
            return  # 현재 프레임 처리를 종료

        if self.candidate_id is None:  # 아직 Candidate 추적을 시작하지 않았다면
            self.start_candidate(detection, now)  # 새 Candidate 추적 시작
        else:  # 이미 Candidate를 추적 중이면
            self.class_name, _, self.bbox = detection  # 최신 class/bbox로 갱신
            self.last_seen = now  # 마지막 검출 시각 갱신
            self.hits.append(now)  # 현재 검출 시각을 Candidate hit 기록에 추가

        if self.state == VisionState.DUPLICATE_SUPPRESSED:  # 이미 처리한 이벤트로 판정된 상태라면
            return  # 대상이 화면에서 사라질 때까지 아무것도 발행하지 않음

        while self.hits and now - self.hits[0] > CANDIDATE_WINDOW_SEC:  # 0.3초보다 오래된 hit가 남아 있는 동안
            self.hits.popleft()  # 가장 오래된 hit부터 제거

#########################################################################핵심내용 - 이벤트 감지
        if (  # Candidate 확정 조건
            self.state == VisionState.SEARCHING  # 아직 탐색 상태이고
            and len(self.hits) >= CANDIDATE_MIN_HITS  # 최근 0.3초 안에 2회 이상 검출됐다면
        ):
            if self.is_duplicate(frame, self.bbox, self.class_name):  # 이전에 확정한 유사 이벤트인지 검사
                self.state = VisionState.DUPLICATE_SUPPRESSED  # 중복 억제 상태로 변경
                self.get_logger().info(  # 중복 억제 로그 출력
                    f"Duplicate candidate suppressed | type={self.class_name}"  # 중복된 class 표시
                )
                return  # Candidate 발행하지 않고 종료

            self.state = VisionState.WAITING_ALIGNMENT  # 새로운 Candidate이므로 AMR 정렬 대기 상태로 변경
            self.get_logger().info(  # Candidate 확정 로그 출력
                f"Candidate ACQUIRED | id={self.candidate_id} | "  # Candidate ID
                f"type={self.class_name}"  # Candidate class
            )
#########################################################################핵심내용

        if self.state == VisionState.WAITING_ALIGNMENT:  # AMR 정렬을 기다리는 동안
            self.publish_candidate(frame, image_msg)  # 최신 horizontal_error를 매 프레임 계속 발행

    def publish_candidate(self, frame, image_msg):  # DetectionCandidate 메시지를 만들어 AMR에 발행
        _, width = frame.shape[:2]  # 이미지 너비 읽기
        x1, _, x2, _ = self.bbox  # 현재 bbox의 x 좌표만 사용
        horizontal_error = (((x1 + x2) / 2.0) - width / 2.0) / (width / 2.0)  # bbox 중심과 화면 중심의 정규화 오차 계산

        msg = DetectionCandidate()  # DetectionCandidate 메시지 객체 생성
        msg.header = image_msg.header  # 원본 카메라 프레임의 timestamp/frame_id 사용
        msg.robot_id = ROBOT_ID  # 어떤 로봇의 Candidate인지 기록
        msg.candidate_id = self.candidate_id  # 현재 Candidate ID 기록
        msg.horizontal_error = float(horizontal_error)  # AMR yaw 정렬에 사용할 좌우 오차 기록
        self.candidate_pub.publish(msg)  # /robot6/vision/detection_candidate 발행

    def alignment_callback(self, msg):  # AMR의 AlignmentStatus가 들어올 때마다 실행
        if msg.robot_id != ROBOT_ID or self.candidate_id is None:  # 다른 로봇 메시지거나 현재 Candidate가 없으면
            return  # 처리하지 않음

        if msg.candidate_id != self.candidate_id:  # AMR이 돌려준 Candidate ID가 현재 ID와 다르면
            self.get_logger().warning(  # ID mismatch 경고
                f"Alignment ID mismatch | current={self.candidate_id} | "  # 비전이 현재 기다리는 ID
                f"received={msg.candidate_id}"  # AMR에서 받은 ID
            )
            return  # 다른 Candidate 결과이므로 무시

        if msg.state == AlignmentStatus.ALIGNING:  # AMR이 아직 정렬 중이면
            return  # 비전은 아무것도 하지 않고 기다림

        if msg.state == AlignmentStatus.ALIGNED_COMPLETE:  # AMR 정렬이 완료됐으면
            if self.state == VisionState.WAITING_ALIGNMENT:  # 비전도 해당 정렬 결과를 기다리던 상태인지 확인
                self.start_verification()  # 1초 최종 검증 시작
            return  # callback 종료

        if msg.state == AlignmentStatus.FAILED:  # AMR 정렬 자체가 실패했으면
            self.get_logger().warning(  # 실패 로그 출력
                f"Alignment FAILED | id={self.candidate_id}"  # 실패한 Candidate ID 표시
            )
            self.reset_candidate()  # Candidate 폐기 후 다시 탐색
            return  # callback 종료

        if msg.state == AlignmentStatus.SAFETY_ABORTED:  # 안전 문제로 AMR이 정렬을 중단했으면
            self.get_logger().warning(  # 안전 중단 로그 출력
                f"Alignment SAFETY ABORTED | id={self.candidate_id}"  # 해당 Candidate ID 표시
            )
            self.reset_candidate()  # Candidate 폐기 후 다시 탐색
            return  # callback 종료

        self.get_logger().warning(f"Unknown AlignmentStatus state: {msg.state}")  # 정의하지 않은 state가 오면 경고

    def start_verification(self):  # ALIGNED_COMPLETE 수신 직후 1초 검증을 시작
        now = time.monotonic()  # 검증 시작 기준 시각
        self.state = VisionState.VERIFYING  # 상태를 VERIFYING으로 변경
        self.verify_start = now  # 1초 측정을 위한 시작 시각 저장
        self.verify_last_frame = now  # 첫 프레임 기준 시각 저장
        self.verify_confidences.clear()  # 이전 confidence 기록 제거

        self.get_logger().info(f"Alignment COMPLETE | id={self.candidate_id}")  # 정렬 완료 로그
        self.get_logger().info(  # 최종 검증 시작 로그
            f"Verification START | duration={VERIFY_DURATION_SEC:.1f} sec"  # 검증 시간 표시
        )

    def update_verification(self, detection, frame, image_msg, now):  # VERIFYING 상태에서 매 프레임 호출
        if now - self.verify_last_frame > VERIFY_MAX_FRAME_GAP_SEC:  # 이전 프레임 이후 0.3초 이상 비었다면
            self.fail_verification("frame_gap")  # 연속 영상이 아니므로 검증 실패
            return  # 현재 처리 종료

        self.verify_last_frame = now  # 정상 프레임이 들어왔으므로 마지막 프레임 시각 갱신

        if detection is None:  # 유효 detection이 사라졌다면
            self.fail_verification("detection_lost_or_low_confidence")  # bbox 소실 또는 confidence 미달로 실패
            return  # 처리 종료

        class_name, confidence, bbox = detection  # 현재 detection 값 분리
        if class_name != self.class_name:  # 기존 Candidate와 다른 class가 잡히면
            self.fail_verification("event_changed")  # 이벤트가 바뀌었다고 판단하고 실패
            return  # 처리 종료

        self.bbox = bbox  # 최신 bbox 갱신
        self.last_seen = now  # 마지막 검출 시각 갱신
        self.verify_confidences.append(confidence)  # 평균 confidence 계산을 위해 값 누적

#########################################################################핵심내용 - 이벤트 확정
        if now - self.verify_start < VERIFY_DURATION_SEC:  # 아직 1초가 지나지 않았다면
            return  # 다음 프레임까지 계속 검증

        if self.is_duplicate(frame, bbox, class_name):  # 1초 검증까지 성공했지만 이미 본 이벤트인지 다시 검사
            self.get_logger().info(  # 중복 이벤트 로그 출력
                f"Duplicate event suppressed | type={class_name}"  # 중복 class 표시
            )
            self.reset_candidate()  # 재발행하지 않고 다시 SEARCHING으로 복귀
            return  # 처리 종료

        avg_conf = sum(self.verify_confidences) / len(self.verify_confidences)  # 1초 동안의 평균 confidence 계산
        self.finish_verification(frame, image_msg, avg_conf)  # 최종 Event + JPEG 생성 및 발행
#########################################################################핵심내용

    def fail_verification(self, reason):  # 1초 검증 실패 공통 처리 함수
        self.get_logger().warning(  # 실패 원인을 로그로 출력
            f"Verification FAILED | id={self.candidate_id} | reason={reason}"  # Candidate ID와 실패 이유 표시
        )
        self.reset_candidate()  # 실패 Candidate를 버리고 다시 탐색

    def finish_verification(self, frame, image_msg, avg_conf):  # 1초 검증 성공 후 최종 메시지를 생성
        signature = crop_dhash(frame, self.bbox)  # 현재 이벤트를 나중에 중복 판정할 수 있도록 dHash 생성

        evidence_frame = frame.copy()  # 원본 영상은 유지하고 증적용 이미지를 별도 복사
        x1, y1, x2, y2 = self.bbox  # 최종 bbox 좌표 읽기
        cv2.rectangle(evidence_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)  # 증적 이미지에 bbox 표시
        cv2.putText(  # 증적 이미지에 class와 confidence 표시
            evidence_frame,  # 수정할 이미지
            f"{self.class_name} {avg_conf:.2f}",  # 예: fire 0.83
            (x1, max(20, y1 - 10)),  # bbox 위쪽에 텍스트 표시
            cv2.FONT_HERSHEY_SIMPLEX,  # 폰트
            0.7,  # 글자 크기
            (0, 255, 0),  # 초록색
            2,  # 글자 두께
        )

        ok, encoded = cv2.imencode(  # bbox가 그려진 이미지를 JPEG로 압축
            ".jpg",  # JPEG 형식
            evidence_frame,  # 압축할 이미지
            [cv2.IMWRITE_JPEG_QUALITY, 90],  # JPEG 품질 90
        )
        if not ok:  # JPEG 인코딩 실패 시
            self.get_logger().error(  # 실패 로그 출력
                f"Event evidence encoding failed | candidate_id={self.candidate_id}"  # 어떤 Candidate에서 실패했는지 표시
            )
            self.reset_candidate()  # 현재 Candidate 정리
            return  # Event 발행하지 않고 종료

        self.event_sequence += 1  # 최종 Event 순번 1 증가
        event_id = (  # 최종 Event ID 생성
            f"det-{self.session_id}-{self.class_name}-{self.event_sequence:06d}"  # 세션/class/순번 조합
        )
        evidence_id = f"evidence-{self.session_id}-{self.event_sequence:06d}"  # 현재 인터페이스의 evidence_id 생성
        stamp = self.get_clock().now().to_msg()  # 최종 Detection 확정 시각을 ROS Time으로 생성

        image = CompressedImage()  # DetectionEvent에 넣을 JPEG 이미지 메시지 생성
        image.header.stamp = stamp  # 증적 이미지 촬영/확정 시각
        image.header.frame_id = image_msg.header.frame_id  # 원본 카메라 optical frame 유지
        image.format = "jpeg"  # 압축 포맷을 JPEG로 명시
        image.data = encoded.tobytes()  # JPEG 압축 byte 데이터를 메시지에 저장

        event = DetectionEvent()  # 최종 DetectionEvent 메시지 생성
        event.header.stamp = stamp  # 최종 이벤트 확정 시각
        event.header.frame_id = image_msg.header.frame_id  # 이벤트 기준 카메라 frame
        event.event_id = event_id  # 최종 사건 고유 ID
        event.source_session_id = self.session_id  # 현재 비전 노드 실행 세션 ID
        event.source_sequence = self.event_sequence  # 이 세션 내 최종 이벤트 순번
        event.robot_id = ROBOT_ID  # 이벤트를 탐지한 로봇 ID
        event.mission_id = ""  # 현재 Vision은 mission 정보를 직접 받지 않으므로 빈 문자열
        event.command_id = ""  # 현재 Vision은 command 정보를 직접 받지 않으므로 빈 문자열
        event.event_type = EVENT_TYPE[self.class_name]  # fire/leak/obstacle을 enum 값으로 기록
        event.confidence = float(avg_conf)  # 1초 Verification 동안의 평균 confidence
        event.evidence_id = evidence_id  # 현재 인터페이스 호환을 위해 evidence_id 기록
        event.image = image  # bbox 표시 JPEG 이미지를 DetectionEvent 안에 직접 포함

        self.event_pub.publish(event)  # 모든 정보가 준비된 최종 DetectionEvent를 한 번 발행

        if signature is not None:  # 현재 이벤트 dHash가 정상 생성됐다면
            self.confirmed_hashes[EVENT_TYPE[self.class_name]].append(signature)  # 같은 event_type의 확정 hash 목록에 저장

        self.get_logger().info(  # 최종 Event 발행 성공 로그
            f"EVENT CONFIRMED + PUBLISHED | id={event_id} | "  # Event ID 출력
            f"type={self.class_name} | conf={avg_conf:.2f} | "  # class와 평균 confidence 출력
            f"jpeg_bytes={len(image.data)}"  # JPEG 데이터 크기 출력
        )

        self.reset_candidate()  # 현재 이벤트 처리 완료 후 다시 SEARCHING으로 복귀

    def is_duplicate(self, frame, bbox, class_name):  # 현재 이벤트가 과거 확정 이벤트와 중복인지 확인
        signature = crop_dhash(frame, bbox)  # 현재 bbox의 dHash 계산
        if signature is None:  # 해시 생성에 실패하면
            return False  # 중복이라고 단정하지 않고 새 이벤트로 처리

        return any(  # 같은 event_type의 과거 hash 중 하나라도 기준 이내이면 True
            (signature ^ old).bit_count() <= DEDUP_HASH_DISTANCE  # XOR 후 다른 bit 수 = Hamming distance 계산
            for old in self.confirmed_hashes[EVENT_TYPE[class_name]]  # 같은 event_type의 이전 확정 hash들과 비교
        )


def main(args=None):  # 프로그램 시작 함수
    rclpy.init(args=args)  # ROS2 Python 통신 초기화
    node = DetectingNode()  # 비전 노드 객체 생성

    try:  # 노드를 실행
        rclpy.spin(node)  # callback을 계속 처리하며 노드 유지
    except KeyboardInterrupt:  # Ctrl+C가 들어오면
        pass  # 정상 종료 흐름으로 이동
    finally:  # 종료할 때 반드시 실행
        cv2.destroyAllWindows()  # OpenCV 디버깅 창 모두 닫기
        node.destroy_node()  # ROS2 노드 객체 제거
        if rclpy.ok():  # ROS2가 아직 살아 있다면
            rclpy.shutdown()  # ROS2 정상 종료


if __name__ == "__main__":  # 이 파일을 직접 실행했을 때만
    main()  # main 함수 실행
