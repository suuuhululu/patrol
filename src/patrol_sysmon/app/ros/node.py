"""구독 노드 생성과 실행. 수신한 메시지를 기존 서비스로 넘기고 결과를 회신한다."""

from collections import Counter
import time
import uuid

from .errors import RosAdapterUnavailable, RosMessageMappingError
from .payloads import (
    camera_state_payload, compressed_image_input, report_detection_payload,
    detection_event_payload, estop_payload, evidence_chunk_payload,
    keepout_status_payload, occupancy_grid_payload, patrol_allowed_payload,
    patrol_report_payload, patrol_visit_payload, robot_status_payload,
)
from .qos import _qos_profiles
from .registry import (
    COSTMAP_SOURCES_BY_TOPIC,
    EVIDENCE_SOURCES_BY_TOPIC,
    PATROL_REPORT_SOURCES_BY_TOPIC,
    ROBOT_DISPLAY_IDS, REPORT_DETECTION_SERVICE,
    CAMERA_STATE_SOURCES_BY_TOPIC, COSTMAP_SOURCES_BY_TOPIC,
    DETECTION_SOURCES_BY_TOPIC, EVIDENCE_SOURCES_BY_TOPIC,
    KEEPOUT_SOURCES_BY_TOPIC, PATROL_REPORT_SOURCES_BY_TOPIC,
    PATROL_VISIT_SOURCES_BY_TOPIC, active_subscriptions, dependency_report,
)


def build_node(app, node_name="sysmon_ros_adapter"):
    """의존성이 준비된 환경에서 실제 구독 노드를 만든다."""
    report = dependency_report()
    if not report["ready"]:
        missing = ", ".join(
            name for name, available in report["dependencies"].items() if not available
        )
        raise RosAdapterUnavailable(f"ROS adapter 의존성이 없습니다: {missing}")

    from nav_msgs.msg import OccupancyGrid
    from patrol_interfaces.msg import (
        CameraState, DetectionEvent, EStop, EvidenceChunk, IngestionAck,
        KeepoutStatus, PatrolReport, PatrolVisit, RobotStatus,
    )
    from rclpy.node import Node
    try:
        from patrol_interfaces.srv import ReportDetection
    except ImportError:
        # [구버전 빌드] srv 없이 빌드한 patrol_interfaces면 토픽 수신만 하고 서비스는 띄우지 않는다.
        ReportDetection = None
    from sensor_msgs.msg import CompressedImage
    from std_msgs.msg import Bool

    from ..models.costmap import CostmapMessageConflictError, StaleCostmapError
    from ..models.cctv import CctvEventConflictError
    from ..models.patrol import PatrolConflictError
    from ..models.detection import DetectionMessageConflictError, EvidenceRejectedError
    from ..models.map import MapMessageConflictError, StaleMapError
    from ..models.robot import MessageIdConflictError, StaleStatusError
    from ..services import (
        camera_service, costmap_service, cctv_service, detection_service,
        patrol_service, safety_service,
        map_service, robot_service,
    )
    from ..services.camera_service import CameraFrameConflictError, StaleCameraFrameError
    from ..services.event_service import EvidenceValidationError

    qos = _qos_profiles()

    class SysmonRosAdapter(Node):
        def __init__(self):
            super().__init__(node_name)
            self._app = app
            # [계약 2.5절] 표시용 영상은 최대 5 Hz까지만 처리한다.
            # 카메라가 더 빨리 발행해도 파일 교체와 다른 callback을 밀어내지 않게 버린다.
            max_hz = app.config.get("CAMERA_MAX_HZ", 5.0)
            self._camera_min_interval = 1.0 / max_hz if max_hz else 0.0
            self._camera_last_processed = {}
            self.processing_counts = Counter()
            self._ack_publishers = {
                robot_id: self.create_publisher(
                    IngestionAck, f"/{robot_id}/ingestion_ack", qos["ingestion_ack"]
                )
                for robot_id in ROBOT_DISPLAY_IDS
            }
            for spec in active_subscriptions():
                if spec.handler == "robot_status":
                    self.create_subscription(
                        RobotStatus, spec.topic, self._receive_robot_status,
                        qos["robot_status"],
                    )
                elif spec.handler == "map":
                    self.create_subscription(
                        OccupancyGrid, spec.topic, self._receive_map, qos["map"],
                    )
                elif spec.handler == "camera_frame":
                    self.create_subscription(
                        CompressedImage, spec.topic,
                        lambda message, topic=spec.topic: self._receive_camera(topic, message),
                        qos["camera_frame"],
                    )
                elif spec.handler == "costmap":
                    self.create_subscription(
                        OccupancyGrid, spec.topic,
                        lambda message, topic=spec.topic: self._receive_costmap(topic, message),
                        qos["costmap"],
                    )
                elif spec.handler == "detection_event":
                    self.create_subscription(
                        DetectionEvent, spec.topic,
                        lambda message, topic=spec.topic: self._receive_detection(topic, message),
                        qos["detection_event"],
                    )
                elif spec.handler == "evidence_chunk":
                    self.create_subscription(
                        EvidenceChunk, spec.topic,
                        lambda message, topic=spec.topic: self._receive_evidence(topic, message),
                        qos["evidence_chunk"],
                    )
                elif spec.handler == "camera_state":
                    self.create_subscription(
                        CameraState, spec.topic,
                        lambda message, topic=spec.topic: self._receive_camera_state(topic, message),
                        qos["camera_state"],
                    )
                elif spec.handler == "patrol_allowed":
                    self.create_subscription(
                        Bool, spec.topic, self._receive_patrol_allowed,
                        qos["patrol_allowed"],
                    )
                elif spec.handler == "patrol_visit":
                    self.create_subscription(
                        PatrolVisit, spec.topic,
                        lambda message, topic=spec.topic: self._receive_patrol_visit(topic, message),
                        qos["patrol_visit"],
                    )
                elif spec.handler == "patrol_report":
                    self.create_subscription(
                        PatrolReport, spec.topic,
                        lambda message, topic=spec.topic: self._receive_patrol_report(topic, message),
                        qos["patrol_report"],
                    )
                elif spec.handler == "keepout_status":
                    self.create_subscription(
                        KeepoutStatus, spec.topic,
                        lambda message, topic=spec.topic: self._receive_keepout(topic, message),
                        qos["keepout_status"],
                    )
                elif spec.handler == "estop":
                    self.create_subscription(
                        EStop, spec.topic, self._receive_estop, qos["estop"],
                    )
            # [ReportDetection] 확정 사건 + 사진을 서비스 한 번으로 받는다. 응답이 곧 저장 결과다.
            self._report_service = None
            if ReportDetection is not None:
                self._report_service = self.create_service(
                    ReportDetection, REPORT_DETECTION_SERVICE, self._handle_report_detection
                )
            self.get_logger().info(
                f"sysmon ROS adapter 구독 준비: {len(active_subscriptions())}개"
                + (f" · 서비스 {REPORT_DETECTION_SERVICE}" if self._report_service else
                   " · ReportDetection 서비스 없음(patrol_interfaces를 srv 포함으로 재빌드)")
            )

        def _handle_report_detection(self, request, response):
            """요청 5개 필드를 검증·저장하고 status·detail로 결과를 돌려준다."""
            try:
                payload = report_detection_payload(request)
                with self._app.app_context():
                    outcome, stored = detection_service.receive_report(payload)
                response.status = (
                    ReportDetection.Response.DUPLICATE if outcome == "duplicate"
                    else ReportDetection.Response.STORED
                )
                response.detail = str(stored.get("detail", ""))[:240]
                if stored.get("suppressed_by"):
                    outcome = "suppressed"
                self.processing_counts[f"report_detection_{outcome}"] += 1
            except (
                RosMessageMappingError, detection_service.DetectionValidationError,
                DetectionMessageConflictError,
            ) as exc:
                response.status = ReportDetection.Response.REJECTED
                response.detail = str(exc)[:240]
                self.processing_counts["report_detection_rejected"] += 1
                self.get_logger().warning(f"ReportDetection 거부: {exc}")
            except Exception as exc:
                response.status = ReportDetection.Response.REJECTED
                response.detail = "storage failure"
                self.processing_counts["report_detection_failed"] += 1
                self.get_logger().error(f"ReportDetection 처리 실패: {exc}")
            return response

        def _receive_robot_status(self, message):
            try:
                with self._app.app_context():
                    outcome, _ = robot_service.receive_status(
                        robot_status_payload(message)
                    )
                self.processing_counts[f"robot_status_{outcome}"] += 1
            except (RosMessageMappingError, MessageIdConflictError, StaleStatusError) as exc:
                self.processing_counts["robot_status_rejected"] += 1
                self.get_logger().warning(f"RobotStatus 처리 거부: {exc}")
            except Exception as exc:
                self.processing_counts["robot_status_failed"] += 1
                self.get_logger().error(f"RobotStatus 처리 실패: {exc}")

        def _receive_map(self, message):
            try:
                with self._app.app_context():
                    outcome, _ = map_service.receive_map(
                        occupancy_grid_payload(message)
                    )
                self.processing_counts[f"map_{outcome}"] += 1
            except (RosMessageMappingError, MapMessageConflictError, StaleMapError) as exc:
                self.processing_counts["map_rejected"] += 1
                self.get_logger().warning(f"OccupancyGrid 처리 거부: {exc}")
            except Exception as exc:
                self.processing_counts["map_failed"] += 1
                self.get_logger().error(f"OccupancyGrid 처리 실패: {exc}")

        def _receive_camera(self, topic, message):
            if self._camera_min_interval:
                now = time.monotonic()
                last = self._camera_last_processed.get(topic)
                if last is not None and now - last < self._camera_min_interval:
                    self.processing_counts["camera_frame_throttled"] += 1
                    return
                self._camera_last_processed[topic] = now
            try:
                camera_id, frame_id, captured_at, image_stream = compressed_image_input(
                    topic, message
                )
                with self._app.app_context():
                    outcome, _ = camera_service.receive_frame(
                        camera_id, frame_id, captured_at, image_stream
                    )
                self.processing_counts[f"camera_frame_{outcome}"] += 1
            except (
                RosMessageMappingError,
                camera_service.CameraValidationError,
                CameraFrameConflictError,
                StaleCameraFrameError,
            ) as exc:
                self.processing_counts["camera_frame_rejected"] += 1
                self.get_logger().warning(f"CompressedImage 처리 거부: {exc}")
            except Exception as exc:
                self.processing_counts["camera_frame_failed"] += 1
                self.get_logger().error(f"CompressedImage 처리 실패: {exc}")

        def _receive_costmap(self, topic, message):
            try:
                robot_id, layer = COSTMAP_SOURCES_BY_TOPIC[topic]
                with self._app.app_context():
                    outcome, _ = costmap_service.receive_costmap(
                        robot_id, layer, occupancy_grid_payload(message)
                    )
                self.processing_counts[f"costmap_{outcome}"] += 1
            except (
                KeyError, RosMessageMappingError, map_service.MapValidationError,
                costmap_service.CostmapValidationError,
                CostmapMessageConflictError, StaleCostmapError,
            ) as exc:
                self.processing_counts["costmap_rejected"] += 1
                self.get_logger().warning(f"Costmap 처리 거부: {exc}")
            except Exception as exc:
                self.processing_counts["costmap_failed"] += 1
                self.get_logger().error(f"Costmap 처리 실패: {exc}")

        def _publish_ingestion_ack(
            self, contract_robot, entity_type, source_message_id,
            entity_id, status, missing_chunks=(), detail="",
        ):
            ack = IngestionAck()
            ack.header.stamp = self.get_clock().now().to_msg()
            ack.header.frame_id = ""
            ack.message_id = str(uuid.uuid4())
            ack.robot_id = contract_robot
            ack.entity_type = entity_type
            ack.source_message_id = source_message_id if isinstance(source_message_id, str) else ""
            ack.entity_id = entity_id if isinstance(entity_id, str) else ""
            ack.status = status
            ack.missing_chunks = list(missing_chunks)
            ack.detail = str(detail)[:240]
            self._ack_publishers[contract_robot].publish(ack)
            self.processing_counts[f"ingestion_ack_{status}"] += 1

        def _receive_detection(self, topic, message):
            contract_robot = DETECTION_SOURCES_BY_TOPIC[topic]
            try:
                payload = detection_event_payload(topic, message)
                with self._app.app_context():
                    outcome, stored = detection_service.receive_detection(payload)
                ack_status = (
                    IngestionAck.DUPLICATE if outcome == "duplicate" else IngestionAck.STORED
                )
                self.processing_counts[f"detection_event_{outcome}"] += 1
                self._publish_ingestion_ack(
                    contract_robot, IngestionAck.DETECTION_EVENT,
                    payload["message_id"], stored["event_id"], ack_status,
                    detail=outcome,
                )
            except (
                RosMessageMappingError, detection_service.DetectionValidationError,
                DetectionMessageConflictError,
            ) as exc:
                self.processing_counts["detection_event_rejected"] += 1
                self.get_logger().warning(f"DetectionEvent 처리 거부: {exc}")
                self._publish_ingestion_ack(
                    contract_robot, IngestionAck.DETECTION_EVENT,
                    getattr(message, "message_id", ""), getattr(message, "event_id", ""),
                    IngestionAck.REJECTED, detail=exc,
                )
            except Exception as exc:
                self.processing_counts["detection_event_failed"] += 1
                self.get_logger().error(f"DetectionEvent 처리 실패: {exc}")
                self._publish_ingestion_ack(
                    contract_robot, IngestionAck.DETECTION_EVENT,
                    getattr(message, "message_id", ""), getattr(message, "event_id", ""),
                    IngestionAck.REJECTED, detail="storage failure",
                )

        def _receive_evidence(self, topic, message):
            contract_robot = EVIDENCE_SOURCES_BY_TOPIC[topic]
            try:
                payload = evidence_chunk_payload(topic, message)
                with self._app.app_context():
                    outcome, stored = detection_service.receive_evidence_chunk(payload)
                ack_status = {
                    "stored": IngestionAck.STORED,
                    "duplicate": IngestionAck.DUPLICATE,
                    "incomplete": IngestionAck.INCOMPLETE,
                }[outcome]
                self.processing_counts[f"evidence_chunk_{outcome}"] += 1
                self._publish_ingestion_ack(
                    contract_robot, IngestionAck.EVIDENCE,
                    payload["message_id"], payload["evidence_id"], ack_status,
                    missing_chunks=stored["missing_chunks"], detail=outcome,
                )
            except (
                RosMessageMappingError, detection_service.DetectionValidationError,
                DetectionMessageConflictError, EvidenceRejectedError,
                EvidenceValidationError,
            ) as exc:
                self.processing_counts["evidence_chunk_rejected"] += 1
                self.get_logger().warning(f"EvidenceChunk 처리 거부: {exc}")
                self._publish_ingestion_ack(
                    contract_robot, IngestionAck.EVIDENCE,
                    getattr(message, "message_id", ""), getattr(message, "evidence_id", ""),
                    IngestionAck.REJECTED, detail=exc,
                )
            except Exception as exc:
                self.processing_counts["evidence_chunk_failed"] += 1
                self.get_logger().error(f"EvidenceChunk 처리 실패: {exc}")
                self._publish_ingestion_ack(
                    contract_robot, IngestionAck.EVIDENCE,
                    getattr(message, "message_id", ""), getattr(message, "evidence_id", ""),
                    IngestionAck.REJECTED, detail="storage failure",
                )

        def _receive_camera_state(self, topic, message):
            try:
                payload = camera_state_payload(topic, message)
                with self._app.app_context():
                    outcome, _ = cctv_service.receive_camera_state(payload)
                self.processing_counts[f"camera_state_{outcome}"] += 1
            except (
                RosMessageMappingError, cctv_service.CctvValidationError,
                CctvEventConflictError,
            ) as exc:
                self.processing_counts["camera_state_rejected"] += 1
                self.get_logger().warning(f"CameraState 처리 거부: {exc}")
            except Exception as exc:
                self.processing_counts["camera_state_failed"] += 1
                self.get_logger().error(f"CameraState 처리 실패: {exc}")

        def _receive_patrol_allowed(self, message):
            try:
                with self._app.app_context():
                    outcome = cctv_service.receive_patrol_allowed(
                        patrol_allowed_payload(message)
                    )
                self.processing_counts[f"patrol_allowed_{outcome}"] += 1
            except (RosMessageMappingError, cctv_service.CctvValidationError) as exc:
                self.processing_counts["patrol_allowed_rejected"] += 1
                self.get_logger().warning(f"patrol_allowed 처리 거부: {exc}")
            except Exception as exc:
                self.processing_counts["patrol_allowed_failed"] += 1
                self.get_logger().error(f"patrol_allowed 처리 실패: {exc}")

        def _receive_patrol_visit(self, topic, message):
            # [재전송 종료] 방문 보고는 ACK를 받을 때까지 재전송되므로 결과를 반드시 회신한다.
            contract_robot = PATROL_VISIT_SOURCES_BY_TOPIC[topic]
            try:
                payload = patrol_visit_payload(topic, message)
                with self._app.app_context():
                    outcome, stored = patrol_service.receive_visit(payload)
                ack_status = (
                    IngestionAck.DUPLICATE if outcome == "duplicate" else IngestionAck.STORED
                )
                self.processing_counts[f"patrol_visit_{outcome}"] += 1
                self._publish_ingestion_ack(
                    contract_robot, IngestionAck.PATROL_VISIT,
                    payload["message_id"], stored["visit_id"], ack_status, detail=outcome,
                )
            except (
                RosMessageMappingError, patrol_service.PatrolValidationError,
                PatrolConflictError,
            ) as exc:
                self.processing_counts["patrol_visit_rejected"] += 1
                self.get_logger().warning(f"PatrolVisit 처리 거부: {exc}")
                self._publish_ingestion_ack(
                    contract_robot, IngestionAck.PATROL_VISIT,
                    getattr(message, "message_id", ""), getattr(message, "visit_id", ""),
                    IngestionAck.REJECTED, detail=exc,
                )
            except Exception as exc:
                self.processing_counts["patrol_visit_failed"] += 1
                self.get_logger().error(f"PatrolVisit 처리 실패: {exc}")
                self._publish_ingestion_ack(
                    contract_robot, IngestionAck.PATROL_VISIT,
                    getattr(message, "message_id", ""), getattr(message, "visit_id", ""),
                    IngestionAck.REJECTED, detail="storage failure",
                )

        def _receive_patrol_report(self, topic, message):
            contract_robot = PATROL_REPORT_SOURCES_BY_TOPIC[topic]
            try:
                payload = patrol_report_payload(topic, message)
                with self._app.app_context():
                    outcome, stored = patrol_service.receive_report(payload)
                ack_status = (
                    IngestionAck.DUPLICATE if outcome == "duplicate" else IngestionAck.STORED
                )
                self.processing_counts[f"patrol_report_{outcome}"] += 1
                self._publish_ingestion_ack(
                    contract_robot, IngestionAck.PATROL_REPORT,
                    payload["message_id"], stored["patrol_id"], ack_status, detail=outcome,
                )
            except (
                RosMessageMappingError, patrol_service.PatrolValidationError,
                PatrolConflictError,
            ) as exc:
                self.processing_counts["patrol_report_rejected"] += 1
                self.get_logger().warning(f"PatrolReport 처리 거부: {exc}")
                self._publish_ingestion_ack(
                    contract_robot, IngestionAck.PATROL_REPORT,
                    getattr(message, "message_id", ""), getattr(message, "report_id", ""),
                    IngestionAck.REJECTED, detail=exc,
                )
            except Exception as exc:
                self.processing_counts["patrol_report_failed"] += 1
                self.get_logger().error(f"PatrolReport 처리 실패: {exc}")
                self._publish_ingestion_ack(
                    contract_robot, IngestionAck.PATROL_REPORT,
                    getattr(message, "message_id", ""), getattr(message, "report_id", ""),
                    IngestionAck.REJECTED, detail="storage failure",
                )

        def _receive_keepout(self, topic, message):
            # [상태 관측] Keepout 변경은 costmap parameter API가 수행하고 관제는 결과만 본다.
            try:
                with self._app.app_context():
                    outcome, _ = safety_service.receive_keepout(
                        keepout_status_payload(topic, message)
                    )
                self.processing_counts[f"keepout_{outcome}"] += 1
            except (RosMessageMappingError, safety_service.SafetyValidationError) as exc:
                self.processing_counts["keepout_rejected"] += 1
                self.get_logger().warning(f"KeepoutStatus 처리 거부: {exc}")
            except Exception as exc:
                self.processing_counts["keepout_failed"] += 1
                self.get_logger().error(f"KeepoutStatus 처리 실패: {exc}")

        def _receive_estop(self, message):
            # [안전 관측] E-stop 해제는 이동 명령이 아니므로 관제는 상태만 기록한다.
            try:
                with self._app.app_context():
                    outcome, _ = safety_service.receive_estop(estop_payload(message))
                self.processing_counts[f"estop_{outcome}"] += 1
            except (RosMessageMappingError, safety_service.SafetyValidationError) as exc:
                self.processing_counts["estop_rejected"] += 1
                self.get_logger().warning(f"EStop 처리 거부: {exc}")
            except Exception as exc:
                self.processing_counts["estop_failed"] += 1
                self.get_logger().error(f"EStop 처리 실패: {exc}")

        def ack_publisher_matches(self):
            return {
                f"/{robot_id}/ingestion_ack": publisher.get_subscription_count()
                for robot_id, publisher in self._ack_publishers.items()
            }

    return SysmonRosAdapter()


def spin(app):
    """웹 서버와 분리된 프로세스에서 ROS callback을 실행한다."""
    report = dependency_report()
    if not report["ready"]:
        missing = ", ".join(
            name for name, available in report["dependencies"].items() if not available
        )
        raise RosAdapterUnavailable(f"ROS adapter 의존성이 없습니다: {missing}")
    import rclpy

    rclpy.init(args=None)
    node = None
    try:
        node = build_node(app)
        rclpy.spin(node)
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
