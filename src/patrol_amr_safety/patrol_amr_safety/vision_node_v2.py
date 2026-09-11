#!/usr/bin/env python3
import math
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

if __package__:
    from .event_check import VisionPatrolLink
else:
    from event_check import VisionPatrolLink


ROBOT_ID = "robot1"

# 주의: 이 토픽이 실제로 발행되려면 카메라 드라이버 쪽에서 컴프레스드 발행을 켜줘야 함
# (지금 확인 결과 안 뜨고 있었음 -> 드라이버 설정/실행 쪽에서 활성화 필요)
CAMERA_TOPIC = "/robot1/oakd/rgb/image_raw/compressed"
ODOM_TOPIC = "/robot1/odom"  # 임시. AMCL 켜지면 /robot1/amcl_pose로 교체 (map 좌표계 아님, 테스트용)
SUBMIT_SERVICE = "/system_monitor/report_detection"

MODEL_PATH = Path("/home/mu-01/patrol/detection_best/detection_best.pt")  # TODO: 학습된 YOLO .pt 파일 경로 입력

YOLO_CONFIDENCE = 0.70
YOLO_IMAGE_SIZE = 704

HOLD_DURATION_SEC = 1.0
MAX_FRAME_GAP_SEC = 0.30
STATUS_LOG_PERIOD_SEC = 5.0  # 진단 출력 주기이며 정지/복구 판단에는 사용하지 않음

MAX_IMAGE_BYTES = 1024 * 1024  # 1 MiB. 인터페이스가 요구하는 상한
JPEG_QUALITY_FALLBACK = 50      # 1차 인코딩이 상한을 넘으면 품질 낮춰서 재시도

EVENT_TYPE_NAMES = ("fire", "leak", "obstacle")

# ------------------------------------------------------------------
# 중복 식별(같은 로봇 안에서 같은 사건 재보고 방지) — 레이(위치+방향) 교차 기반.
# 로봇 위치만으로는 실제 사건 위치를 알 수 없어(뎁쓰 미사용), odom 위치·yaw +
# bbox의 화면 내 위치(화각으로 각도 환산)로 "시선"을 구해 두 시선이 실제로
# 교차하는지로 판정한다. 뎁쓰 카메라는 연산량·레이턴시 문제로 쓰지 않는다.
# CR-비전_09-10_12-01 3절 참고.
# ------------------------------------------------------------------
CAMERA_HORIZONTAL_FOV_DEG = 64.0  # /robot1/oakd/rgb/preview/camera_info 기준 실측.
                                    # TODO: vision_node가 실제 쓰는 image_raw 기준 camera_info로 재확인 필요
CAMERA_HORIZONTAL_FOV_RAD = math.radians(CAMERA_HORIZONTAL_FOV_DEG)

NEAR_ORIGIN_THRESHOLD_M = 0.5      # 로봇이 거의 같은 자리(이 거리 이내)에서 본 것끼리는 각도 직접 비교
BEARING_NEAR_TOLERANCE_RAD = math.radians(15.0)   # 같은 자리 판정 시 각도 허용 오차
MIN_RAY_ANGLE_DIFF_RAD = math.radians(15.0)       # 두 레이 각도차가 이보다 작으면(거의 평행) 삼각측량 신뢰 불가
MAX_SENSOR_RANGE_M = 5.0           # 교차점이 이보다 멀면(비현실적) 무시


class DetectingNode(Node):
    def __init__(self):
        super().__init__("detecting_node_test")
        self.get_logger().info(
            f"VISION START | robot_id={ROBOT_ID} camera={CAMERA_TOPIC} odom={ODOM_TOPIC}"
        )

        best_effort = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )

        self.get_logger().info(f"YOLO loading | model={MODEL_PATH}")
        try:
            self.model = YOLO(str(MODEL_PATH))
        except Exception as error:
            self.get_logger().error(f"YOLO load failed | model={MODEL_PATH} error={error}")
            raise
        self.get_logger().info(
            f"YOLO ready | classes={self.model.names} "
            f"allowed={EVENT_TYPE_NAMES} confidence={YOLO_CONFIDENCE}"
        )
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
        self._frames_received = 0
        self._frames_processed = 0
        self._last_image_at = None
        self._last_odom_at = None
        self._last_detection = "none"
        self._last_boxes_count = 0

        # 같은 로봇이 보고한 사건들: [{"class_name", "x", "y", "theta"}, ...] (중복 식별용)
        self._reported_events = []
        self._MAX_REPORTED_EVENTS = 500  # 장시간 운용 시 메모리 상한(안전장치, 실제로 도달할 일은 거의 없음)

        self.image_sub = self.create_subscription(
            CompressedImage, CAMERA_TOPIC, self.image_callback, best_effort
        )
        self.odom_sub = self.create_subscription(
            Odometry, ODOM_TOPIC, self.odom_callback, best_effort
        )
        self.submit_client = self.create_client(ReportDetection, SUBMIT_SERVICE)
        self.patrol_events = VisionPatrolLink(self, ROBOT_ID)
        self._status_timer = self.create_timer(STATUS_LOG_PERIOD_SEC, self._log_status)
        self.get_logger().info(
            f"VISION READY | waiting for camera frames; report_service={SUBMIT_SERVICE} "
            f"status_log_period={STATUS_LOG_PERIOD_SEC}s"
        )

    def _log_status(self):
        now = time.monotonic()
        camera_age = "never" if self._last_image_at is None else f"{now - self._last_image_at:.1f}s"
        odom_age = "never" if self._last_odom_at is None else f"{now - self._last_odom_at:.1f}s"
        self.get_logger().info(
            f"VISION STATUS | camera_publishers={self.count_publishers(CAMERA_TOPIC)} "
            f"frames={self._frames_received} processed={self._frames_processed} "
            f"camera_age={camera_age} odom_age={odom_age} "
            f"boxes={self._last_boxes_count} detection={self._last_detection} "
            f"stop_busy={self.patrol_events.busy} stopped={self.patrol_events.stopped} "
            f"reported={self.reported} pending_reports={len(self._pending_futures)} "
            f"report_service_ready={self.submit_client.service_is_ready()}"
        )

    def odom_callback(self, msg):
        if self._last_odom_at is None:
            self.get_logger().info(f"ODOM first message | topic={ODOM_TOPIC}")
        self._last_odom_at = time.monotonic()
        self.latest_pose = msg.pose.pose

    def get_current_pose_2d(self):
        """(x, y, yaw) 또는 아직 odom을 못 받았으면 None."""
        if self.latest_pose is None:
            return None
        x = self.latest_pose.position.x
        y = self.latest_pose.position.y
        yaw = self._yaw_from_quaternion(self.latest_pose.orientation)
        return (x, y, yaw)

    def get_current_position(self):
        pose = self.get_current_pose_2d()
        if pose is None:
            return None
        return (pose[0], pose[1])

    @staticmethod
    def _yaw_from_quaternion(q):
        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        return math.atan2(siny_cosp, cosy_cosp)

    @staticmethod
    def _bearing_offset(bbox, frame_width):
        """bbox 중심이 화면 중심에서 벗어난 정도를, 카메라 화각 기준 각도(rad)로 변환.
        TODO: 실제 로봇에서 부호(왼쪽/오른쪽 회전 방향과 일치하는지) 검증 필요."""
        x1, _, x2, _ = bbox
        bbox_center_x = (x1 + x2) / 2.0
        frame_center_x = frame_width / 2.0
        ratio = (bbox_center_x - frame_center_x) / frame_center_x  # -1..1
        return ratio * (CAMERA_HORIZONTAL_FOV_RAD / 2.0)

    def compute_theta(self, bbox, frame_width):
        """지금 로봇 pose + bbox 위치로, 대상을 향한 절대 방향(rad)을 계산. pose 없으면 None."""
        pose = self.get_current_pose_2d()
        if pose is None:
            return None
        _, _, yaw = pose
        return yaw + self._bearing_offset(bbox, frame_width)

    def image_callback(self, image_msg):
        now = time.monotonic()
        self._frames_received += 1
        self._last_image_at = now
        if self._frames_received == 1:
            self.get_logger().info(
                f"CAMERA first frame | topic={CAMERA_TOPIC} bytes={len(image_msg.data)}"
            )

        try:
            frame = cv2.imdecode(
                np.frombuffer(image_msg.data, dtype=np.uint8), cv2.IMREAD_COLOR
            )
            if frame is None:
                self.get_logger().warning(
                    f"CAMERA decode failed | bytes={len(image_msg.data)}",
                    throttle_duration_sec=STATUS_LOG_PERIOD_SEC,
                )
                return

            if self._frames_received == 1:
                self.get_logger().info(f"YOLO first inference starting | shape={frame.shape}")
            result = self.model.predict(
                source=frame, conf=YOLO_CONFIDENCE, imgsz=YOLO_IMAGE_SIZE, verbose=False
            )[0]
            self._frames_processed += 1
            self._last_boxes_count = 0 if result.boxes is None else len(result.boxes)

            detection = self.select_detection(result)
            self._last_detection = (
                "none" if detection is None else f"{detection[0]}:{detection[1]:.2f}"
            )
            frame_width = frame.shape[1]

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
                        # 새로 잡힌 후보 -> hold 타이머 시작 전에 먼저 중복부터 확인
                        if self.is_known_event(class_name, bbox, frame_width):
                            # 같은 로봇이 이미 보고한 사건과 같음(레이 교차로 확인) -> 후보로 삼지 않고 무시
                            self.get_logger().info(
                                f"DETECTION skipped: known event | class={class_name} bbox={bbox}",
                                throttle_duration_sec=STATUS_LOG_PERIOD_SEC,
                            )
                            return
                        self.class_name = class_name
                        self.hold_start = now
                        self.reported = False
                        self.get_logger().info(
                            f"DETECTION candidate | class={class_name} confidence={confidence:.2f} "
                            f"bbox={bbox}; requesting patrol stop"
                        )
                    self.confidence = confidence
                    self.bbox = bbox

                    if not self.reported:
                        # 첫 유효 bbox에서 즉시 정지 요청. 1초 hold는 보고에만 적용.
                        self.patrol_events.request()
                        if (self.patrol_events.stopped and not self._pending_futures
                                and now - self.hold_start >= HOLD_DURATION_SEC):
                            self.submit_event(frame)
                            self.reported = True

            cv2.imshow("AMR Vision (test)", result.plot())

            if cv2.waitKey(1) & 0xFF == ord("q"):
                self.get_logger().info("VISION shutdown requested | key=q")
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
        if self.class_name is not None:
            self.get_logger().info(
                f"DETECTION reset: frame gap exceeded | class={self.class_name} "
                f"stop_busy={self.patrol_events.busy} stopped={self.patrol_events.stopped}"
            )
        self.class_name = None
        self.bbox = None
        self.confidence = 0.0
        self.hold_start = None
        self.last_seen = None
        self.reported = False

    # ------------------------------------------------------------------
    # 중복 식별 — 레이(위치+방향) 교차 기반. CR-비전_09-10_12-01 3절 참고.
    # ------------------------------------------------------------------
    def is_known_event(self, class_name, bbox, frame_width):
        pose = self.get_current_pose_2d()
        if pose is None:
            return False  # 위치를 모르면 판단 불가 -> 중복 아님으로 취급하고 정상 진행

        x, y, yaw = pose
        theta = yaw + self._bearing_offset(bbox, frame_width)

        for event in self._reported_events:
            if event["class_name"] != class_name:
                continue

            ex, ey, etheta = event["x"], event["y"], event["theta"]
            origin_dist = math.hypot(x - ex, y - ey)

            if origin_dist <= NEAR_ORIGIN_THRESHOLD_M:
                # 거의 같은 자리에서 본 것 -> 각도까지 비슷해야 같은 사건
                if self._angle_diff(theta, etheta) <= BEARING_NEAR_TOLERANCE_RAD:
                    return True
                continue  # 같은 자리인데 각도가 다르면 다른 사건(같은 지점, 다른 방향)

            # 원점이 떨어져 있으면(다른 웨이포인트 등) 실제로 레이를 교차시켜 확인
            if self._intersect_rays(x, y, theta, ex, ey, etheta) is not None:
                return True

        return False

    def record_reported_event(self, class_name, position, theta):
        if position is None or theta is None:
            return

        x, y = position
        self._reported_events.append({"class_name": class_name, "x": x, "y": y, "theta": theta})
        if len(self._reported_events) > self._MAX_REPORTED_EVENTS:
            self._reported_events = self._reported_events[-self._MAX_REPORTED_EVENTS:]

    @staticmethod
    def _angle_diff(a, b):
        d = (a - b + math.pi) % (2 * math.pi) - math.pi
        return abs(d)

    @staticmethod
    def _intersect_rays(x1, y1, th1, x2, y2, th2):
        """두 레이가 실제로 교차하는 지점을 구한다. 둘 다 '앞쪽'이고 탐지 가능
        거리 안이면 좌표를 반환, 아니면(뒤쪽/너무 멀리/거의 평행) None."""
        angle_between = DetectingNode._angle_diff(th1, th2)
        if angle_between < MIN_RAY_ANGLE_DIFF_RAD or angle_between > (math.pi - MIN_RAY_ANGLE_DIFF_RAD):
            return None  # 거의 평행 -> 삼각측량 신뢰 불가

        d1x, d1y = math.cos(th1), math.sin(th1)
        d2x, d2y = math.cos(th2), math.sin(th2)

        cross = d1x * d2y - d1y * d2x
        if abs(cross) < 1e-6:
            return None

        dx = x2 - x1
        dy = y2 - y1
        t1 = (dx * d2y - dy * d2x) / cross
        t2 = (dx * d1y - dy * d1x) / cross

        if t1 <= 0 or t2 <= 0:
            return None  # 둘 중 하나라도 로봇 '뒤쪽'이면 무효
        if t1 > MAX_SENSOR_RANGE_M or t2 > MAX_SENSOR_RANGE_M:
            return None  # 비현실적으로 먼 교차점

        return (x1 + t1 * d1x, y1 + t1 * d1y)

    def submit_event(self, frame):
        frame_width = frame.shape[1]
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
            self.get_logger().error("SUBMIT skipped | JPEG encoding failed")
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
            self.get_logger().warning(
                f"SUBMIT skipped | service not ready: {SUBMIT_SERVICE}"
            )
            return

        event_id = str(uuid.uuid4())
        class_name = self.class_name
        # 보고 시점(=지금)의 위치·방향을 스냅샷으로 떠서 그대로 쓴다(응답 콜백에서
        # 다시 조회하면 그 사이 로봇이 움직였을 수 있어 엉뚱한 값이 될 수 있음).
        position = self.get_current_position()
        theta = self.compute_theta(self.bbox, frame_width)

        request = ReportDetection.Request()
        request.robot_id = ROBOT_ID
        request.event_id = event_id
        request.detected_at = self.get_clock().now().to_msg()
        if position is not None:
            request.position.x, request.position.y = position
        request.image = list(encoded.tobytes())
        request.event_type = self.event_type_map[class_name]

        self.get_logger().info(
            f"SUBMIT request | event_id={event_id} class={class_name} "
            f"image_bytes={encoded.nbytes} position={position}"
        )
        future = self.submit_client.call_async(request)
        self._pending_futures.add(future)
        future.add_done_callback(
            lambda fut: self.on_submit_response(fut, event_id, class_name, position, theta)
        )

    def on_submit_response(self, future, event_id, class_name, position, theta):
        self._pending_futures.discard(future)

        try:
            response = future.result()
        except Exception as error:
            self.get_logger().error(f"SUBMIT 실패 | event_id={event_id} error={error}")
            return

        self.get_logger().info(
            f"SUBMIT 결과 | event_id={event_id} status={response.status} detail={response.detail!r}"
        )

        if response.status == ReportDetection.Response.STORED:
            self.record_reported_event(class_name, position, theta)
            self.patrol_events.resume()
        else:
            self.get_logger().warning(
                f"SUBMIT not stored: resume not sent | event_id={event_id} status={response.status}"
            )


def main(args=None):
    rclpy.init(args=args)
    node = DetectingNode()

    try:
        node.get_logger().info("VISION spin started")
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("VISION shutdown requested | KeyboardInterrupt")
    finally:
        node.get_logger().info("VISION cleanup")
        cv2.destroyAllWindows()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
