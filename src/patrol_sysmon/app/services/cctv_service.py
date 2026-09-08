"""CameraState와 patrol_allowed 검증·저장·화면 표시 처리."""

from datetime import datetime, timedelta, timezone
import math
import re
import uuid

from flask import current_app

from ..models import cctv as cctv_model
from . import vehicle_access_service


UUID_V4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
CAMERA_NAMES = {"gate_cam": "게이트 CCTV", "center_cam": "센터 CCTV"}
STATE_LABELS = {
    "ENTERING": "진입 중", "PARKED": "주차 완료",
    "EXITING": "출차 중", "EXITED": "출차 완료",
}
ALLOWED_STATES = {
    "gate_cam": {"ENTERING", "EXITED"},
    "center_cam": {"PARKED", "EXITING"},
}
# [입출차 연결] 차량이 실제로 드나드는 지점은 게이트다.
# 게이트의 진입·출차 완료만 입출차 로그로 남기고, 센터의 주차 완료·출차 중은
# 주차장 안 상태라 CCTV 상태로만 보존한다. 한 대가 지날 때 입출차가 두 번 남지 않게 한다.
ACCESS_CAMERA_IDS = {"gate_cam": "webcam1"}
ACCESS_DIRECTIONS = {"ENTERING": "ENTRY", "EXITED": "EXIT"}


class CctvValidationError(ValueError):
    """PC 4 CCTV 계약 필드가 확정 형식과 다를 때 사용한다."""


def _uuid_v4(value):
    if not isinstance(value, str) or not UUID_V4_PATTERN.fullmatch(value):
        raise CctvValidationError("event_id는 소문자 UUID v4여야 합니다.")
    try:
        parsed = uuid.UUID(value, version=4)
    except ValueError as exc:
        raise CctvValidationError("event_id는 소문자 UUID v4여야 합니다.") from exc
    if str(parsed) != value:
        raise CctvValidationError("event_id는 소문자 UUID v4여야 합니다.")
    return value


def _timestamp(value, now):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise CctvValidationError("observed_at은 시간대가 포함된 ISO 8601 시각이어야 합니다.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CctvValidationError("observed_at에 시간대가 필요합니다.")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > now + timedelta(minutes=5):
        raise CctvValidationError("observed_at이 서버 시각보다 5분 이상 미래입니다.")
    return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def validate_camera_state(payload, now=None):
    """topic 검사를 마친 CameraState를 저장 가능한 계약 값으로 정규화한다."""
    if not isinstance(payload, dict):
        raise CctvValidationError("CameraState 객체가 필요합니다.")
    current = now or datetime.now(timezone.utc)
    camera_id = payload.get("camera_id")
    if camera_id not in CAMERA_NAMES:
        raise CctvValidationError("camera_id는 gate_cam 또는 center_cam이어야 합니다.")
    state = payload.get("state")
    if state not in ALLOWED_STATES[camera_id]:
        raise CctvValidationError(f"{camera_id}에서 허용되지 않은 state입니다.")
    confidence = payload.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not 0.0 <= confidence <= 1.0
    ):
        raise CctvValidationError("confidence는 0.0에서 1.0 사이의 유한한 숫자여야 합니다.")
    return {
        "event_id": _uuid_v4(payload.get("event_id")),
        "camera_id": camera_id,
        "state": state,
        "confidence": float(confidence),
        "observed_at": _timestamp(payload.get("observed_at"), current),
        "received_at": current.astimezone(timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z"),
    }


def vehicle_access_payload(record):
    """게이트 CameraState 한 건을 차량 입출차 기록 입력으로 바꾼다.

    게이트가 아니거나 입출차와 무관한 상태면 None을 돌려 기록하지 않는다.
    """
    if record["camera_id"] not in ACCESS_CAMERA_IDS:
        return None
    if record["state"] not in ACCESS_DIRECTIONS:
        return None
    return {
        # 상태 확정마다 새로 만들어지는 event_id를 그대로 써서 중복 저장을 막는다.
        "access_id": record["event_id"],
        "message_id": record["event_id"],
        "camera_id": ACCESS_CAMERA_IDS[record["camera_id"]],
        "direction": ACCESS_DIRECTIONS[record["state"]],
        "detected_at": record["observed_at"],
    }


def receive_camera_state(payload, now=None):
    """CameraState를 보존하고 게이트 진입·출차만 차량 입출차 로그에 남긴다."""
    record = validate_camera_state(payload, now)
    outcome, stored = cctv_model.store_event(record)
    access = vehicle_access_payload(record)
    if access is not None:
        # 재전송으로 상태가 이미 있어도 입출차 기록은 다시 확인한다. 중복이면 그대로 넘어간다.
        vehicle_access_service.receive_access(access, now)
    return outcome, stored


def receive_patrol_allowed(value, now=None):
    """Bool을 임의 변환하지 않고 마지막 수신 시각과 변경 이력을 저장한다."""
    if not isinstance(value, bool):
        raise CctvValidationError("patrol_allowed.data는 Bool이어야 합니다.")
    current = now or datetime.now(timezone.utc)
    received_at = current.astimezone(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")
    return cctv_model.store_permit(value, received_at)


def _display_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone(timedelta(hours=9))).strftime("%m-%d %H:%M:%S")


def _event_view(row):
    item = dict(row)
    return {
        "event_id": item["event_id"],
        "camera_id": item["camera_id"],
        "camera_name": CAMERA_NAMES[item["camera_id"]],
        "state": item["state"],
        "state_label": STATE_LABELS[item["state"]],
        "confidence": item["confidence"],
        "observed_at": item["observed_at"],
        "observed_label": _display_time(item["observed_at"]),
    }


def dashboard_cctv(now=None):
    """permit 단절 시 마지막 Bool은 보존하고 stale 경고만 계산한다."""
    current = now or datetime.now(timezone.utc)
    row = cctv_model.latest_permit()
    events = [_event_view(item) for item in cctv_model.list_recent_events(20)]
    if row is None:
        permit = {
            "received": False, "allowed": None, "stale": False,
            "state": "WAITING", "status_label": "순찰 조건 수신 대기",
            "received_at": None, "received_label": "수신 전",
        }
    else:
        received = datetime.fromisoformat(row["received_at"].replace("Z", "+00:00"))
        age = max(0.0, (current - received).total_seconds())
        stale_after = float(current_app.config["PATROL_PERMIT_STALE_SECONDS"])
        allowed = bool(row["allowed"])
        stale = age > stale_after
        permit = {
            "received": True, "allowed": allowed, "stale": stale,
            "state": "STALE" if stale else ("ALLOWED" if allowed else "BLOCKED"),
            "status_label": (
                "통신 경고 · 마지막 값 유지"
                if stale else ("순찰 허용" if allowed else "순찰 제한")
            ),
            "received_at": row["received_at"],
            "received_label": _display_time(row["received_at"]),
        }
    return {"permit": permit, "events": events, "latest_event": events[0] if events else None}
