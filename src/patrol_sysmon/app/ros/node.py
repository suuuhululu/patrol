"""구독 노드 생성과 실행. 수신한 메시지를 기존 서비스로 넘기고 결과를 회신한다."""

from collections import Counter
import time

from .errors import RosAdapterUnavailable, RosMessageMappingError
from .patrol_action import PatrolActionTracker
from .payloads import (
    battery_state_payload, camera_state_payload, compressed_image_input, estop_payload,
    occupancy_grid_payload, patrol_allowed_payload, patrol_feedback_payload,
    patrol_goal_status_payload, report_detection_payload,
)
from .qos import _qos_profiles
from .registry import (
    COSTMAP_SOURCES_BY_TOPIC, REPORT_DETECTION_SERVICE,
    active_subscriptions, dependency_report,
)


def build_node(app, node_name="sysmon_ros_adapter"):
    """의존성이 준비된 환경에서 실제 구독 노드를 만든다."""
    report = dependency_report()
    if not report["ready"]:
        missing = ", ".join(
            name for name, available in report["dependencies"].items() if not available
        )
        raise RosAdapterUnavailable(f"ROS adapter 의존성이 없습니다: {missing}")

    from action_msgs.msg import GoalStatusArray
    from nav_msgs.msg import OccupancyGrid
    from patrol_interfaces.action import Patrol
    from patrol_interfaces.msg import CameraState, EStop
    from rclpy.node import Node
    try:
        from patrol_interfaces.srv import ReportDetection
    except ImportError:
        # [구버전 빌드] srv 없이 빌드한 patrol_interfaces면 토픽 수신만 하고 서비스는 띄우지 않는다.
        ReportDetection = None
    from sensor_msgs.msg import BatteryState, CompressedImage
    from std_msgs.msg import Bool

    from ..models.costmap import CostmapMessageConflictError, StaleCostmapError
    from ..models.cctv import CctvEventConflictError
    from ..models.patrol import PatrolConflictError
    from ..models.detection import DetectionMessageConflictError
    from ..models.map import MapMessageConflictError, StaleMapError
    from ..models.robot import MessageIdConflictError, StaleStatusError
    from ..services import (
        camera_service, costmap_service, cctv_service, detection_service,
        patrol_service, safety_service,
        map_service, robot_service,
    )
    from ..services.camera_service import CameraFrameConflictError, StaleCameraFrameError

    qos = _qos_profiles()

    class SysmonRosAdapter(Node):
        def __init__(self):
            super().__init__(node_name)
            self._app = app
            # [계약 2.5절] 표시용 영상은 최대 5 Hz까지만 처리한다.
            # 카메라가 더 빨리 발행해도 파일 교체와 다른 callback을 밀어내지 않게 버린다.
            max_hz = app.config.get("CAMERA_MAX_HZ", 5.0)
            self._camera_min_interval = 1.0 / max_hz if max_hz else 0.0
            # 토픽별 다음 처리 예정 시각. 직전 처리 시각이 아니라 일정표 기준으로 센다.
            self._camera_next_due = {}
            self.processing_counts = Counter()
            # [v2 로봇 상태] Action 피드백·상태와 배터리를 합쳐 로봇 상태·방문·결과를 만든다.
            self._patrol_tracker = PatrolActionTracker()
            for spec in active_subscriptions():
                if spec.handler == "patrol_feedback":
                    self.create_subscription(
                        Patrol.Impl.FeedbackMessage, spec.topic,
                        lambda message, topic=spec.topic: self._receive_patrol_feedback(topic, message),
                        qos["patrol_feedback"],
                    )
                elif spec.handler == "patrol_goal_status":
                    self.create_subscription(
                        GoalStatusArray, spec.topic,
                        lambda message, topic=spec.topic: self._receive_patrol_status(topic, message),
                        qos["patrol_goal_status"],
                    )
                elif spec.handler == "battery_state":
                    self.create_subscription(
                        BatteryState, spec.topic,
                        lambda message, topic=spec.topic: self._receive_battery(topic, message),
                        qos["battery_state"],
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
                # [주기 제한] "직전 처리 뒤 0.2초 미만이면 버림"은 5 Hz 카메라가 조금만 일찍 와도
                # 한 장씩 걸러 2.5 Hz가 된다. 0.2초 간격 일정표에 맞춰, 예정보다 간격의 25%까지
                # 이른 프레임은 받는다. 받을 때마다 예정 시각을 한 칸씩 미루므로 평균은 5 Hz를 넘지 않는다.
                interval = self._camera_min_interval
                now = time.monotonic()
                due = self._camera_next_due.get(topic)
                if due is not None and now < due - interval * 0.25:
                    self.processing_counts["camera_frame_throttled"] += 1
                    return
                # 오래 끊겼다가 오면 밀린 몫을 몰아 받지 않도록 지금 기준으로 다시 시작한다.
                self._camera_next_due[topic] = (
                    due if due is not None and now - due < interval else now
                ) + interval
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

        def _store_patrol_outputs(self, outputs, label):
            """추적기가 만든 상태 행·방문·결과를 기존 저장 서비스로 넘긴다. 한 건 실패가 나머지를 막지 않는다."""
            handlers = {
                "status": robot_service.receive_status,
                "visit": patrol_service.receive_visit,
                "report": patrol_service.receive_action_result,
            }
            for kind, payload in outputs:
                try:
                    with self._app.app_context():
                        outcome, _ = handlers[kind](payload)
                    self.processing_counts[f"{kind}_{outcome}"] += 1
                except (
                    robot_service.StatusValidationError, MessageIdConflictError, StaleStatusError,
                    patrol_service.PatrolValidationError, PatrolConflictError,
                ) as exc:
                    self.processing_counts[f"{kind}_rejected"] += 1
                    self.get_logger().warning(f"{label} {kind} 저장 거부: {exc}")
                except Exception as exc:
                    self.processing_counts[f"{kind}_failed"] += 1
                    self.get_logger().error(f"{label} {kind} 저장 실패: {exc}")

        def _receive_patrol_feedback(self, topic, message):
            try:
                payload = patrol_feedback_payload(topic, message)
            except RosMessageMappingError as exc:
                self.processing_counts["patrol_feedback_rejected"] += 1
                self.get_logger().warning(f"Patrol 피드백 거부: {exc}")
                return
            self._store_patrol_outputs(self._patrol_tracker.on_feedback(payload), "Patrol 피드백")

        def _receive_patrol_status(self, topic, message):
            try:
                payload = patrol_goal_status_payload(topic, message)
            except RosMessageMappingError as exc:
                self.processing_counts["patrol_status_rejected"] += 1
                self.get_logger().warning(f"Patrol 목표 상태 거부: {exc}")
                return
            self._store_patrol_outputs(self._patrol_tracker.on_goal_status(payload), "Patrol 목표 상태")

        def _receive_battery(self, topic, message):
            try:
                payload = battery_state_payload(topic, message)
            except RosMessageMappingError as exc:
                self.processing_counts["battery_rejected"] += 1
                self.get_logger().warning(f"battery_state 거부: {exc}")
                return
            self._store_patrol_outputs(self._patrol_tracker.on_battery(payload), "battery_state")

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
