"""화재·누수·장애물 이벤트의 화면 표시값과 관제 처리 상태 기록."""

from datetime import datetime, timedelta, timezone
import struct

from ..models import event as event_model
from .robot_service import ROBOT_NAMES


# [제품 범위] 관제가 이벤트 로그로 남기는 이상은 화재·누수·장애물 세 종류다.
# 계약 enum에는 LIGHTING·FACILITY_DAMAGE도 있지만 이번 범위에서는 저장하지 않는다.
EVENT_TYPES = {"FIRE", "LEAK", "OBSTACLE"}
EVENT_TYPE_LABELS = {
    "FIRE": "화재", "LEAK": "누수", "OBSTACLE": "장애물",
    # 아래 둘은 더 이상 저장하지 않는다. 범위 축소 전에 저장된 이력을 읽을 때만 사용한다.
    "LIGHTING": "조명 이상", "FACILITY_DAMAGE": "시설물 파손",
    # ReportDetection에 종류 필드가 생기기 전에 받은 사건이다.
    "UNKNOWN": "미분류",
}
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


def _detect_image(image_bytes):
    """파일 이름이나 MIME 선언 대신 실제 바이트의 PNG/JPEG 형식을 확인한다."""
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") and len(image_bytes) >= 24:
        width, height = struct.unpack(">II", image_bytes[16:24])
        if width and height:
            return ".png"
    if image_bytes.startswith(b"\xff\xd8\xff") and image_bytes.endswith(b"\xff\xd9"):
        return ".jpg"
    raise EvidenceValidationError("증거 이미지는 유효한 PNG 또는 JPEG 파일이어야 합니다.")


def _parse_stored_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _display_time(value):
    # [화면 시각] DB의 UTC 시각을 관제 화면에서는 한국 시각으로 표시한다.
    korea = timezone(timedelta(hours=9))
    return _parse_stored_time(value).astimezone(korea).strftime("%m-%d %H:%M:%S")


def _event_view(row):
    event = dict(row)
    if event["x"] is None or event["y"] is None or not event["frame_id"]:
        location_label = "좌표 없음"
    else:
        location_label = f'{event["frame_id"]} ({event["x"]:.2f}, {event["y"]:.2f})'
    return {
        "event_id": event["event_id"],
        "robot_id": event["robot_id"],
        "robot_name": event.get("robot_name") or ROBOT_NAMES[event["robot_id"]],
        "event_type": event["event_type"],
        "event_label": EVENT_TYPE_LABELS.get(event["event_type"], event["event_type"]),
        "occurred_at": event["occurred_at"],
        "occurred_label": _display_time(event["occurred_at"]),
        "captured_at": event.get("captured_at"),
        "captured_label": _display_time(event["captured_at"]) if event.get("captured_at") else "—",
        "x": event["x"], "y": event["y"], "frame_id": event["frame_id"],
        "location_label": location_label,
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
