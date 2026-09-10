"""ROS 2 수신 adapter의 공개 진입점.

실제 구현은 기능별로 `app/ros/`에 나눠 두고 여기서는 이름만 모아 노출한다.
기존 코드와 시험이 `app.ros_adapter`에서 가져다 쓰던 이름은 그대로 유지한다.

- `ros/registry.py`: 구독 토픽 등록표와 계약 enum 대응표
- `ros/payloads.py`: ROS 메시지 → 서비스 입력 변환 (ROS 없이도 시험 가능)
- `ros/patrol_action.py`: v2 Patrol Action 피드백·상태와 배터리를 로봇 상태·방문·결과로 옮기는 추적기
- `ros/qos.py`: 구독 QoS
- `ros/node.py`: 구독 노드 생성·callback·ReportDetection 서비스·실행
"""

from .ros.errors import RosAdapterUnavailable, RosMessageMappingError
from .ros.node import build_node, spin
from .ros.patrol_action import PatrolActionTracker
from .ros.payloads import (
    battery_state_payload,
    camera_state_payload,
    compressed_image_input,
    estop_payload,
    occupancy_grid_payload,
    patrol_allowed_payload,
    patrol_feedback_payload,
    patrol_goal_status_payload,
)
from .ros.qos import _qos_profiles
from .ros.registry import (
    BATTERY_SOURCES_BY_TOPIC,
    CAMERA_IDS_BY_TOPIC,
    CAMERA_STATE_SOURCES_BY_TOPIC,
    CAMERA_STATE_TYPES,
    COSTMAP_SOURCES_BY_TOPIC,
    GOAL_STATUS_ACTIVE,
    GOAL_STATUS_RESULTS,
    PATROL_FEEDBACK_SOURCES_BY_TOPIC,
    PATROL_STATUS_SOURCES_BY_TOPIC,
    PATROL_TASK_STATES,
    ROBOT_DISPLAY_IDS,
    SUBSCRIPTIONS,
    SubscriptionSpec,
    active_subscriptions,
    dependency_report,
)

__all__ = [
    "RosAdapterUnavailable", "RosMessageMappingError", "SubscriptionSpec",
    "SUBSCRIPTIONS", "active_subscriptions", "dependency_report",
    "build_node", "spin", "_qos_profiles", "PatrolActionTracker",
    "occupancy_grid_payload", "compressed_image_input", "camera_state_payload",
    "patrol_allowed_payload", "estop_payload",
    "patrol_feedback_payload", "patrol_goal_status_payload", "battery_state_payload",
    "ROBOT_DISPLAY_IDS", "CAMERA_IDS_BY_TOPIC", "COSTMAP_SOURCES_BY_TOPIC",
    "PATROL_FEEDBACK_SOURCES_BY_TOPIC", "PATROL_STATUS_SOURCES_BY_TOPIC",
    "BATTERY_SOURCES_BY_TOPIC", "PATROL_TASK_STATES", "GOAL_STATUS_ACTIVE",
    "GOAL_STATUS_RESULTS", "CAMERA_STATE_SOURCES_BY_TOPIC", "CAMERA_STATE_TYPES",
]
