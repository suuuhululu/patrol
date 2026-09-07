"""ROS 2 메시지를 sysmon 서비스 입력(dict)으로 바꾸는 순수 함수.

ROS 실행 없이도 불러 쓸 수 있어 계약 변환만 따로 시험한다.
"""

from datetime import datetime, timezone
from io import BytesIO
import math

from .errors import RosMessageMappingError
from .registry import (
    CAMERA_IDS_BY_TOPIC, CAMERA_STATE_SOURCES_BY_TOPIC, CAMERA_STATE_TYPES,
    COSTMAP_SOURCES_BY_TOPIC, DETECTION_EVENT_TYPES, DETECTION_RISK_LEVELS,
    DETECTION_SOURCES_BY_TOPIC, EVIDENCE_SOURCES_BY_TOPIC, KEEPOUT_SOURCES_BY_TOPIC,
    KEEPOUT_STATES, MISSION_STATES, PATROL_REPORT_RESULTS,
    PATROL_REPORT_SOURCES_BY_TOPIC, PATROL_VISIT_RESULTS,
    PATROL_VISIT_SOURCES_BY_TOPIC, ROBOT_DISPLAY_IDS,
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


def _finite_number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RosMessageMappingError(f"{field} 값은 유한한 숫자여야 합니다.")
    return float(value)


def robot_status_payload(message):
    """계약 RobotStatus를 기존 상태 서비스가 받는 내부 payload로 바꾼다."""
    contract_robot_id = getattr(message, "robot_id", "")
    try:
        display_robot_id = ROBOT_DISPLAY_IDS[contract_robot_id]
    except KeyError as exc:
        raise RosMessageMappingError("robot_id는 robot1 또는 robot6이어야 합니다.") from exc
    pose_valid = getattr(message, "pose_valid", None)
    if not isinstance(pose_valid, bool):
        raise RosMessageMappingError("RobotStatus pose_valid는 Bool이어야 합니다.")
    mission_state = getattr(message, "mission_state", None)
    if mission_state not in MISSION_STATES:
        raise RosMessageMappingError("지원하지 않는 RobotStatus mission_state입니다.")
    battery_soc = _finite_number(getattr(message, "battery_soc", None), "battery_soc")
    if not 0.0 <= battery_soc <= 1.0:
        raise RosMessageMappingError("battery_soc는 0.0에서 1.0 사이여야 합니다.")
    try:
        # 계약 타입은 geometry_msgs/PoseWithCovariance이므로 pose가 한 단계 더 중첩된다.
        position = message.pose.pose.position
        header = message.header
        # [무효 위치] 좌표가 NaN이어도 배터리·임무는 계속 받아야 하므로 좌표만 비운다.
        x = _finite_number(position.x, "pose.position.x") if pose_valid else None
        y = _finite_number(position.y, "pose.position.y") if pose_valid else None
        last_valid_pose_at = _optional_stamp_iso(message.last_valid_pose_stamp)
    except AttributeError as exc:
        raise RosMessageMappingError("RobotStatus pose 또는 header가 없습니다.") from exc
    message_id = getattr(message, "message_id", "")
    if not isinstance(message_id, str) or not message_id:
        raise RosMessageMappingError("RobotStatus message_id가 필요합니다.")
    frame_id = _frame_id(header)
    if frame_id != "map":
        raise RosMessageMappingError("RobotStatus header.frame_id는 map이어야 합니다.")
    return {
        "message_id": message_id,
        "robot_id": display_robot_id,
        "battery": battery_soc * 100.0,
        "x": x,
        "y": y,
        "frame_id": frame_id,
        "pose_valid": pose_valid,
        "last_valid_pose_at": last_valid_pose_at,
        "mission_status": MISSION_STATES[mission_state],
        # 토픽을 현재 수신한 사실만 ONLINE으로 변환하며, 이후 단절은 기존 수신 시각으로 판정한다.
        "connection_status": "ONLINE",
        "observed_at": _stamp_iso(header.stamp),
    }


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


def detection_event_payload(topic, message):
    """계약 DetectionEvent를 증적과 독립 저장 가능한 내부 사건으로 바꾼다."""
    expected_robot = DETECTION_SOURCES_BY_TOPIC.get(topic)
    if expected_robot is None:
        raise RosMessageMappingError("등록되지 않은 DetectionEvent 토픽입니다.")
    contract_robot = getattr(message, "robot_id", "")
    if contract_robot != expected_robot:
        raise RosMessageMappingError("DetectionEvent robot_id가 토픽 namespace와 다릅니다.")
    try:
        header = message.header
        _stamp_parts(header.stamp)
        event_type = DETECTION_EVENT_TYPES[message.event_type]
        risk_level = DETECTION_RISK_LEVELS[message.risk_level]
        location_valid = bool(message.location_valid)
        position = message.pose.pose.position
        x = _finite_number(position.x, "pose.position.x") if location_valid else None
        y = _finite_number(position.y, "pose.position.y") if location_valid else None
    except (AttributeError, KeyError) as exc:
        raise RosMessageMappingError("DetectionEvent 필수 필드 또는 enum이 올바르지 않습니다.") from exc
    return {
        "message_id": getattr(message, "message_id", ""),
        "event_id": getattr(message, "event_id", ""),
        "robot_id": ROBOT_DISPLAY_IDS[contract_robot],
        "event_type": event_type,
        "confidence": _finite_number(getattr(message, "confidence", None), "confidence"),
        "risk_level": risk_level,
        "x": x,
        "y": y,
        "frame_id": _frame_id(header),
        "location_valid": location_valid,
        "detected_at": _stamp_iso(message.detected_at),
        "evidence_id": getattr(message, "evidence_id", ""),
    }


def evidence_chunk_payload(topic, message):
    """계약 EvidenceChunk를 조립 서비스가 검증할 메타데이터와 bytes로 바꾼다."""
    expected_robot = EVIDENCE_SOURCES_BY_TOPIC.get(topic)
    if expected_robot is None:
        raise RosMessageMappingError("등록되지 않은 EvidenceChunk 토픽입니다.")
    contract_robot = getattr(message, "robot_id", "")
    if contract_robot != expected_robot:
        raise RosMessageMappingError("EvidenceChunk robot_id가 토픽 namespace와 다릅니다.")
    try:
        _stamp_parts(message.header.stamp)
        data = bytes(message.data)
    except (AttributeError, TypeError, ValueError) as exc:
        raise RosMessageMappingError("EvidenceChunk 필수 필드가 올바르지 않습니다.") from exc
    return {
        "message_id": getattr(message, "message_id", ""),
        "evidence_id": getattr(message, "evidence_id", ""),
        "event_id": getattr(message, "event_id", ""),
        "robot_id": ROBOT_DISPLAY_IDS[contract_robot],
        "captured_at": _stamp_iso(message.captured_at),
        "media_type": getattr(message, "media_type", ""),
        "sha256": getattr(message, "sha256", ""),
        "total_size": int(getattr(message, "total_size", 0)),
        "chunk_index": int(getattr(message, "chunk_index", 0)),
        "chunk_count": int(getattr(message, "chunk_count", 0)),
        "data": data,
    }


def camera_state_payload(topic, message):
    """CameraState 토픽·camera_id·enum을 PC 3 저장 서비스 입력으로 바꾼다."""
    expected_camera = CAMERA_STATE_SOURCES_BY_TOPIC.get(topic)
    if expected_camera is None:
        raise RosMessageMappingError("등록되지 않은 CameraState 토픽입니다.")
    if getattr(message, "camera_id", "") != expected_camera:
        raise RosMessageMappingError("CameraState camera_id가 토픽 source와 다릅니다.")
    try:
        observed_at = _stamp_iso(message.header.stamp)
        state = CAMERA_STATE_TYPES[message.state]
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


def _contract_robot(topic, message, sources, label):
    """토픽 namespace와 메시지의 robot_id가 어긋나면 저장하지 않는다."""
    source = sources.get(topic)
    if source is None:
        raise RosMessageMappingError(f"등록되지 않은 {label} 토픽입니다.")
    if getattr(message, "robot_id", "") != source:
        raise RosMessageMappingError(f"{label} robot_id가 토픽 namespace와 다릅니다.")
    return ROBOT_DISPLAY_IDS[source]


def _optional_stamp_iso(stamp):
    # [미설정 시각] 계약에서 값이 없는 시각은 0으로 온다. 임의 시각으로 채우지 않는다.
    seconds, nanoseconds = _stamp_parts(stamp)
    if seconds == 0 and nanoseconds == 0:
        return None
    return _stamp_iso(stamp)


def patrol_visit_payload(topic, message):
    """PatrolVisit을 관측점 방문 저장 서비스 입력으로 바꾼다."""
    robot_id = _contract_robot(topic, message, PATROL_VISIT_SOURCES_BY_TOPIC, "PatrolVisit")
    try:
        result = PATROL_VISIT_RESULTS[message.result]
        arrived_at = _stamp_iso(message.arrived_at)
        completed_at = _optional_stamp_iso(message.completed_at)
        frame_id = _frame_id(message.pose.header)
        position = message.pose.pose.position
    except (AttributeError, KeyError) as exc:
        raise RosMessageMappingError("PatrolVisit 필수 필드 또는 enum이 올바르지 않습니다.") from exc
    return {
        "visit_id": getattr(message, "visit_id", ""),
        "message_id": getattr(message, "message_id", ""),
        "robot_id": robot_id,
        "patrol_id": getattr(message, "patrol_id", ""),
        "mission_id": getattr(message, "mission_id", ""),
        "command_id": getattr(message, "command_id", ""),
        "waypoint_id": getattr(message, "waypoint_id", ""),
        "x": _finite_number(position.x, "pose.position.x"),
        "y": _finite_number(position.y, "pose.position.y"),
        "frame_id": frame_id,
        "result": result,
        "reason_code": int(getattr(message, "reason_code", 0)),
        "reason": getattr(message, "reason", ""),
        "arrived_at": arrived_at,
        "completed_at": completed_at,
    }


def patrol_report_payload(topic, message):
    """PatrolReport를 순찰 결과 저장 서비스 입력으로 바꾼다."""
    robot_id = _contract_robot(topic, message, PATROL_REPORT_SOURCES_BY_TOPIC, "PatrolReport")
    try:
        result = PATROL_REPORT_RESULTS[message.result]
        started_at = _stamp_iso(message.started_at)
        ended_at = _optional_stamp_iso(message.ended_at)
    except (AttributeError, KeyError) as exc:
        raise RosMessageMappingError("PatrolReport 필수 필드 또는 enum이 올바르지 않습니다.") from exc
    return {
        "report_id": getattr(message, "report_id", ""),
        "message_id": getattr(message, "message_id", ""),
        "robot_id": robot_id,
        "patrol_id": getattr(message, "patrol_id", ""),
        "mission_id": getattr(message, "mission_id", ""),
        "command_id": getattr(message, "command_id", ""),
        "result": result,
        "reason_code": int(getattr(message, "reason_code", 0)),
        "reason": getattr(message, "reason", ""),
        "started_at": started_at,
        "ended_at": ended_at,
        "planned_visit_count": int(getattr(message, "planned_visit_count", 0)),
        "completed_visit_count": int(getattr(message, "completed_visit_count", 0)),
    }


def keepout_status_payload(topic, message):
    """KeepoutStatus를 로봇별 최신 상태 저장 입력으로 바꾼다."""
    robot_id = _contract_robot(topic, message, KEEPOUT_SOURCES_BY_TOPIC, "KeepoutStatus")
    try:
        state = KEEPOUT_STATES[message.state]
        observed_at = _stamp_iso(message.header.stamp)
    except (AttributeError, KeyError) as exc:
        raise RosMessageMappingError("KeepoutStatus 필수 필드 또는 enum이 올바르지 않습니다.") from exc
    return {
        "robot_id": robot_id,
        "message_id": getattr(message, "message_id", ""),
        "transaction_id": getattr(message, "transaction_id", ""),
        "state": state,
        "global_enabled": bool(getattr(message, "global_enabled", False)),
        "local_enabled": bool(getattr(message, "local_enabled", False)),
        "reason_code": int(getattr(message, "reason_code", 0)),
        "detail": getattr(message, "detail", ""),
        "observed_at": observed_at,
    }


def estop_payload(message):
    """EStopState를 안전 상태 저장 입력으로 바꾼다."""
    try:
        observed_at = _stamp_iso(message.header.stamp)
    except AttributeError as exc:
        raise RosMessageMappingError("EStopState header가 올바르지 않습니다.") from exc
    active = getattr(message, "active", None)
    manual_reset = getattr(message, "manual_reset_required", None)
    if not isinstance(active, bool) or not isinstance(manual_reset, bool):
        raise RosMessageMappingError("EStopState active·manual_reset_required는 Bool이어야 합니다.")
    return {
        "estop_id": getattr(message, "estop_id", ""),
        "message_id": getattr(message, "message_id", ""),
        "active": active,
        "reason_code": int(getattr(message, "reason_code", 0)),
        "reason": getattr(message, "reason", ""),
        "manual_reset_required": manual_reset,
        "source_id": getattr(message, "source_id", ""),
        "sequence": int(getattr(message, "sequence", 0)),
        "observed_at": observed_at,
    }
