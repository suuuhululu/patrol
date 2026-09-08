#!/usr/bin/env python3

"""
AMR Vision Detection Node

기능
- OAK-D 영상 수신
- YOLO fire / leak / obstacle 탐지
- 0.3초 안에 같은 이벤트 2회 검출 시 Candidate 확정
- DetectionCandidate를 AMR에 발행
- 로봇 회전/정지는 수행하지 않음
"""

from collections import deque
from pathlib import Path
import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSProfile,
    ReliabilityPolicy,
    HistoryPolicy,
    DurabilityPolicy,
)

from sensor_msgs.msg import CompressedImage
from patrol_interfaces.msg import DetectionCandidate
from ultralytics import YOLO


# ==========================================================
# 설정
# ==========================================================

ROBOT_ID = "robot6"

CAMERA_TOPIC = "/robot6/oakd/rgb/image_raw/compressed"
CANDIDATE_TOPIC = "/robot6/vision/detection_candidate"

MODEL_PATH = Path(__file__).resolve().parent / "detection_best.pt"

# YOLO 최소 신뢰도
CONFIDENCE = 0.70

# 0.3초 안에 같은 이벤트가 2회 검출되면 Candidate
CANDIDATE_WINDOW_SEC = 0.30
CANDIDATE_MIN_HITS = 2

# 잠깐 탐지가 끊겨도 같은 Candidate 유지
CANDIDATE_LOST_SEC = 0.60

# 비전팀 제안 enum
EVENT_TYPE = {
    "fire": 0,
    "leak": 1,
    "obstacle": 2,
}


class DetectingNode(Node):

    def __init__(self):
        super().__init__("detecting_node")

        # OAK-D에서 실제 동작 확인한 QoS
        camera_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )

        # YOLO 모델 확인
        if not MODEL_PATH.is_file():
            raise FileNotFoundError(
                f"Model not found: {MODEL_PATH}"
            )

        # YOLO 모델은 시작할 때 한 번만 로드
        self.model = YOLO(str(MODEL_PATH))

        # 현재 Candidate 정보
        self.candidate_id = None
        self.class_name = None
        self.bbox = None
        self.confidence = 0.0

        self.sequence = 0
        self.last_seen = 0.0
        self.qualified = False

        # 최근 검출 시각 저장
        self.hits = deque()

        # OAK-D 카메라 구독
        self.image_sub = self.create_subscription(
            CompressedImage,
            CAMERA_TOPIC,
            self.image_callback,
            camera_qos,
        )

        # Candidate 발행
        self.candidate_pub = self.create_publisher(
            DetectionCandidate,
            CANDIDATE_TOPIC,
            10,
        )

        self.get_logger().info(
            f"Vision ready | classes={self.model.names}"
        )


    # ==========================================================
    # 새로운 Candidate 생성
    # ==========================================================

    def start_candidate(
        self,
        class_name,
        bbox,
        confidence,
        now,
    ):
        self.sequence += 1

        self.candidate_id = (
            f"cand-{ROBOT_ID}-{self.sequence:06d}"
        )

        self.class_name = class_name
        self.bbox = bbox
        self.confidence = confidence
        self.last_seen = now

        self.qualified = False

        self.hits.clear()
        self.hits.append(now)


    # ==========================================================
    # Candidate 제거
    # ==========================================================

    def clear_candidate(self):
        self.candidate_id = None
        self.class_name = None
        self.bbox = None
        self.confidence = 0.0

        self.last_seen = 0.0
        self.qualified = False

        self.hits.clear()


    # ==========================================================
    # OAK-D 영상 처리
    # ==========================================================

    def image_callback(self, msg):
        now = time.monotonic()

        try:
            # CompressedImage → OpenCV
            data = np.frombuffer(
                msg.data,
                dtype=np.uint8,
            )

            frame = cv2.imdecode(
                data,
                cv2.IMREAD_COLOR,
            )

            if frame is None:
                return

            # YOLO 추론
            result = self.model.predict(
                source=frame,
                conf=CONFIDENCE,
                imgsz=704,
                verbose=False,
            )[0]

            # 가장 confidence가 높은 이벤트 하나 선택
            detection = self.get_best_detection(
                result
            )

            # Candidate 판정
            self.update_candidate(
                detection,
                frame,
                msg,
                now,
            )

            # YOLO 결과 화면
            cv2.imshow(
                "AMR Vision",
                result.plot(),
            )

            if cv2.waitKey(1) & 0xFF == ord("q"):
                rclpy.shutdown()

        except Exception as error:
            self.get_logger().error(
                f"Vision error: {error}"
            )


    # ==========================================================
    # 현재 화면에서 가장 높은 confidence 객체 선택
    # ==========================================================

    def get_best_detection(self, result):
        best = None

        if result.boxes is None:
            return None

        for box in result.boxes:
            class_id = int(box.cls[0])

            class_name = str(
                self.model.names[class_id]
            )

            # 사용하는 이벤트만 처리
            if class_name not in EVENT_TYPE:
                continue

            confidence = float(box.conf[0])

            bbox = tuple(
                int(v)
                for v in box.xyxy[0].tolist()
            )

            if (
                best is None
                or confidence > best[1]
            ):
                best = (
                    class_name,
                    confidence,
                    bbox,
                )

        return best


    # ==========================================================
    # Candidate 판정
    # ==========================================================

    def update_candidate(
        self,
        detection,
        frame,
        image_msg,
        now,
    ):
        # 객체가 현재 검출된 경우
        if detection is not None:
            class_name, confidence, bbox = detection

            # 처음 발견했거나 이벤트 종류가 바뀜
            if (
                self.candidate_id is None
                or class_name != self.class_name
            ):
                self.start_candidate(
                    class_name,
                    bbox,
                    confidence,
                    now,
                )

            # 같은 종류의 이벤트 계속 검출
            else:
                self.bbox = bbox
                self.confidence = confidence
                self.last_seen = now

                self.hits.append(now)

        # 현재 프레임에서 검출되지 않음
        elif self.candidate_id is not None:

            # 0.6초 이상 안 보이면 Candidate 종료
            if (
                now - self.last_seen
                > CANDIDATE_LOST_SEC
            ):
                self.clear_candidate()

            return

        if self.candidate_id is None:
            return

        # 최근 0.3초의 검출만 유지
        while (
            self.hits
            and now - self.hits[0]
            > CANDIDATE_WINDOW_SEC
        ):
            self.hits.popleft()

        # 0.3초 안에 2회 이상 검출 → Candidate 확정
        if (
            not self.qualified
            and len(self.hits)
            >= CANDIDATE_MIN_HITS
        ):
            self.qualified = True

            self.get_logger().info(
                f"Candidate ACQUIRED | "
                f"id={self.candidate_id} | "
                f"type={self.class_name}"
            )

        # 확정 Candidate가 현재 보이면 최신 위치 발행
        if (
            self.qualified
            and detection is not None
        ):
            self.publish_candidate(
                frame,
                image_msg,
            )


    # ==========================================================
    # DetectionCandidate 발행
    # ==========================================================

    def publish_candidate(
        self,
        frame,
        image_msg,
    ):
        _, width = frame.shape[:2]

        x1, _, x2, _ = self.bbox

        # bbox 중심과 화면 중심 계산
        bbox_center_x = (x1 + x2) / 2.0
        image_center_x = width / 2.0

        # 정규화된 수평 오차
        #
        # 음수 = 객체가 왼쪽
        # 0    = 객체가 중앙
        # 양수 = 객체가 오른쪽
        horizontal_error = (
            bbox_center_x - image_center_x
        ) / image_center_x

        msg = DetectionCandidate()

        # 실제 카메라 프레임 timestamp 사용
        msg.header = image_msg.header

        msg.robot_id = ROBOT_ID
        msg.candidate_id = self.candidate_id

        msg.event_type = EVENT_TYPE[
            self.class_name
        ]

        msg.confidence = float(
            self.confidence
        )

        msg.horizontal_error = float(
            horizontal_error
        )

        self.candidate_pub.publish(msg)


# ==========================================================
# 실행
# ==========================================================

def main(args=None):
    rclpy.init(args=args)

    node = DetectingNode()

    try:
        rclpy.spin(node)

    except KeyboardInterrupt:
        pass

    finally:
        cv2.destroyAllWindows()

        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
