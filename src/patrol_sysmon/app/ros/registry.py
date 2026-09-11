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
    # [v2 로봇 상태] patrol_interfaces 2.0에는 RobotStatus·PatrolVisit·PatrolReport가 없다.
    # 관제가 호출하는 Patrol Action의 피드백·상태 토픽을 옆에서 구독해 임무 상태·위치·방문·결과를 얻고,
    # 배터리는 TurtleBot4 기본 battery_state로 받는다. Action 흐름에는 끼어들지 않는다.
    SubscriptionSpec(
        "robot1_patrol_feedback", "/robot1/patrol_action/_action/feedback",
        "patrol_interfaces/action/Patrol_FeedbackMessage", "patrol_feedback", True,
    ),
    SubscriptionSpec(
        "robot6_patrol_feedback", "/robot6/patrol_action/_action/feedback",
        "patrol_interfaces/action/Patrol_FeedbackMessage", "patrol_feedback", True,
    ),
    SubscriptionSpec(
        "robot1_patrol_status", "/robot1/patrol_action/_action/status",
        "action_msgs/msg/GoalStatusArray", "patrol_goal_status", True,
    ),
    SubscriptionSpec(
        "robot6_patrol_status", "/robot6/patrol_action/_action/status",
        "action_msgs/msg/GoalStatusArray", "patrol_goal_status", True,
    ),
    SubscriptionSpec(
        "robot1_battery", "/robot1/battery_state",
        "sensor_msgs/msg/BatteryState", "battery_state", True,
    ),
    SubscriptionSpec(
        "robot6_battery", "/robot6/battery_state",
        "sensor_msgs/msg/BatteryState", "battery_state", True,
    ),
    SubscriptionSpec(
        "map", "/map", "nav_msgs/msg/OccupancyGrid", "map", True,
    ),
    SubscriptionSpec(
        "robot1_image", "/robot1/oakd/rgb/preview/image_raw/compressed",
        "sensor_msgs/msg/CompressedImage", "camera_frame", True,
    ),
    SubscriptionSpec(
        "robot6_image", "/robot6/oakd/rgb/image_raw/compressed",
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
        "robot6_global_costmap", "/robot6/global_costmap/costmap",
        "nav_msgs/msg/OccupancyGrid", "costmap", True,
    ),
    # [local costmap 미구독] Nav2 local costmap은 odom 좌표계라 map 검증에서 매번 거부되고,
    # NAV 지도는 global costmap만 바탕으로 쓰므로 구독하지 않는다.
    # [사건 보고] DetectionEvent·EvidenceChunk 토픽은 구독하지 않는다. 확정 사건과 사진은
    # ReportDetection 서비스(REPORT_DETECTION_SERVICE) 한 번으로 받는다.
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
    # [E-stop 예약] v2에서 /control/estop은 타입만 예약돼 발행자가 없다. 발행되면 바로 표시한다.
    SubscriptionSpec(
        "estop", "/control/estop",
        "patrol_interfaces/msg/EStop", "estop", True,
    ),
)

ROBOT_DISPLAY_IDS = {"robot1": "AMR1", "robot6": "AMR2"}
# [ReportDetection] 확정 사건·증거 사진을 서비스 한 번으로 받는다. System monitor가 서버다.
REPORT_DETECTION_SERVICE = "/system_monitor/report_detection"
# v1.1 기준선의 FIRE=1·LEAK=2·OBSTACLE=3 과 같은 값. 0(UNKNOWN)은 "안 채운 값"으로 보고 거부한다.
REPORT_EVENT_TYPES = {1: "FIRE", 2: "LEAK", 3: "OBSTACLE"}
# [v2 Patrol Feedback] task_state 값. 이름은 Patrol.action 상수를 그대로 쓴다.
PATROL_TASK_STATES = {
    1: "WAITING_FOR_TOKEN",
    2: "UNDOCKING",
    3: "INITIAL_POSE_READY",
    4: "PATROLLING",
    5: "MOVING_TO_SAFE_ZONE",
    6: "DETECTION_PROCESSING",
    7: "DETECTION_CONFIRMED",
    8: "RESUMING",
    9: "DOCKING",
    10: "BLOCKED",
    11: "WAYPOINT_REACHED",
}
# action_msgs/GoalStatus. 끝난 목표만 순찰 결과로 기록한다. Patrol Result의 outcome과 같은 뜻으로 옮긴다.
GOAL_STATUS_ACTIVE = {1: "ACCEPTED", 2: "EXECUTING", 3: "CANCELING"}
GOAL_STATUS_RESULTS = {4: "SUCCEEDED", 5: "CANCELED", 6: "FAILED"}
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
    "/robot1/oakd/rgb/preview/image_raw/compressed": "amr1",
    "/robot6/oakd/rgb/image_raw/compressed": "amr2",
    "/vision/cctv/gate_image/compressed": "webcam1",
    "/vision/cctv/center_image/compressed": "webcam2",
}
COSTMAP_SOURCES_BY_TOPIC = {
    "/robot1/global_costmap/costmap": ("AMR1", "global"),
    "/robot6/global_costmap/costmap": ("AMR2", "global"),
}
PATROL_FEEDBACK_SOURCES_BY_TOPIC = {
    "/robot1/patrol_action/_action/feedback": "robot1",
    "/robot6/patrol_action/_action/feedback": "robot6",
}
PATROL_STATUS_SOURCES_BY_TOPIC = {
    "/robot1/patrol_action/_action/status": "robot1",
    "/robot6/patrol_action/_action/status": "robot6",
}
BATTERY_SOURCES_BY_TOPIC = {
    "/robot1/battery_state": "robot1",
    "/robot6/battery_state": "robot6",
}
CAMERA_STATE_SOURCES_BY_TOPIC = {
    "/vision/cctv/gate_event": "gate_cam",
    "/vision/cctv/center_event": "center_cam",
}
# [v2 CameraState] 숫자는 메시지 상수(STATE_*)를 먼저 읽고, 상수가 없을 때만 이 표를 쓴다.
CAMERA_STATE_TYPES = {
    1: "ENTERING", 2: "EXITED", 3: "PARKED", 4: "EXITING",
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
        "patrol_interfaces.action": "patrol_interfaces.action",
        "action_msgs": "action_msgs.msg",
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
