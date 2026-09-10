"""고정 웹캠 인식 모듈에서 받은 차량 입출차 내역 검증과 표시 처리."""

from datetime import datetime, timedelta, timezone
import re

from ..models import cctv as cctv_model
from ..models import vehicle_access as vehicle_access_model


ACCESS_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


CAMERA_NAMES = {"webcam1": "고정 웹캠 1", "webcam2": "고정 웹캠 2"}
DIRECTIONS = {"ENTRY": "입차", "EXIT": "출차"}
# [주차장 안 상태] 센터 CCTV의 주차 완료·출차 중은 게이트 통과가 아니라 별도 표로 보존한다.
# 같은 차량이 입출차로 두 번 세어지지 않도록 목록을 만들 때만 합쳐서 보여준다.
CENTER_STATES = {"PARKED": "주차 완료", "EXITING": "출차 중"}
CENTER_CAMERA_NAME = "센터 CCTV"


class VehicleAccessValidationError(ValueError):
    """차량 입출차 내역이 내부 규약과 다를 때 사용한다."""


def _required_text(payload, field):
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise VehicleAccessValidationError(f"{field} 값이 필요합니다.")
    return value.strip()


def _utc_timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise VehicleAccessValidationError(
            "detected_at은 시간대가 포함된 ISO 8601 시각이어야 합니다."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise VehicleAccessValidationError("detected_at에 시간대가 필요합니다.")
    return parsed.astimezone(timezone.utc)


def validate_access(payload, now=None):
    """영상 인식 adapter와 임시 HTTP 입력이 공유할 입출차 형식을 정규화한다."""
    if not isinstance(payload, dict):
        raise VehicleAccessValidationError("JSON 객체가 필요합니다.")
    access_id = _required_text(payload, "access_id")
    message_id = _required_text(payload, "message_id")
    if not ACCESS_ID_PATTERN.fullmatch(access_id) or not ACCESS_ID_PATTERN.fullmatch(message_id):
        raise VehicleAccessValidationError("access_id 또는 message_id 형식이 올바르지 않습니다.")
    camera_id = _required_text(payload, "camera_id").lower()
    if camera_id not in CAMERA_NAMES:
        raise VehicleAccessValidationError("camera_id는 webcam1 또는 webcam2여야 합니다.")
    direction = _required_text(payload, "direction").upper()
    if direction not in DIRECTIONS:
        raise VehicleAccessValidationError("direction은 ENTRY 또는 EXIT여야 합니다.")
    detected = _utc_timestamp(payload.get("detected_at"))
    current = now or datetime.now(timezone.utc)
    if detected > current + timedelta(minutes=5):
        raise VehicleAccessValidationError("입출차 시각이 서버 시각보다 5분 이상 미래입니다.")
    return {
        "access_id": access_id, "message_id": message_id,
        "camera_id": camera_id, "direction": direction,
        "detected_at": detected.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "received_at": current.astimezone(timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z"),
    }


def receive_access(payload, now=None):
    """검증된 입차·출차 내역을 중복 없이 SQLite에 저장한다."""
    return vehicle_access_model.store(validate_access(payload, now))


def _display_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone(timedelta(hours=9))).strftime("%m-%d %H:%M:%S")


def _view(row):
    item = dict(row)
    return {
        "access_id": item["access_id"], "message_id": item["message_id"],
        "camera_id": item["camera_id"],
        "camera_name": CAMERA_NAMES.get(item["camera_id"], item["camera_id"]),
        "direction": item["direction"], "direction_label": DIRECTIONS[item["direction"]],
        "detected_at": item["detected_at"],
        "detected_label": _display_time(item["detected_at"]),
    }


def _center_view(row):
    """센터 CCTV 상태를 입출차 목록과 같은 열 구조로 바꾼다."""
    item = dict(row)
    return {
        "access_id": item["event_id"], "message_id": item["event_id"],
        "camera_id": "center_cam", "camera_name": CENTER_CAMERA_NAME,
        "direction": item["state"], "direction_label": CENTER_STATES[item["state"]],
        "detected_at": item["observed_at"],
        "detected_label": _display_time(item["observed_at"]),
    }


def recent_accesses(limit=50, after=None):
    """게이트 통과 기록과 센터 주차·출차 상태를 시간순으로 합쳐 돌려준다."""
    items = [_view(row) for row in vehicle_access_model.list_recent(limit, after)]
    items.extend(
        _center_view(row)
        for row in cctv_model.list_center_states(limit, after)
        if row["state"] in CENTER_STATES
    )
    items.sort(key=lambda item: item["detected_at"], reverse=True)
    return items[:limit]
