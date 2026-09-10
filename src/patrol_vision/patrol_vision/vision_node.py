#!/usr/bin/env python3
import time
import uuid

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage
from nav_msgs.msg import Odometry
from ultralytics import YOLO
from pathlib import Path

from patrol_interfaces.srv import ReportDetection  # TODO: patrol_interfaces에 srv 반영 후 임포트 확인


ROBOT_ID = "robot6"

CAMERA_TOPIC = "/robot6/oakd/rgb/image_raw/compressed"
ODOM_TOPIC = "/robot6/odom"  # 임시. AMCL 켜지면 /robot6/amcl_pose로 교체 (map 좌표계 아님, 테스트용)
SUBMIT_SERVICE = "/system_monitor/report_detection"

MODEL_PATH = Path("/home/hv-06/patrol/data/detection_data/detection_best.pt")  # TODO: 학습된 YOLO .pt 파일 경로 입력

YOLO_CONFIDENCE = 0.70
YOLO_IMAGE_SIZE = 704

HOLD_DURATION_SEC = 1.0
MAX_FRAME_GAP_SEC = 0.30

MAX_IMAGE_BYTES = 1024 * 1024  # 1 MiB. 인터페이스가 요구하는 상한
JPEG_QUALITY_FALLBACK = 50      # 1차 인코딩이 상한을 넘으면 품질 낮춰서 재시도

EVENT_TYPE_NAMES = ("fire", "leak", "obstacle")


class DetectingNode(Node):
    def __init__(self):
        super().__init__("detecting_node_test")

        best_effort = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )

        self.model = YOLO(str(MODEL_PATH))
        self.event_type_map = {
            "fire": ReportDetection.Request.FIRE,
            "leak": ReportDetection.Request.LEAK,
            "obstacle": ReportDetection.Request.OBSTACLE,
        }

        self.class_name = None
        self.bbox = None
        self.confidence = 0.0
        self.hold_start = None
        self.last_seen = None
        self.latest_pose = None
        self.reported = False
        self._pending_futures = set()

        self.image_sub = self.create_subscription(
            CompressedImage, CAMERA_TOPIC, self.image_callback, best_effort
        )
        self.odom_sub = self.create_subscription(
            Odometry, ODOM_TOPIC, self.odom_callback, best_effort
        )
        self.submit_client = self.create_client(ReportDetection, SUBMIT_SERVICE)

    def odom_callback(self, msg):
        self.latest_pose = msg.pose.pose

    def image_callback(self, image_msg):
        now = time.monotonic()

        try:
            frame = cv2.imdecode(
                np.frombuffer(image_msg.data, dtype=np.uint8), cv2.IMREAD_COLOR
            )
            if frame is None:
                return

            result = self.model.predict(
                source=frame, conf=YOLO_CONFIDENCE, imgsz=YOLO_IMAGE_SIZE, verbose=False
            )[0]

            detection = self.select_detection(result)

            if detection is None:
                if self.last_seen is not None and now - self.last_seen > MAX_FRAME_GAP_SEC:
                    self.reset()
            else:
                class_name, confidence, bbox = detection
                self.last_seen = now

                if self.reported and class_name == self.class_name:
                    pass
                else:
                    if self.class_name != class_name:
                        self.class_name = class_name
                        self.hold_start = now
                        self.reported = False
                    self.confidence = confidence
                    self.bbox = bbox

                    if not self.reported and now - self.hold_start >= HOLD_DURATION_SEC:
                        self.submit_event(frame, image_msg)
                        self.reported = True

            cv2.imshow("AMR Vision (test)", result.plot())

            if cv2.waitKey(1) & 0xFF == ord("q"):
                rclpy.shutdown()

        except Exception as error:
            self.get_logger().error(f"Vision error: {error}")

    def select_detection(self, result):
        best = None

        if result.boxes is not None:
            for box in result.boxes:
                class_id = int(box.cls[0])
                class_name = str(self.model.names[class_id]).strip().lower()

                if class_name not in EVENT_TYPE_NAMES:
                    continue

                confidence = float(box.conf[0])
                if best is None or confidence > best[1]:
                    bbox = tuple(int(v) for v in box.xyxy[0].tolist())
                    best = (class_name, confidence, bbox)

        return best

    def reset(self):
        self.class_name = None
        self.bbox = None
        self.confidence = 0.0
        self.hold_start = None
        self.last_seen = None
        self.reported = False

    def submit_event(self, frame, image_msg):
        evidence_frame = frame.copy()
        x1, y1, x2, y2 = self.bbox
        cv2.rectangle(evidence_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            evidence_frame,
            f"{self.class_name} {self.confidence:.2f}",
            (x1, max(20, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )

        ok, encoded = cv2.imencode(".jpg", evidence_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            return

        if encoded.nbytes > MAX_IMAGE_BYTES:
            # 1 MiB 넘으면 품질 낮춰서 한 번 더 시도
            ok, encoded = cv2.imencode(
                ".jpg", evidence_frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY_FALLBACK]
            )
            if not ok or encoded.nbytes > MAX_IMAGE_BYTES:
                self.get_logger().error(
                    f"증거 이미지가 1 MiB를 초과해 보고를 건너뜀 | size={encoded.nbytes if ok else 'N/A'}"
                )
                return

        if not self.submit_client.service_is_ready():
            return

        event_id = str(uuid.uuid4())

        request = ReportDetection.Request()
        request.robot_id = ROBOT_ID
        request.event_id = event_id
        request.detected_at = self.get_clock().now().to_msg()
        if self.latest_pose is not None:
            request.position.x = self.latest_pose.position.x
            request.position.y = self.latest_pose.position.y
        request.image = list(encoded.tobytes())
        request.event_type = self.event_type_map[self.class_name]

        future = self.submit_client.call_async(request)
        self._pending_futures.add(future)
        future.add_done_callback(lambda fut: self.on_submit_response(fut, event_id))

    def on_submit_response(self, future, event_id):
        self._pending_futures.discard(future)

        try:
            response = future.result()
        except Exception as error:
            self.get_logger().error(f"SUBMIT 실패 | event_id={event_id} error={error}")
            return

        self.get_logger().info(
            f"SUBMIT 결과 | event_id={event_id} status={response.status} detail={response.detail!r}"
        )


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
