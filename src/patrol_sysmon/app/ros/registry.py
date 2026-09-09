"""구독 토픽 등록표와 계약 enum 대응표.

토픽·타입이 바뀌면 실행 코드가 아니라 이 표만 고친다.
"""

from dataclasses import dataclass
import importlib


@dataclass(frozen=True)
class SubscriptionSpec:
    """토픽 변경이 생겨도 실행 코드가 아니라 등록표 한곳만 고치도록 한다."""

    key: str
    topic: str
    type_name: str
    handler: str
    active: bool


SUBSCRIPTIONS = (
    SubscriptionSpec(
        "robot1_status", "/robot1/robot_status",
        "patrol_interfaces/msg/RobotStatus", "robot_status", True,
    ),
    SubscriptionSpec(
        "robot6_status", "/robot6/robot_status",
        "patrol_interfaces/msg/RobotStatus", "robot_status", True,
    ),
    SubscriptionSpec(
        "map", "/map", "nav_msgs/msg/OccupancyGrid", "map", True,
    ),
    SubscriptionSpec(
        "robot1_image", "/robot1/oakd/image/compressed",
        "sensor_msgs/msg/CompressedImage", "camera_frame", True,
    ),
    SubscriptionSpec(
        "robot6_image", "/robot6/oakd/image/compressed",
        "sensor_msgs/msg/CompressedImage", "camera_frame", True,
    ),
    SubscriptionSpec(
        "gate_image", "/vision/cctv/gate_image/compressed",
        "sensor_msgs/msg/CompressedImage", "camera_frame", True,
    ),
    SubscriptionSpec(
        "center_image", "/vision/cctv/center_image/compressed",
        "sensor_msgs/msg/CompressedImage", "camera_frame", True,
    ),
    SubscriptionSpec(
        "robot1_global_costmap", "/robot1/global_costmap/costmap",
        "nav_msgs/msg/OccupancyGrid", "costmap", True,
    ),
    SubscriptionSpec(
        "robot1_local_costmap", "/robot1/local_costmap/costmap",
        "nav_msgs/msg/OccupancyGrid", "costmap", True,
    ),
    SubscriptionSpec(
        "robot6_global_costmap", "/robot6/global_costmap/costmap",
        "nav_msgs/msg/OccupancyGrid", "costmap", True,
    ),
    SubscriptionSpec(
        "robot6_local_costmap", "/robot6/local_costmap/costmap",
        "nav_msgs/msg/OccupancyGrid", "costmap", True,
    ),
    SubscriptionSpec(
        "robot1_detection", "/robot1/detection/event",
        "patrol_interfaces/msg/DetectionEvent", "detection_event", True,
    ),
    SubscriptionSpec(
        "robot6_detection", "/robot6/detection/event",
        "patrol_interfaces/msg/DetectionEvent", "detection_event", True,
    ),
    SubscriptionSpec(
        "robot1_evidence", "/robot1/detection/evidence",
        "patrol_interfaces/msg/EvidenceChunk", "evidence_chunk", True,
    ),
    SubscriptionSpec(
        "robot6_evidence", "/robot6/detection/evidence",
        "patrol_interfaces/msg/EvidenceChunk", "evidence_chunk", True,
    ),
    SubscriptionSpec(
        "gate_event", "/vision/cctv/gate_event",
        "patrol_interfaces/msg/CameraState", "camera_state", True,
    ),
    SubscriptionSpec(
        "center_event", "/vision/cctv/center_event",
        "patrol_interfaces/msg/CameraState", "camera_state", True,
    ),
    SubscriptionSpec(
        "patrol_allowed", "/vision/cctv/patrol_allowed",
        "std_msgs/msg/Bool", "patrol_allowed", True,
    ),
    SubscriptionSpec(
        "robot1_patrol_visit", "/robot1/patrol_visit",
        "patrol_interfaces/msg/PatrolVisit", "patrol_visit", True,
    ),
    SubscriptionSpec(
        "robot6_patrol_visit", "/robot6/patrol_visit",
        "patrol_interfaces/msg/PatrolVisit", "patrol_visit", True,
    ),
    SubscriptionSpec(
        "robot1_patrol_report", "/robot1/patrol_report",
        "patrol_interfaces/msg/PatrolReport", "patrol_report", True,
    ),
    SubscriptionSpec(
        "robot6_patrol_report", "/robot6/patrol_report",
        "patrol_interfaces/msg/PatrolReport", "patrol_report", True,
    ),
    SubscriptionSpec(
        "robot1_keepout", "/robot1/keepout/status",
        "patrol_interfaces/msg/KeepoutStatus", "keepout_status", True,
    ),
    SubscriptionSpec(
        "robot6_keepout", "/robot6/keepout/status",
        "patrol_interfaces/msg/KeepoutStatus", "keepout_status", True,
    ),
    SubscriptionSpec(
        "estop", "/control/estop",
        "patrol_interfaces/msg/EStop", "estop", True,
    ),
)

ROBOT_DISPLAY_IDS = {"robot1": "AMR1", "robot6": "AMR2"}
# [ReportDetection] 확정 사건·증거 사진을 서비스 한 번으로 받는다. System monitor가 서버다.
REPORT_DETECTION_SERVICE = "/system_monitor/report_detection"
MISSION_STATES = {
    0: "IDLE",
    1: "UNDOCKING",
    2: "PATROLLING",
    3: "MOVING_TO_SAFE_ZONE",
    4: "WAITING_SAFE_ZONE",
    5: "RETURNING_TO_DOCK",
    6: "DOCKING",
    7: "PAUSED",
    8: "COMPLETED",
    9: "FAILED",
    10: "CANCELED",
}
# [계약] interfaces.md 4절 safety_state (2026-09-08 결정). 이름은 계약 표를 그대로 옮긴다.
SAFETY_STATES = {
    0: "UNKNOWN",
    1: "NORMAL",
    2: "STOPPING",
    3: "STOPPED",
    4: "ESTOPPED",
    5: "ERROR",
}
# [계약] interfaces.md 3.1절 EStop reason과 대상 값. UI가 원인 집합을 직접 계산하지 않는다.
ESTOP_REASONS = {
    0: "UNKNOWN",
    1: "OPERATOR",
    2: "COMMUNICATION",
    3: "TOKEN",
    4: "OBSTACLE",
    5: "KEEPOUT_FAILURE",
    6: "SYSTEM_FAULT",
}
ESTOP_TARGETS = ("robot1", "robot6", "all")
CAMERA_IDS_BY_TOPIC = {
    "/robot1/oakd/image/compressed": "amr1",
    "/robot6/oakd/image/compressed": "amr2",
    "/vision/cctv/gate_image/compressed": "webcam1",
    "/vision/cctv/center_image/compressed": "webcam2",
}
COSTMAP_SOURCES_BY_TOPIC = {
    "/robot1/global_costmap/costmap": ("AMR1", "global"),
    "/robot1/local_costmap/costmap": ("AMR1", "local"),
    "/robot6/global_costmap/costmap": ("AMR2", "global"),
    "/robot6/local_costmap/costmap": ("AMR2", "local"),
}
DETECTION_SOURCES_BY_TOPIC = {
    "/robot1/detection/event": "robot1",
    "/robot6/detection/event": "robot6",
}
EVIDENCE_SOURCES_BY_TOPIC = {
    "/robot1/detection/evidence": "robot1",
    "/robot6/detection/evidence": "robot6",
}
DETECTION_EVENT_TYPES = {
    1: "FIRE", 2: "LEAK", 3: "OBSTACLE",
    4: "LIGHTING", 5: "FACILITY_DAMAGE",
}
DETECTION_RISK_LEVELS = {1: "LOW", 2: "MEDIUM", 3: "HIGH"}
PATROL_VISIT_SOURCES_BY_TOPIC = {
    "/robot1/patrol_visit": "robot1",
    "/robot6/patrol_visit": "robot6",
}
PATROL_REPORT_SOURCES_BY_TOPIC = {
    "/robot1/patrol_report": "robot1",
    "/robot6/patrol_report": "robot6",
}
KEEPOUT_SOURCES_BY_TOPIC = {
    "/robot1/keepout/status": "robot1",
    "/robot6/keepout/status": "robot6",
}
PATROL_VISIT_RESULTS = {0: "SUCCEEDED", 1: "SKIPPED", 2: "FAILED"}
PATROL_REPORT_RESULTS = {0: "SUCCEEDED", 1: "FAILED", 2: "CANCELED"}
KEEPOUT_STATES = {
    0: "UNKNOWN", 1: "DISABLED", 2: "APPLIED",
    3: "ROLLED_BACK", 4: "ROLLBACK_FAILED",
}
CAMERA_STATE_SOURCES_BY_TOPIC = {
    "/vision/cctv/gate_event": "gate_cam",
    "/vision/cctv/center_event": "center_cam",
}
CAMERA_STATE_TYPES = {
    1: "ENTERING", 2: "PARKED", 3: "EXITING", 4: "EXITED",
}


def active_subscriptions():
    """현재 서비스로 안전하게 전달할 수 있는 활성 토픽만 반환한다."""
    return tuple(spec for spec in SUBSCRIPTIONS if spec.active)


def _module_available(module_name):
    try:
        importlib.import_module(module_name)
    except (ImportError, ModuleNotFoundError, ValueError):
        return False
    return True


def dependency_report():
    """실행 환경을 바꾸지 않고 ROS adapter 시작 가능 여부를 점검한다."""
    modules = {
        "rclpy": "rclpy",
        "patrol_interfaces": "patrol_interfaces.msg",
        "nav_msgs": "nav_msgs.msg",
        "sensor_msgs": "sensor_msgs.msg",
        "std_msgs": "std_msgs.msg",
    }
    available = {}
    errors = {}
    for name, module_name in modules.items():
        try:
            importlib.import_module(module_name)
            available[name] = True
        except (ImportError, ModuleNotFoundError, ValueError) as exc:
            available[name] = False
            errors[name] = str(exc)
    return {
        "ready": all(available.values()),
        "dependencies": available,
        "errors": errors,
        "active_topics": [spec.topic for spec in active_subscriptions()],
        "report_service": REPORT_DETECTION_SERVICE,
        # 서비스 타입은 patrol_interfaces를 srv 포함으로 다시 빌드해야 보인다. 없어도 토픽 수신은 동작한다.
        "report_service_available": _module_available("patrol_interfaces.srv"),
        "pending_topics": [
            spec.topic for spec in SUBSCRIPTIONS if not spec.active
        ],
    }
