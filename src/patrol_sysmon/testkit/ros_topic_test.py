"""15~19단계: 격리 DDS에서 활성화된 가상 토픽의 종단 수신을 검증한다."""

from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import base64
import math
import os
import secrets
import sqlite3
import tempfile
import time
import uuid

from app import create_app
from app.database import get_db
from app.ros_adapter import RosAdapterUnavailable, _qos_profiles, build_node, dependency_report
from app.services import auth_service


# camera_service가 실제 PNG header와 크기를 검사할 수 있는 1×1 PNG다.
TEST_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
OPERATIONAL_DOMAIN_ID = 6


@dataclass(frozen=True)
class RosTopicTestConfig:
    """실제 운영 DDS와 저장소를 건드리지 않는 로컬 종단시험 설정."""

    duration_seconds: float = 3.0
    domain_id: int = 77
    status_hz: float = 4.0
    map_hz: float = 1.0
    image_hz: float = 2.0
    costmap_hz: float = 0.0
    detection_hz: float = 0.0
    cctv_hz: float = 0.0
    patrol_hz: float = 0.0
    safety_hz: float = 0.0

    def validate(self):
        if (
            isinstance(self.duration_seconds, bool)
            or not isinstance(self.duration_seconds, (int, float))
            or not math.isfinite(self.duration_seconds)
            or self.duration_seconds <= 0
        ):
            raise ValueError("duration_seconds는 0보다 큰 유한한 숫자여야 합니다.")
        if (
            isinstance(self.domain_id, bool)
            or not isinstance(self.domain_id, int)
            or not 0 <= self.domain_id <= 232
        ):
            raise ValueError("domain_id는 0에서 232 사이의 정수여야 합니다.")
        if self.domain_id == OPERATIONAL_DOMAIN_ID:
            raise ValueError("로컬 시험에는 운영 ROS_DOMAIN_ID=6을 사용할 수 없습니다.")
        for name in ("status_hz", "map_hz", "image_hz"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name}는 0보다 큰 유한한 숫자여야 합니다.")
        for name in ("costmap_hz", "detection_hz", "cctv_hz", "patrol_hz", "safety_hz"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{name}는 0 이상의 유한한 숫자여야 합니다.")


@contextmanager
def _isolated_ros_environment(domain_id, log_dir):
    """시험 프로세스에만 별도 도메인·발견 범위·로그 경로를 적용하고 복원한다."""
    previous = {
        name: os.environ.get(name)
        for name in (
            "ROS_DOMAIN_ID",
            "ROS_AUTOMATIC_DISCOVERY_RANGE",
            "ROS_LOCALHOST_ONLY",
            "ROS_LOG_DIR",
        )
    }
    log_dir.mkdir(parents=True, exist_ok=True)
    os.environ["ROS_DOMAIN_ID"] = str(domain_id)
    os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "LOCALHOST"
    os.environ.pop("ROS_LOCALHOST_ONLY", None)
    os.environ["ROS_LOG_DIR"] = str(log_dir)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _temporary_app(root):
    instance = root / "instance"
    return create_app({
        "TESTING": True,
        "DATABASE": str(instance / "sysmon.sqlite3"),
        "EVIDENCE_DIR": str(instance / "evidence"),
        "MAP_DIR": str(instance / "maps"),
        "VIDEO_DIR": str(instance / "live_frames"),
        "COSTMAP_DIR": str(instance / "costmaps"),
        "SECRET_KEY": secrets.token_urlsafe(32),
        "ROBOT_API_KEY": secrets.token_urlsafe(32),
    })


def _create_viewer(app):
    with app.app_context():
        return auth_service.create_user(
            f"ros-viewer-{secrets.token_hex(6)}",
            secrets.token_urlsafe(24),
            "VIEWER",
        )


def build_virtual_publisher(config):
    """선택한 단계의 계약 타입·QoS로 가상 토픽을 발행하는 노드를 만든다."""
    from nav_msgs.msg import OccupancyGrid
    from parking_interfaces.msg import (
        CameraState, DetectionEvent, EStopState, EvidenceChunk, IngestionAck,
        KeepoutStatus, PatrolReport, PatrolVisit, RobotStatus,
    )

    # [시연 범위] 관제가 저장하는 세 종류만 사용한다.
    DETECTION_DEMO_TYPES = (
        DetectionEvent.FIRE, DetectionEvent.LEAK, DetectionEvent.OBSTACLE,
    )
    from rclpy.node import Node
    from sensor_msgs.msg import CompressedImage
    from std_msgs.msg import Bool

    qos = _qos_profiles()

    class VirtualPublisher(Node):
        def __init__(self):
            super().__init__(f"sysmon_virtual_publisher_{os.getpid()}")
            self.published_counts = Counter()
            self._boot_id = str(uuid.uuid4())
            self._status_sequence = {"robot1": 0, "robot6": 0}
            self._status_publishers = {
                robot_id: self.create_publisher(
                    RobotStatus, f"/{robot_id}/robot_status", qos["robot_status"]
                )
                for robot_id in ("robot1", "robot6")
            }
            self._map_publisher = self.create_publisher(
                OccupancyGrid, "/map", qos["map"]
            )
            self._image_publishers = {
                topic: self.create_publisher(CompressedImage, topic, qos["camera_frame"])
                for topic in (
                    "/robot1/oakd/image/compressed",
                    "/robot6/oakd/image/compressed",
                    "/vision/cctv/gate/image/compressed",
                    "/vision/cctv/center/image/compressed",
                )
            }
            self._costmap_publishers = {
                topic: self.create_publisher(OccupancyGrid, topic, qos["costmap"])
                for topic in (
                    "/robot1/global_costmap/costmap",
                    "/robot1/local_costmap/costmap",
                    "/robot6/global_costmap/costmap",
                    "/robot6/local_costmap/costmap",
                )
            } if config.costmap_hz > 0 else {}
            self._detection_publishers = {
                robot_id: self.create_publisher(
                    DetectionEvent, f"/{robot_id}/detection/event", qos["detection_event"]
                )
                for robot_id in ("robot1", "robot6")
            } if config.detection_hz > 0 else {}
            self._evidence_publishers = {
                robot_id: self.create_publisher(
                    EvidenceChunk, f"/{robot_id}/detection/evidence", qos["evidence_chunk"]
                )
                for robot_id in ("robot1", "robot6")
            } if config.detection_hz > 0 else {}
            self.received_acks = Counter()
            self._ack_subscriptions = {
                robot_id: self.create_subscription(
                    IngestionAck, f"/{robot_id}/ingestion_ack",
                    lambda message, robot=robot_id: self._receive_ack(robot, message),
                    qos["ingestion_ack"],
                )
                for robot_id in ("robot1", "robot6")
            } if config.detection_hz > 0 else {}
            self._cctv_sequence = 0
            self._detection_sequence = 0
            self._cctv_publishers = {
                "gate_cam": self.create_publisher(
                    CameraState, "/vision/cctv/gate_event", qos["camera_state"]
                ),
                "center_cam": self.create_publisher(
                    CameraState, "/vision/cctv/center_event", qos["camera_state"]
                ),
            } if config.cctv_hz > 0 else {}
            self._permit_publisher = (
                self.create_publisher(
                    Bool, "/vision/cctv/patrol_allowed", qos["patrol_allowed_writer"]
                )
                if config.cctv_hz > 0 else None
            )
            self._patrol_visit_publishers = {
                robot_id: self.create_publisher(
                    PatrolVisit, f"/{robot_id}/patrol_visit", qos["patrol_visit"]
                ) for robot_id in ("robot1", "robot6")
            } if config.patrol_hz > 0 else {}
            self._patrol_report_publishers = {
                robot_id: self.create_publisher(
                    PatrolReport, f"/{robot_id}/patrol_report", qos["patrol_report"]
                ) for robot_id in ("robot1", "robot6")
            } if config.patrol_hz > 0 else {}
            self._keepout_publishers = {
                robot_id: self.create_publisher(
                    KeepoutStatus, f"/{robot_id}/keepout/status", qos["keepout_status"]
                ) for robot_id in ("robot1", "robot6")
            } if config.safety_hz > 0 else {}
            self._estop_publisher = (
                self.create_publisher(EStopState, "/control/estop", qos["estop"])
                if config.safety_hz > 0 else None
            )
            # [실행 구분] 같은 patrol_id가 다음 실행에서 다른 결과로 재사용되면
            # 관제가 충돌로 거부한다. 실행마다 다른 토큰을 붙인다.
            self._patrol_run_token = uuid.uuid4().hex[:8]
            self._patrol_sequence = 0
            self._safety_sequence = 0
            self.create_timer(1.0 / config.status_hz, self.publish_statuses)
            self.create_timer(1.0 / config.map_hz, self.publish_map)
            self.create_timer(1.0 / config.image_hz, self.publish_images)
            if config.costmap_hz > 0:
                self.create_timer(1.0 / config.costmap_hz, self.publish_costmaps)
            if config.detection_hz > 0:
                self.create_timer(1.0 / config.detection_hz, self.publish_detections)
            if config.cctv_hz > 0:
                self.create_timer(1.0 / config.cctv_hz, self.publish_cctv_state)
            if config.patrol_hz > 0:
                self.create_timer(1.0 / config.patrol_hz, self.publish_patrol)
            if config.safety_hz > 0:
                self.create_timer(1.0 / config.safety_hz, self.publish_safety)

        def publish_statuses(self):
            for index, (robot_id, publisher) in enumerate(
                self._status_publishers.items()
            ):
                self._status_sequence[robot_id] += 1
                sequence = self._status_sequence[robot_id]
                stamp = self.get_clock().now().to_msg()
                message = RobotStatus()
                message.header.stamp = stamp
                message.header.frame_id = "map"
                message.message_id = str(uuid.uuid4())
                message.boot_id = self._boot_id
                message.sequence = sequence
                message.robot_id = robot_id
                message.operational_state = RobotStatus.OP_MOVING
                message.mission_state = RobotStatus.MISSION_PATROLLING
                message.docking_state = RobotStatus.DOCK_UNDOCKED
                message.battery_state = RobotStatus.BATTERY_NORMAL
                message.battery_soc = 0.8 - index * 0.1
                message.pose.pose.position.x = float(sequence) / 10.0
                message.pose.pose.position.y = float(index)
                message.pose.pose.orientation.w = 1.0
                message.pose_valid = True
                message.last_valid_pose_stamp = stamp
                message.active_command_id = ""
                message.mission_id = str(uuid.uuid4())
                message.patrol_id = "local-stage15"
                message.safety_flags = RobotStatus.SAFETY_NONE
                message.drive_token_valid = False
                message.keepout_enabled = False
                message.diagnostic_code = 0
                message.diagnostic_text = "virtual stage15 publisher"
                publisher.publish(message)
                self.published_counts[f"/{robot_id}/robot_status"] += 1

        def publish_map(self):
            stamp = self.get_clock().now().to_msg()
            message = OccupancyGrid()
            message.header.stamp = stamp
            message.header.frame_id = "map"
            message.info.map_load_time = stamp
            message.info.resolution = 0.5
            message.info.width = 8
            message.info.height = 8
            message.info.origin.orientation.w = 1.0
            # [시연 화면] 실제 주차장 지도가 아니므로 전 구역을 미확인(-1)으로 보낸다.
            # 수신·저장·좌표 변환 경로는 그대로 검증되고 화면만 카메라처럼 어둡게 보인다.
            message.data = [-1] * 64
            self._map_publisher.publish(message)
            self.published_counts["/map"] += 1

        def publish_images(self):
            stamp = self.get_clock().now().to_msg()
            for topic, publisher in self._image_publishers.items():
                message = CompressedImage()
                message.header.stamp = stamp
                message.header.frame_id = "virtual_camera_optical_frame"
                message.format = "png"
                message.data = list(TEST_PNG)
                publisher.publish(message)
                self.published_counts[topic] += 1

        def publish_costmaps(self):
            stamp = self.get_clock().now().to_msg()
            for index, (topic, publisher) in enumerate(self._costmap_publishers.items()):
                message = OccupancyGrid()
                message.header.stamp = stamp
                message.header.frame_id = "map"
                message.info.map_load_time = stamp
                message.info.resolution = 0.1 if "local" in topic else 0.5
                message.info.width = 8
                message.info.height = 8
                message.info.origin.position.x = -2.0 + index
                message.info.origin.position.y = -1.0
                message.info.origin.orientation.w = 1.0
                # source마다 다른 장애물 패턴을 넣어 분리 저장 여부를 확인한다.
                message.data = [0] * (44 + index) + [100] * 8 + [-1] * (12 - index)
                publisher.publish(message)
                self.published_counts[topic] += 1

        def publish_detections(self):
            # [번갈아 발행] 호출마다 종류를 바꿔 세 이벤트가 모두 화면에 나오게 한다.
            self._detection_sequence += 1
            """로봇마다 증적 2개 chunk를 역순 사이에 event를 끼워 독립 도착을 시험한다."""
            for index, robot_id in enumerate(self._detection_publishers):
                stamp = self.get_clock().now().to_msg()
                event_id = str(uuid.uuid4())
                evidence_id = str(uuid.uuid4())
                parts = (TEST_PNG[:len(TEST_PNG) // 2], TEST_PNG[len(TEST_PNG) // 2:])
                digest = sha256(TEST_PNG).hexdigest()

                def evidence_message(chunk_index):
                    message = EvidenceChunk()
                    message.header.stamp = stamp
                    message.header.frame_id = "virtual_camera_optical_frame"
                    message.message_id = str(uuid.uuid4())
                    message.evidence_id = evidence_id
                    message.event_id = event_id
                    message.robot_id = robot_id
                    message.captured_at = stamp
                    message.media_type = "image/png"
                    message.sha256 = digest
                    message.total_size = len(TEST_PNG)
                    message.chunk_index = chunk_index
                    message.chunk_count = 2
                    message.data = list(parts[chunk_index])
                    return message

                evidence_topic = f"/{robot_id}/detection/evidence"
                self._evidence_publishers[robot_id].publish(evidence_message(1))
                self.published_counts[evidence_topic] += 1

                event = DetectionEvent()
                event.header.stamp = stamp
                event.header.frame_id = "map"
                event.message_id = str(uuid.uuid4())
                event.event_id = event_id
                event.robot_id = robot_id
                # [시연 범위] 관제가 저장하는 화재·누수·장애물만 로봇별로 번갈아 발행한다.
                event.event_type = DETECTION_DEMO_TYPES[
                    (self._detection_sequence + index) % len(DETECTION_DEMO_TYPES)
                ]
                event.confidence = 0.9
                event.risk_level = DetectionEvent.RISK_MEDIUM
                event.pose.pose.position.x = 1.0 + index
                event.pose.pose.position.y = 2.0 + index
                event.pose.pose.orientation.w = 1.0
                event.location_valid = True
                event.detected_at = stamp
                event.evidence_id = evidence_id
                event_topic = f"/{robot_id}/detection/event"
                self._detection_publishers[robot_id].publish(event)
                self.published_counts[event_topic] += 1

                self._evidence_publishers[robot_id].publish(evidence_message(0))
                self.published_counts[evidence_topic] += 1

        def _receive_ack(self, robot_id, message):
            self.received_acks[f"{robot_id}:{message.entity_type}:{message.status}"] += 1

        def publish_patrol(self):
            """관측점 방문 두 건마다 순찰 결과 한 건을 계약 순서로 발행한다."""
            stamp = self.get_clock().now().to_msg()
            self._patrol_sequence += 1
            waypoints = ("P1", "P2", "P3", "P4", "P5", "P6", "P7")
            for index, robot_id in enumerate(self._patrol_visit_publishers):
                patrol_id = (
                    f"patrol-{robot_id}-{self._patrol_run_token}"
                    f"-{self._patrol_sequence // 2:04d}"
                )
                visit = PatrolVisit()
                visit.header.stamp = stamp
                visit.header.frame_id = "map"
                visit.message_id = str(uuid.uuid4())
                visit.visit_id = str(uuid.uuid4())
                visit.patrol_id = patrol_id
                visit.mission_id = ""
                visit.command_id = ""
                visit.robot_id = robot_id
                visit.waypoint_id = waypoints[
                    (self._patrol_sequence + index) % len(waypoints)
                ]
                visit.pose.header.stamp = stamp
                visit.pose.header.frame_id = "map"
                visit.pose.pose.position.x = 3.0 + index
                visit.pose.pose.position.y = 4.0 + index
                visit.pose.pose.orientation.w = 1.0
                visit.result = PatrolVisit.SUCCEEDED
                visit.reason_code = 0
                visit.reason = ""
                visit.arrived_at = stamp
                visit.completed_at = stamp
                self._patrol_visit_publishers[robot_id].publish(visit)
                self.published_counts[f"/{robot_id}/patrol_visit"] += 1

                # [보고 주기] 방문 두 건마다 순찰 한 회를 마무리해 결과 보고를 보낸다.
                if self._patrol_sequence % 2 == 0:
                    report = PatrolReport()
                    report.header.stamp = stamp
                    report.header.frame_id = "map"
                    report.message_id = str(uuid.uuid4())
                    report.report_id = str(uuid.uuid4())
                    report.patrol_id = patrol_id
                    report.mission_id = ""
                    report.command_id = ""
                    report.robot_id = robot_id
                    report.result = PatrolReport.SUCCEEDED
                    report.reason_code = 0
                    report.reason = ""
                    report.started_at = stamp
                    report.ended_at = stamp
                    report.planned_visit_count = 2
                    report.completed_visit_count = 2
                    self._patrol_report_publishers[robot_id].publish(report)
                    self.published_counts[f"/{robot_id}/patrol_report"] += 1

        def publish_safety(self):
            """Keepout 적용 상태와 E-stop 활성·해제를 번갈아 발행한다."""
            stamp = self.get_clock().now().to_msg()
            self._safety_sequence += 1
            states = (
                KeepoutStatus.APPLIED, KeepoutStatus.ROLLED_BACK,
                KeepoutStatus.DISABLED, KeepoutStatus.ROLLBACK_FAILED,
            )
            for index, robot_id in enumerate(self._keepout_publishers):
                message = KeepoutStatus()
                message.header.stamp = stamp
                message.header.frame_id = "map"
                message.message_id = str(uuid.uuid4())
                message.transaction_id = str(uuid.uuid4())
                message.robot_id = robot_id
                message.state = states[(self._safety_sequence + index) % len(states)]
                message.global_enabled = True
                message.local_enabled = bool((self._safety_sequence + index) % 2)
                message.reason_code = 0
                message.detail = ""
                self._keepout_publishers[robot_id].publish(message)
                self.published_counts[f"/{robot_id}/keepout/status"] += 1

            if self._estop_publisher is not None:
                active = self._safety_sequence % 2 == 1
                estop = EStopState()
                estop.header.stamp = stamp
                estop.header.frame_id = ""
                estop.message_id = str(uuid.uuid4())
                estop.estop_id = str(uuid.uuid4())
                estop.boot_id = str(uuid.uuid4())
                estop.active = active
                estop.reason_code = 101 if active else 0
                estop.reason = "가상 안전 시험" if active else ""
                estop.manual_reset_required = False
                estop.source_id = "virtual_safety_arbiter"
                estop.sequence = self._safety_sequence
                self._estop_publisher.publish(estop)
                self.published_counts["/control/estop"] += 1

        def publish_cctv_state(self):
            """진입·주차·출차 상태와 그에 대응하는 permit을 계약 순서로 발행한다."""
            cases = (
                ("gate_cam", CameraState.ENTERING, False),
                ("center_cam", CameraState.PARKED, True),
                ("center_cam", CameraState.EXITING, False),
                ("gate_cam", CameraState.EXITED, True),
            )
            camera_id, state, allowed = cases[self._cctv_sequence % len(cases)]
            self._cctv_sequence += 1
            message = CameraState()
            message.header.stamp = self.get_clock().now().to_msg()
            message.header.frame_id = camera_id
            message.event_id = str(uuid.uuid4())
            message.camera_id = camera_id
            message.state = state
            message.confidence = 0.92
            topic = (
                "/vision/cctv/gate_event"
                if camera_id == "gate_cam" else "/vision/cctv/center_event"
            )
            self._cctv_publishers[camera_id].publish(message)
            self.published_counts[topic] += 1

            permit = Bool()
            permit.data = allowed
            self._permit_publisher.publish(permit)
            self.published_counts["/vision/cctv/patrol_allowed"] += 1

        def publish_all(self):
            # [시험 초기 발행] 타이머가 이미 발행한 종류는 즉시 재발행하지 않아
            # 밀리초 정규화 뒤 같은 observed_at으로 판정되는 비결정적 stale를 막는다.
            if not any(topic.endswith("/robot_status") for topic in self.published_counts):
                self.publish_statuses()
            if self.published_counts["/map"] == 0:
                self.publish_map()
            if not any("/image/compressed" in topic for topic in self.published_counts):
                self.publish_images()
            if self._costmap_publishers and not any(
                "/costmap/" in topic for topic in self.published_counts
            ):
                self.publish_costmaps()
            if self._detection_publishers and not any(
                "/detection/event" in topic for topic in self.published_counts
            ):
                self.publish_detections()
            if self._cctv_publishers and not any(
                "/vision/cctv/" in topic and not topic.endswith("/image/compressed")
                for topic in self.published_counts
            ):
                self.publish_cctv_state()

        def matched_subscriptions(self):
            result = {
                f"/{robot_id}/robot_status": publisher.get_subscription_count()
                for robot_id, publisher in self._status_publishers.items()
            }
            result["/map"] = self._map_publisher.get_subscription_count()
            result.update({
                topic: publisher.get_subscription_count()
                for topic, publisher in self._image_publishers.items()
            })
            result.update({
                topic: publisher.get_subscription_count()
                for topic, publisher in self._costmap_publishers.items()
            })
            result.update({
                f"/{robot_id}/detection/event": publisher.get_subscription_count()
                for robot_id, publisher in self._detection_publishers.items()
            })
            result.update({
                f"/{robot_id}/detection/evidence": publisher.get_subscription_count()
                for robot_id, publisher in self._evidence_publishers.items()
            })
            result.update({
                (
                    "/vision/cctv/gate_event"
                    if camera_id == "gate_cam" else "/vision/cctv/center_event"
                ): publisher.get_subscription_count()
                for camera_id, publisher in self._cctv_publishers.items()
            })
            if self._permit_publisher is not None:
                result["/vision/cctv/patrol_allowed"] = (
                    self._permit_publisher.get_subscription_count()
                )
            result.update({
                f"/{robot_id}/patrol_visit": publisher.get_subscription_count()
                for robot_id, publisher in self._patrol_visit_publishers.items()
            })
            result.update({
                f"/{robot_id}/patrol_report": publisher.get_subscription_count()
                for robot_id, publisher in self._patrol_report_publishers.items()
            })
            result.update({
                f"/{robot_id}/keepout/status": publisher.get_subscription_count()
                for robot_id, publisher in self._keepout_publishers.items()
            })
            if self._estop_publisher is not None:
                result["/control/estop"] = self._estop_publisher.get_subscription_count()
            return dict(sorted(result.items()))

        def ack_publisher_matches(self):
            return {
                f"/{robot_id}/ingestion_ack": subscription.get_publisher_count()
                for robot_id, subscription in self._ack_subscriptions.items()
            }

    return VirtualPublisher()


def _spin_for(executor, seconds):
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        executor.spin_once(timeout_sec=min(0.1, remaining))


def run_virtual_publisher(config=None, log_dir=None):
    """별도 프로세스에서도 쓸 수 있게 가상 publisher만 유한 시간 실행한다."""
    config = config or RosTopicTestConfig()
    config.validate()
    dependencies = dependency_report()
    if not dependencies["ready"]:
        missing = [
            name for name, available in dependencies["dependencies"].items()
            if not available
        ]
        raise RosAdapterUnavailable(
            "가상 publisher 의존성이 없습니다: " + ", ".join(missing)
        )

    temporary = None
    if log_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="sysmon-ros-publisher-")
        log_dir = Path(temporary.name)
    else:
        log_dir = Path(log_dir)
    try:
        with _isolated_ros_environment(config.domain_id, log_dir):
            import rclpy
            from rclpy.executors import SingleThreadedExecutor

            if rclpy.ok():
                raise RuntimeError("이미 초기화된 rclpy context에서는 publisher를 시작할 수 없습니다.")
            rclpy.init(args=None)
            node = None
            executor = SingleThreadedExecutor()
            started = time.monotonic()
            try:
                node = build_virtual_publisher(config)
                executor.add_node(node)
                warmup = min(0.5, config.duration_seconds / 3.0)
                _spin_for(executor, warmup)
                node.publish_all()
                _spin_for(executor, config.duration_seconds - warmup)
                published = dict(sorted(node.published_counts.items()))
                matched = node.matched_subscriptions()
                ack_matches = node.ack_publisher_matches()
                received_acks = dict(sorted(node.received_acks.items()))
                elapsed = time.monotonic() - started
            finally:
                executor.shutdown()
                if node is not None:
                    node.destroy_node()
                if rclpy.ok():
                    rclpy.shutdown()
        return {
            "test_kind": "VIRTUAL_PUBLISHER_PROCESS",
            "config": asdict(config),
            "runtime_seconds": round(elapsed, 3),
            "published": published,
            "matched_subscriptions": matched,
            "ack_publisher_matches": ack_matches,
            "received_acks": received_acks,
        }
    finally:
        if temporary is not None:
            temporary.cleanup()


def _storage_report(app):
    with app.app_context():
        db = get_db()
        robot_ids = [
            row[0] for row in db.execute(
                "SELECT robot_id FROM robot_latest_status ORDER BY robot_id"
            )
        ]
        history_count = db.execute(
            "SELECT COUNT(*) FROM robot_status_history"
        ).fetchone()[0]
        map_count = db.execute("SELECT COUNT(*) FROM maps").fetchone()[0]
        costmap_sources = [
            f"{row[0]}:{row[1]}" for row in db.execute(
                "SELECT robot_id, layer FROM costmap_latest ORDER BY robot_id, layer"
            )
        ]
        detection_events = db.execute(
            "SELECT COUNT(*) FROM detection_event_messages"
        ).fetchone()[0]
        stored_evidence = db.execute(
            "SELECT COUNT(*) FROM evidence_ingestions WHERE status='STORED'"
        ).fetchone()[0]
        incomplete_evidence = db.execute(
            "SELECT COUNT(*) FROM evidence_ingestions WHERE status='INCOMPLETE'"
        ).fetchone()[0]
        evidence_links = db.execute(
            "SELECT COUNT(*) FROM event_evidence WHERE evidence_id IS NOT NULL"
        ).fetchone()[0]
        patrol_visits = db.execute("SELECT COUNT(*) FROM patrol_visits").fetchone()[0]
        patrol_reports = db.execute("SELECT COUNT(*) FROM patrol_runs").fetchone()[0]
        keepout_states = [
            f"{row[0]}:{row[1]}" for row in db.execute(
                "SELECT robot_id, state FROM keepout_latest ORDER BY robot_id"
            )
        ]
        estop_latest = db.execute(
            "SELECT active, reason_code FROM estop_latest WHERE singleton = 1"
        ).fetchone()
        estop_changes = db.execute("SELECT COUNT(*) FROM estop_history").fetchone()[0]
        chunk_payloads = db.execute(
            "SELECT COUNT(*) FROM evidence_chunks WHERE data IS NOT NULL"
        ).fetchone()[0]
        cctv_event_count = db.execute(
            "SELECT COUNT(*) FROM cctv_state_events"
        ).fetchone()[0]
        cctv_camera_ids = [
            row[0] for row in db.execute(
                "SELECT DISTINCT camera_id FROM cctv_state_events ORDER BY camera_id"
            )
        ]
        permit_latest = db.execute(
            "SELECT allowed, received_at FROM patrol_permit_latest WHERE singleton=1"
        ).fetchone()
        permit_history_count = db.execute(
            "SELECT COUNT(*) FROM patrol_permit_history"
        ).fetchone()[0]
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = len(db.execute("PRAGMA foreign_key_check").fetchall())
    frame_ids = sorted(
        path.stem
        for path in Path(app.config["VIDEO_DIR"]).glob("*.json")
    )
    return {
        "robot_latest_ids": robot_ids,
        "robot_status_history": history_count,
        "maps": map_count,
        "costmap_sources": costmap_sources,
        "detection_event_messages": detection_events,
        "stored_evidence": stored_evidence,
        "incomplete_evidence": incomplete_evidence,
        "evidence_links": evidence_links,
        "chunk_payloads_remaining": chunk_payloads,
        "patrol_visits": patrol_visits,
        "patrol_reports": patrol_reports,
        "keepout_states": keepout_states,
        "estop_latest": (
            {"active": bool(estop_latest[0]), "reason_code": estop_latest[1]}
            if estop_latest is not None else None
        ),
        "estop_changes": estop_changes,
        "cctv_state_events": cctv_event_count,
        "cctv_camera_ids": cctv_camera_ids,
        "patrol_permit_latest": (
            {"allowed": bool(permit_latest[0]), "received_at": permit_latest[1]}
            if permit_latest is not None else None
        ),
        "patrol_permit_history": permit_history_count,
        "camera_ids": frame_ids,
        "integrity_check": integrity,
        "foreign_key_errors": foreign_key_errors,
    }


def _dashboard_report(app, viewer_id):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = viewer_id
    paths = (
        "/api/robots/status",
        "/api/maps/current",
        "/api/cameras",
        "/api/costmaps",
        "/api/events",
        "/api/cctv/status",
        "/api/patrol/status",
        "/api/safety/status",
    )
    return {path: client.get(path).status_code for path in paths}


def run_local_ros_topic_test(config=None):
    """가상 publisher와 실제 adapter를 DDS로 연결하고 임시 저장 결과를 반환한다."""
    config = config or RosTopicTestConfig()
    config.validate()
    dependencies = dependency_report()
    if not dependencies["ready"]:
        missing = [
            name for name, available in dependencies["dependencies"].items()
            if not available
        ]
        raise RosAdapterUnavailable(
            "ROS topic 시험 의존성이 없습니다: " + ", ".join(missing)
        )

    temporary = tempfile.TemporaryDirectory(prefix="sysmon-ros-stage15-")
    root = Path(temporary.name)
    report = None
    try:
        app = _temporary_app(root)
        viewer_id = _create_viewer(app)
        with _isolated_ros_environment(config.domain_id, root / "ros_logs"):
            import rclpy
            from rclpy.executors import SingleThreadedExecutor

            if rclpy.ok():
                raise RuntimeError("이미 초기화된 rclpy context에서는 격리 시험을 시작할 수 없습니다.")
            rclpy.init(args=None)
            adapter = None
            publisher = None
            executor = SingleThreadedExecutor()
            started = time.monotonic()
            try:
                adapter = build_node(
                    app, node_name=f"sysmon_ros_adapter_test_{os.getpid()}"
                )
                publisher = build_virtual_publisher(config)
                executor.add_node(adapter)
                executor.add_node(publisher)
                warmup = min(0.5, config.duration_seconds / 3.0)
                _spin_for(executor, warmup)
                publisher.publish_all()
                _spin_for(executor, config.duration_seconds - warmup)
                _spin_for(executor, 0.2)
                elapsed = time.monotonic() - started
                published = dict(sorted(publisher.published_counts.items()))
                processed = dict(sorted(adapter.processing_counts.items()))
            finally:
                executor.shutdown()
                if publisher is not None:
                    publisher.destroy_node()
                if adapter is not None:
                    adapter.destroy_node()
                if rclpy.ok():
                    rclpy.shutdown()

        storage = _storage_report(app)
        dashboard = _dashboard_report(app, viewer_id)
        failures = sum(
            count for name, count in processed.items()
            if name.endswith("_failed") or name.endswith("_rejected")
        )
        local_pass = (
            set(storage["robot_latest_ids"]) == {"AMR1", "AMR2"}
            and storage["robot_status_history"] >= 2
            and storage["maps"] >= 1
            and set(storage["camera_ids"]) == {"amr1", "amr2", "webcam1", "webcam2"}
            and storage["integrity_check"] == "ok"
            and storage["foreign_key_errors"] == 0
            and all(status == 200 for status in dashboard.values())
            and failures == 0
            and (
                config.costmap_hz == 0
                or set(storage["costmap_sources"]) == {
                    "AMR1:global", "AMR1:local", "AMR2:global", "AMR2:local"
                }
            )
            and (
                config.cctv_hz == 0
                or (
                    storage["cctv_state_events"] >= 2
                    and set(storage["cctv_camera_ids"]) == {"gate_cam", "center_cam"}
                    and storage["patrol_permit_latest"] is not None
                    and storage["patrol_permit_history"] >= 2
                )
            )
        )
        report = {
            "stage": (
                19 if config.cctv_hz > 0
                else (18 if config.detection_hz > 0 else (17 if config.costmap_hz > 0 else 15))
            ),
            "test_kind": (
                "LOCAL_VIRTUAL_DDS_WITH_CCTV" if config.cctv_hz > 0
                else "LOCAL_VIRTUAL_DDS_WITH_DETECTION" if config.detection_hz > 0
                else ("LOCAL_VIRTUAL_DDS_WITH_COSTMAP" if config.costmap_hz > 0 else "LOCAL_VIRTUAL_DDS")
            ),
            "external_publishers": "NOT_RUN",
            "config": asdict(config),
            "runtime_seconds": round(elapsed, 3),
            "published": published,
            "processed": processed,
            "storage": storage,
            "dashboard_http": dashboard,
            "processing_failures": failures,
            "local_pass": local_pass,
            "scope_note": "localhost 전용 격리 도메인·임시 DB 시험이며 PC 간 통합시험이 아님",
        }
    finally:
        temporary.cleanup()
    report["temporary_storage_removed"] = not root.exists()
    return report
