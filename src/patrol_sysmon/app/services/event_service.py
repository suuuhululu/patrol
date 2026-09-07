"""화재·누수·장애물 이벤트 메타데이터와 증거 이미지 저장 처리."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import math
import os
import re
import struct
import tempfile

from flask import current_app

from ..models import event as event_model
from .robot_service import FRAME_ID_PATTERN, MESSAGE_ID_PATTERN, ROBOT_NAMES


EVENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
RISK_LEVELS = {"HIGH", "MEDIUM", "LOW"}
# [제품 범위] 관제가 이벤트 로그로 남기는 이상은 화재·누수·장애물 세 종류다.
# 계약 enum에는 LIGHTING·FACILITY_DAMAGE도 있지만 이번 범위에서는 저장하지 않는다.
EVENT_TYPES = {"FIRE", "LEAK", "OBSTACLE"}
EVENT_TYPE_LABELS = {
    "FIRE": "화재", "LEAK": "누수", "OBSTACLE": "장애물",
    # 아래 둘은 더 이상 저장하지 않는다. 범위 축소 전에 저장된 이력을 읽을 때만 사용한다.
    "LIGHTING": "조명 이상", "FACILITY_DAMAGE": "시설물 파손",
}
RISK_LABELS = {"HIGH": "상", "MEDIUM": "중", "LOW": "하"}
STATUS_LABELS = {
    "NEW": "신규", "REVIEWING": "확인중",
    "WORK_REQUESTED": "작업요청", "RESOLVED": "조치완료",
}
STATUS_TRANSITIONS = {
    "NEW": "REVIEWING", "REVIEWING": "WORK_REQUESTED",
    "WORK_REQUESTED": "RESOLVED",
}


class EventValidationError(ValueError):
    """이벤트 메타데이터가 내부 규약과 다를 때 사용한다."""


class EvidenceValidationError(ValueError):
    """증거 이미지가 허용 형식·크기와 다를 때 사용한다."""


def _required_text(payload, field):
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EventValidationError(f"{field} 값이 필요합니다.")
    return value.strip()


def _finite_number(payload, field):
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EventValidationError(f"{field} 값은 유한한 숫자여야 합니다.")
    return float(value)


def _utc_timestamp(value, field):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise EventValidationError(f"{field}은 시간대가 포함된 ISO 8601 시각이어야 합니다.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EventValidationError(f"{field}에 시간대가 필요합니다.")
    return parsed.astimezone(timezone.utc)


def validate_event(payload, now=None):
    """ROS adapter와 임시 HTTP 입력이 공유할 이상 이벤트 형식으로 정규화한다."""
    if not isinstance(payload, dict):
        raise EventValidationError("metadata는 JSON 객체여야 합니다.")
    event_id = _required_text(payload, "event_id")
    message_id = _required_text(payload, "message_id")
    if not EVENT_ID_PATTERN.fullmatch(event_id):
        raise EventValidationError("event_id 형식이 올바르지 않습니다.")
    if not MESSAGE_ID_PATTERN.fullmatch(message_id):
        raise EventValidationError("message_id 형식이 올바르지 않습니다.")
    robot_id = _required_text(payload, "robot_id").upper()
    if robot_id not in ROBOT_NAMES:
        raise EventValidationError("robot_id는 AMR1 또는 AMR2여야 합니다.")
    event_type = _required_text(payload, "event_type").upper()
    if event_type not in EVENT_TYPES:
        raise EventValidationError(
            "event_type은 FIRE, LEAK, OBSTACLE 중 하나여야 합니다."
        )
    risk_level = _required_text(payload, "risk_level").upper()
    if risk_level not in RISK_LEVELS:
        raise EventValidationError("risk_level은 HIGH, MEDIUM, LOW 중 하나여야 합니다.")
    frame_id = _required_text(payload, "frame_id")
    if not FRAME_ID_PATTERN.fullmatch(frame_id):
        raise EventValidationError("frame_id 형식이 올바르지 않습니다.")
    occurred = _utc_timestamp(payload.get("occurred_at"), "occurred_at")
    captured = _utc_timestamp(payload.get("captured_at"), "captured_at")
    current = now or datetime.now(timezone.utc)
    if occurred > current + timedelta(minutes=5) or captured > current + timedelta(minutes=5):
        raise EventValidationError("이벤트 시각이 서버 시각보다 5분 이상 미래입니다.")
    return {
        "event_id": event_id,
        "message_id": message_id,
        "robot_id": robot_id,
        "robot_name": ROBOT_NAMES[robot_id],
        "event_type": event_type,
        "occurred_at": occurred.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "captured_at": captured.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "x": _finite_number(payload, "x"),
        "y": _finite_number(payload, "y"),
        "frame_id": frame_id,
        "risk_level": risk_level,
    }


def _detect_image(image_bytes):
    """파일 이름이나 MIME 선언 대신 실제 바이트의 PNG/JPEG 형식을 확인한다."""
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") and len(image_bytes) >= 24:
        width, height = struct.unpack(">II", image_bytes[16:24])
        if width and height:
            return ".png"
    if image_bytes.startswith(b"\xff\xd8\xff") and image_bytes.endswith(b"\xff\xd9"):
        return ".jpg"
    raise EvidenceValidationError("증거 이미지는 유효한 PNG 또는 JPEG 파일이어야 합니다.")


def validate_evidence(image_stream):
    if image_stream is None:
        raise EvidenceValidationError("image 파일 한 장이 필요합니다.")
    maximum = current_app.config["EVENT_IMAGE_MAX_BYTES"]
    image_bytes = image_stream.read(maximum + 1)
    if not image_bytes:
        raise EvidenceValidationError("증거 이미지가 비어 있습니다.")
    if len(image_bytes) > maximum:
        limit_label = f"{maximum // (1024 * 1024)}MB" if maximum >= 1024 * 1024 else f"{maximum}바이트"
        raise EvidenceValidationError(f"증거 이미지는 {limit_label} 이하여야 합니다.")
    extension = _detect_image(image_bytes)
    return image_bytes, extension, sha256(image_bytes).hexdigest()


def receive_event(payload, image_stream, now=None):
    """검증된 이미지 파일을 저장한 뒤 이벤트와 증거 경로를 DB에 연결한다."""
    current = now or datetime.now(timezone.utc)
    event = validate_event(payload, current)
    image_bytes, extension, content_hash = validate_evidence(image_stream)
    image_name = f'event-{event["event_id"]}-{content_hash[:24]}{extension}'
    evidence_dir = Path(current_app.config["EVIDENCE_DIR"])
    image_path = evidence_dir / image_name
    created = False
    if not image_path.exists():
        temporary_path = None
        try:
            # [원자적 파일 저장] 완성되지 않은 증거 이미지가 조회되지 않도록 이름을 마지막에 바꾼다.
            with tempfile.NamedTemporaryFile(dir=evidence_dir, suffix=".tmp", delete=False) as stream:
                temporary_path = Path(stream.name)
                stream.write(image_bytes)
            os.replace(temporary_path, image_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        created = True
    event.update(
        image_path=image_name,
        received_at=current.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    )
    try:
        return event_model.store_event(event)
    except Exception:
        # [DB 실패 정리] 이번 요청이 새로 만든 파일만 제거하고 기존 증거는 보존한다.
        if created:
            image_path.unlink(missing_ok=True)
        raise


def _parse_stored_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _display_time(value):
    # [화면 시각] DB의 UTC 시각을 관제 화면에서는 한국 시각으로 표시한다.
    korea = timezone(timedelta(hours=9))
    return _parse_stored_time(value).astimezone(korea).strftime("%m-%d %H:%M:%S")


# [증적 상태] 저장값은 INCOMPLETE·STORED·REJECTED 그대로 두고, 조립이 끝나지 않은
# 시간으로 지연·누락을 나눠 표시한다. 없는 결과를 관제가 만들어 내지 않는다.
EVIDENCE_STATE_LABELS = {
    "STORED": "저장 완료", "REJECTED": "거부", "DELAYED": "지연",
    "MISSING": "누락", "NONE": "없음",
}


def evidence_state(row, now=None):
    """이벤트 한 건의 증적 상태를 화면 표시용 값으로 계산한다."""
    status = row.get("evidence_status") if isinstance(row, dict) else None
    if status in {"STORED", "REJECTED"}:
        return status
    if status is None:
        # ROS 증적을 예고하지 않은 사건은 상태를 만들지 않는다.
        return "STORED" if row.get("image_path") else "NONE"
    updated_at = row.get("evidence_updated_at")
    if not updated_at:
        return "DELAYED"
    current = now or datetime.now(timezone.utc)
    age = (current - _parse_stored_time(updated_at)).total_seconds()
    if age >= current_app.config["EVIDENCE_MISSING_AFTER_SECONDS"]:
        return "MISSING"
    if age >= current_app.config["EVIDENCE_DELAYED_AFTER_SECONDS"]:
        return "DELAYED"
    return "INCOMPLETE"


def _event_view(row):
    event = dict(row)
    if event["x"] is None or event["y"] is None or not event["frame_id"]:
        location_label = "좌표 없음"
    else:
        location_label = f'{event["frame_id"]} ({event["x"]:.2f}, {event["y"]:.2f})'
    return {
        "event_id": event["event_id"],
        "message_id": event["message_id"],
        "robot_id": event["robot_id"],
        "robot_name": event.get("robot_name") or ROBOT_NAMES[event["robot_id"]],
        "event_type": event["event_type"],
        "event_label": EVENT_TYPE_LABELS.get(event["event_type"], event["event_type"]),
        "occurred_at": event["occurred_at"],
        "occurred_label": _display_time(event["occurred_at"]),
        "captured_at": event.get("captured_at"),
        "captured_label": _display_time(event["captured_at"]) if event.get("captured_at") else "—",
        "x": event["x"], "y": event["y"], "frame_id": event["frame_id"],
        "confidence": event.get("confidence"),
        "location_valid": bool(event.get("location_valid", 1)),
        "evidence_id": event.get("evidence_id"),
        "evidence_state": evidence_state(event),
        "evidence_state_label": EVIDENCE_STATE_LABELS.get(
            evidence_state(event), "조립 중"
        ),
        "location_label": location_label,
        "risk_level": event["risk_level"],
        "risk_label": RISK_LABELS[event["risk_level"]],
        "status": event["status"],
        "status_label": STATUS_LABELS[event["status"]],
        "next_status": STATUS_TRANSITIONS.get(event["status"]),
        "next_status_label": STATUS_LABELS.get(STATUS_TRANSITIONS.get(event["status"])),
        "has_evidence": bool(event.get("image_path")),
    }


def recent_events(limit=50, after=None):
    """저장된 최근 이벤트를 대시보드 표에 필요한 표시값으로 바꾼다."""
    return [_event_view(row) for row in event_model.list_recent(limit, after)]


def event_detail(event_id):
    """이벤트 한 건과 관제 처리 이력을 상세 화면용 값으로 만든다."""
    row = event_model.find_event(event_id)
    if row is None:
        return None
    event = _event_view(row)
    event["changes"] = [
        {
            "previous_status": change["previous_status"],
            "previous_label": STATUS_LABELS[change["previous_status"]],
            "new_status": change["new_status"],
            "new_label": STATUS_LABELS[change["new_status"]],
            "memo": change["memo"],
            "username": change["username"],
            "changed_at": change["changed_at"],
            "changed_label": _display_time(change["changed_at"]),
        }
        for change in event_model.list_changes(event_id)
    ]
    return event


def change_event_status(event_id, user_id, new_status, memo):
    """순차 상태 전이와 메모 길이를 검증하고 변경 이력을 저장한다."""
    if not isinstance(new_status, str) or new_status not in STATUS_LABELS:
        raise EventValidationError("지원하지 않는 이벤트 처리 상태입니다.")
    if not isinstance(memo, str):
        raise EventValidationError("메모는 문자열이어야 합니다.")
    normalized_memo = memo.strip()
    if len(normalized_memo) > 500:
        raise EventValidationError("메모는 500자 이하여야 합니다.")
    return event_model.change_status(
        event_id, user_id, new_status, normalized_memo, STATUS_TRANSITIONS
    )
