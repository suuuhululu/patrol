"""ROS 2 메시지를 sysmon 서비스 입력(dict)으로 바꾸는 순수 함수.

ROS 실행 없이도 불러 쓸 수 있어 계약 변환만 따로 시험한다.
"""

from datetime import datetime, timezone
from io import BytesIO
import math
import uuid

from .errors import RosMessageMappingError
from .registry import (
    BATTERY_SOURCES_BY_TOPIC, CAMERA_IDS_BY_TOPIC, CAMERA_STATE_SOURCES_BY_TOPIC,
    CAMERA_STATE_TYPES, ESTOP_REASONS, ESTOP_TARGETS, GOAL_STATUS_ACTIVE,
    GOAL_STATUS_RESULTS, PATROL_FEEDBACK_SOURCES_BY_TOPIC, PATROL_STATUS_SOURCES_BY_TOPIC,
    PATROL_TASK_STATES, REPORT_EVENT_TYPES, ROBOT_DISPLAY_IDS,
)


def _stamp_parts(stamp):
    try:
        seconds = int(stamp.sec)
        nanoseconds = int(stamp.nanosec)
    except (AttributeError, TypeError, ValueError) as exc:
        raise RosMessageMappingError("ROS header stamp 형식이 올바르지 않습니다.") from exc
    if seconds < 0 or not 0 <= nanoseconds < 1_000_000_000:
        raise RosMessageMappingError("ROS header stamp 범위가 올바르지 않습니다.")
    return seconds, nanoseconds


def _stamp_iso(stamp):
    seconds, nanoseconds = _stamp_parts(stamp)
    value = datetime.fromtimestamp(
        seconds + nanoseconds / 1_000_000_000,
        tz=timezone.utc,
    )
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _frame_id(header):
    value = getattr(header, "frame_id", None)
    if not isinstance(value, str) or not value:
        raise RosMessageMappingError("ROS header frame_id가 필요합니다.")
    return value


def _enum_name(message, value, fallback_table, prefixes, label):
    """enum 이름을 메시지 클래스 상수에서 읽는다.

    같은 이름의 상태라도 정의마다 숫자가 다를 수 있어 숫자표를 고정하지 않는다.
    상수를 찾지 못하면 기존 표로 되돌아간다.
    """
    # 같은 숫자를 쓰는 다른 enum 묶음이 있으므로 기대하는 이름만 인정한다.
    expected = set(fallback_table.values())
    for name in dir(type(message)):
        if not name.isupper() or getattr(type(message), name, None) != value:
            continue
        for prefix in prefixes:
            if name.startswith(prefix) and name[len(prefix):] in expected:
                return name[len(prefix):]
        if name in expected:
            return name
    try:
        return fallback_table[value]
    except KeyError as exc:
        raise RosMessageMappingError(f"지원하지 않는 {label} enum 값입니다.") from exc


def _finite_number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RosMessageMappingError(f"{field} 값은 유한한 숫자여야 합니다.")
    return float(value)


def _quaternion_yaw(orientation):
    try:
        x = _finite_number(orientation.x, "origin.orientation.x")
        y = _finite_number(orientation.y, "origin.orientation.y")
        z = _finite_number(orientation.z, "origin.orientation.z")
        w = _finite_number(orientation.w, "origin.orientation.w")
    except AttributeError as exc:
        raise RosMessageMappingError("OccupancyGrid origin orientation이 없습니다.") from exc
    sin_yaw = 2.0 * (w * z + x * y)
    cos_yaw = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(sin_yaw, cos_yaw)


def occupancy_grid_payload(message):
    """표준 OccupancyGrid를 기존 지도 서비스 입력으로 바꾼다."""
    try:
        header = message.header
        info = message.info
        seconds, nanoseconds = _stamp_parts(header.stamp)
        origin = info.origin
        data = list(message.data)
    except AttributeError as exc:
        raise RosMessageMappingError("OccupancyGrid 필수 필드가 없습니다.") from exc
    return {
        # OccupancyGrid에는 message_id가 없으므로 생산자 stamp로 재전송 식별자를 만든다.
        "message_id": f"ros-map-{seconds}-{nanoseconds}",
        "frame_id": _frame_id(header),
        "resolution": _finite_number(info.resolution, "resolution"),
        "width": int(info.width),
        "height": int(info.height),
        "origin": {
            "x": _finite_number(origin.position.x, "origin.position.x"),
            "y": _finite_number(origin.position.y, "origin.position.y"),
            "yaw": _quaternion_yaw(origin.orientation),
        },
        "data": data,
        "observed_at": _stamp_iso(header.stamp),
    }


def compressed_image_input(topic, message):
    """CompressedImage와 토픽을 기존 최신 프레임 서비스 인자로 바꾼다."""
    try:
        camera_id = CAMERA_IDS_BY_TOPIC[topic]
    except KeyError as exc:
        raise RosMessageMappingError("등록되지 않은 영상 토픽입니다.") from exc
    try:
        header = message.header
        seconds, nanoseconds = _stamp_parts(header.stamp)
        image_bytes = bytes(message.data)
    except (AttributeError, TypeError, ValueError) as exc:
        raise RosMessageMappingError("CompressedImage 필수 필드가 없습니다.") from exc
    if not image_bytes:
        raise RosMessageMappingError("CompressedImage data가 비어 있습니다.")
    frame_id = f"ros-{camera_id}-{seconds}-{nanoseconds}"
    return camera_id, frame_id, _stamp_iso(header.stamp), BytesIO(image_bytes)


def camera_state_payload(topic, message):
    """CameraState 토픽·camera_id·enum을 PC 3 저장 서비스 입력으로 바꾼다."""
    expected_camera = CAMERA_STATE_SOURCES_BY_TOPIC.get(topic)
    if expected_camera is None:
        raise RosMessageMappingError("등록되지 않은 CameraState 토픽입니다.")
    if getattr(message, "camera_id", "") != expected_camera:
        raise RosMessageMappingError("CameraState camera_id가 토픽 source와 다릅니다.")
    try:
        observed_at = _stamp_iso(message.header.stamp)
        # [enum 값 차이] 같은 상태라도 정의마다 숫자가 다르므로 이름으로 맞춘다.
        state = _enum_name(
            message, message.state, CAMERA_STATE_TYPES, ("STATE_",), "CameraState state"
        )
    except (AttributeError, KeyError) as exc:
        raise RosMessageMappingError("CameraState 필수 필드 또는 enum이 올바르지 않습니다.") from exc
    return {
        "event_id": getattr(message, "event_id", ""),
        "camera_id": expected_camera,
        "state": state,
        "confidence": _finite_number(getattr(message, "confidence", None), "confidence"),
        "observed_at": observed_at,
    }


def patrol_allowed_payload(message):
    """std_msgs/Bool을 암묵적 형변환 없이 서비스 입력으로 꺼낸다."""
    value = getattr(message, "data", None)
    if not isinstance(value, bool):
        raise RosMessageMappingError("patrol_allowed.data는 Bool이어야 합니다.")
    return value


def _robot_of(topic, sources, label):
    """토픽 namespace로 로봇을 정한다. Action 피드백·상태와 battery_state에는 robot_id 필드가 없다."""
    contract_robot = sources.get(topic)
    if contract_robot is None:
        raise RosMessageMappingError(f"등록되지 않은 {label} 토픽입니다.")
    return ROBOT_DISPLAY_IDS[contract_robot]


def _goal_uuid(goal_id):
    """unique_identifier_msgs/UUID(16바이트)를 소문자 UUID 문자열로 바꾼다."""
    try:
        raw = bytes(bytearray(goal_id.uuid))
    except (AttributeError, TypeError, ValueError) as exc:
        raise RosMessageMappingError("Action goal_id가 올바르지 않습니다.") from exc
    if len(raw) != 16:
        raise RosMessageMappingError("Action goal_id는 16바이트여야 합니다.")
    return str(uuid.UUID(bytes=raw))


def patrol_feedback_payload(topic, message):
    """Patrol Action 피드백(FeedbackMessage)을 추적기 입력으로 바꾼다."""
    robot_id = _robot_of(topic, PATROL_FEEDBACK_SOURCES_BY_TOPIC, "Patrol 피드백")
    try:
        feedback = message.feedback
        task_state = _enum_name(
            feedback, feedback.task_state, PATROL_TASK_STATES, (), "Patrol task_state"
        )
        pose = feedback.current_pose
        frame_id = getattr(pose.header, "frame_id", "")
        position = pose.pose.position
    except AttributeError as exc:
        raise RosMessageMappingError("Patrol 피드백 필수 필드가 없습니다.") from exc
    # [위치 유효성] map 좌표계의 유한한 좌표만 위치로 쓴다. 비어 있으면 위치를 모르는 것으로 둔다.
    x, y = getattr(position, "x", None), getattr(position, "y", None)
    pose_valid = (
        frame_id == "map"
        and all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            for value in (x, y)
        )
    )
    return {
        "robot_id": robot_id,
        "goal_id": _goal_uuid(message.goal_id),
        "task_state": task_state,
        "waypoint_id": str(getattr(feedback, "current_waypoint_id", "") or "").strip(),
        "token_valid": bool(getattr(feedback, "token_valid", False)),
        "pose_valid": pose_valid,
        "x": float(x) if pose_valid else None,
        "y": float(y) if pose_valid else None,
    }


def patrol_goal_status_payload(topic, message):
    """action_msgs/GoalStatusArray에서 목표별 상태와 수락 시각을 꺼낸다."""
    robot_id = _robot_of(topic, PATROL_STATUS_SOURCES_BY_TOPIC, "Patrol 상태")
    goals = []
    for status in getattr(message, "status_list", []):
        code = getattr(status, "status", None)
        name = GOAL_STATUS_ACTIVE.get(code) or GOAL_STATUS_RESULTS.get(code)
        if name is None:
            # UNKNOWN(0)은 판단 근거가 없어 건너뛴다.
            continue
        try:
            goal_info = status.goal_info
            accepted_at = _stamp_iso(goal_info.stamp)
        except AttributeError as exc:
            raise RosMessageMappingError("GoalStatus goal_info가 없습니다.") from exc
        goals.append({
            "goal_id": _goal_uuid(goal_info.goal_id),
            "status": name,
            "finished": code in GOAL_STATUS_RESULTS,
            "accepted_at": accepted_at,
        })
    return {"robot_id": robot_id, "goals": goals}


def battery_state_payload(topic, message):
    """sensor_msgs/BatteryState의 percentage(0~1)를 0~100 값으로 바꾼다. 모르면 None."""
    robot_id = _robot_of(topic, BATTERY_SOURCES_BY_TOPIC, "battery_state")
    percentage = getattr(message, "percentage", None)
    if (
        isinstance(percentage, bool) or not isinstance(percentage, (int, float))
        or not math.isfinite(percentage) or not 0.0 <= percentage <= 1.0
    ):
        # BatteryState는 모르는 값을 NaN으로 보낸다. 임의 값으로 채우지 않는다.
        return {"robot_id": robot_id, "battery": None}
    return {"robot_id": robot_id, "battery": float(percentage) * 100.0}


def report_detection_payload(request):
    """ReportDetection 요청(필드 5개)을 저장 서비스 입력으로 바꾼다."""
    contract_robot_id = getattr(request, "robot_id", "")
    try:
        robot_id = ROBOT_DISPLAY_IDS[contract_robot_id]
    except KeyError as exc:
        raise RosMessageMappingError("robot_id는 robot1 또는 robot6이어야 합니다.") from exc
    try:
        position = request.position
        detected_at = _stamp_iso(request.detected_at)
        image = bytes(request.image)
    except (AttributeError, TypeError, ValueError) as exc:
        raise RosMessageMappingError("ReportDetection 필수 필드가 올바르지 않습니다.") from exc
    event_type = getattr(request, "event_type", None)
    if event_type not in REPORT_EVENT_TYPES:
        raise RosMessageMappingError("event_type은 1(화재)·2(누수)·3(장애물) 중 하나여야 합니다.")
    return {
        "robot_id": robot_id,
        "event_id": getattr(request, "event_id", ""),
        "event_type": REPORT_EVENT_TYPES[event_type],
        "detected_at": detected_at,
        "x": _finite_number(getattr(position, "x", None), "position.x"),
        "y": _finite_number(getattr(position, "y", None), "position.y"),
        "image": image,
    }


def estop_payload(message):
    """계약 EStop(/control/estop)을 안전 상태 저장 입력으로 바꾼다.

    interfaces.md v1.0: header·target_robot_id·active·reason·sequence만 쓴다.
    """
    try:
        observed_at = _stamp_iso(message.header.stamp)
    except AttributeError as exc:
        raise RosMessageMappingError("EStop header가 올바르지 않습니다.") from exc
    target = getattr(message, "target_robot_id", "")
    if target not in ESTOP_TARGETS:
        raise RosMessageMappingError("EStop target_robot_id는 robot1, robot6, all 중 하나여야 합니다.")
    active = getattr(message, "active", None)
    if not isinstance(active, bool):
        raise RosMessageMappingError("EStop active는 Bool이어야 합니다.")
    reason = getattr(message, "reason", 0)
    if isinstance(reason, bool) or not isinstance(reason, int):
        raise RosMessageMappingError("EStop reason은 정수여야 합니다.")
    return {
        "target_robot_id": target,
        "active": active,
        # 정의되지 않은 원인 수치는 버리지 않고 UNKNOWN으로 표시해 활성 사실을 잃지 않는다.
        "reason": reason if reason in ESTOP_REASONS else 0,
        "sequence": int(getattr(message, "sequence", 0)),
        "observed_at": observed_at,
    }
