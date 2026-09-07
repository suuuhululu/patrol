"""PatrolVisit·PatrolReport 계약 검증과 순찰 화면 표시 처리."""

from datetime import datetime, timedelta, timezone
import math
import re
import uuid

from ..models import patrol as patrol_model


UUID_V4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
ROBOT_NAMES = {"AMR1": "로봇 1", "AMR2": "로봇 2"}
VISIT_RESULTS = {"SUCCEEDED": "완료", "SKIPPED": "건너뜀", "FAILED": "실패"}
REPORT_RESULTS = {"SUCCEEDED": "완료", "FAILED": "실패", "CANCELED": "취소"}
# 계약상 관제는 없는 결과를 대필하지 않는다. 아래 라벨은 화면 계산값이며 메시지 enum이 아니다.
UNREPORTED_LABEL = "보고 없음"


class PatrolValidationError(ValueError):
    """AMR 순찰 계약 필드가 확정 형식과 다를 때 사용한다."""


def _uuid_v4(value, field):
    if not isinstance(value, str) or not UUID_V4_PATTERN.fullmatch(value):
        raise PatrolValidationError(f"{field}는 소문자 UUID v4여야 합니다.")
    if str(uuid.UUID(value, version=4)) != value:
        raise PatrolValidationError(f"{field}는 소문자 UUID v4여야 합니다.")
    return value


def _optional_id(payload, field):
    # [선택 ID] 계약에서 값이 없는 선택 ID는 빈 문자열이다. 임의 값으로 채우지 않는다.
    value = payload.get(field, "")
    if not isinstance(value, str):
        raise PatrolValidationError(f"{field}는 문자열이어야 합니다.")
    return value.strip()


def _timestamp(value, now, field, required=True):
    if value in (None, "") and not required:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PatrolValidationError(f"{field}는 시간대가 포함된 ISO 8601 시각이어야 합니다.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PatrolValidationError(f"{field}에 시간대가 필요합니다.")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > now + timedelta(minutes=5):
        raise PatrolValidationError(f"{field}가 서버 시각보다 5분 이상 미래입니다.")
    return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _reason_code(payload):
    value = payload.get("reason_code", 0)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 65535:
        raise PatrolValidationError("reason_code는 0에서 65535 사이의 정수여야 합니다.")
    return value


def _count(payload, field):
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PatrolValidationError(f"{field}는 0 이상의 정수여야 합니다.")
    return value


def _coordinate(payload, field, location_required):
    value = payload.get(field)
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        if location_required:
            raise PatrolValidationError(f"{field} 값이 필요합니다.")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PatrolValidationError(f"{field}는 숫자여야 합니다.")
    return float(value)


def validate_visit(payload, now=None):
    """PatrolVisit을 저장 가능한 계약 값으로 정규화한다."""
    if not isinstance(payload, dict):
        raise PatrolValidationError("PatrolVisit 객체가 필요합니다.")
    current = now or datetime.now(timezone.utc)
    robot_id = payload.get("robot_id")
    if robot_id not in ROBOT_NAMES:
        raise PatrolValidationError("robot_id는 AMR1 또는 AMR2여야 합니다.")
    waypoint_id = payload.get("waypoint_id")
    if not isinstance(waypoint_id, str) or not waypoint_id.strip():
        raise PatrolValidationError("waypoint_id 값이 필요합니다.")
    result = payload.get("result")
    if result not in VISIT_RESULTS:
        raise PatrolValidationError("result는 SUCCEEDED, SKIPPED, FAILED 중 하나여야 합니다.")
    frame_id = payload.get("frame_id")
    if frame_id not in (None, "", "map"):
        raise PatrolValidationError("PatrolVisit pose의 frame_id는 map이어야 합니다.")
    return {
        "visit_id": _uuid_v4(payload.get("visit_id"), "visit_id"),
        "message_id": _uuid_v4(payload.get("message_id"), "message_id"),
        "robot_id": robot_id,
        "patrol_id": _optional_id(payload, "patrol_id"),
        "mission_id": _optional_id(payload, "mission_id"),
        "command_id": _optional_id(payload, "command_id"),
        "waypoint_id": waypoint_id.strip(),
        "x": _coordinate(payload, "x", False),
        "y": _coordinate(payload, "y", False),
        "frame_id": frame_id or None,
        "result": result,
        "reason_code": _reason_code(payload),
        "reason": str(payload.get("reason", "")),
        "arrived_at": _timestamp(payload.get("arrived_at"), current, "arrived_at"),
        "completed_at": _timestamp(
            payload.get("completed_at"), current, "completed_at", required=False
        ),
        "received_at": current.astimezone(timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z"),
    }


def validate_report(payload, now=None):
    """PatrolReport를 저장 가능한 계약 값으로 정규화한다."""
    if not isinstance(payload, dict):
        raise PatrolValidationError("PatrolReport 객체가 필요합니다.")
    current = now or datetime.now(timezone.utc)
    robot_id = payload.get("robot_id")
    if robot_id not in ROBOT_NAMES:
        raise PatrolValidationError("robot_id는 AMR1 또는 AMR2여야 합니다.")
    result = payload.get("result")
    if result not in REPORT_RESULTS:
        raise PatrolValidationError("result는 SUCCEEDED, FAILED, CANCELED 중 하나여야 합니다.")
    reason_code = _reason_code(payload)
    reason = str(payload.get("reason", "")).strip()
    # [계약 3.8] 실패·취소 보고에는 원인 코드와 설명이 반드시 있어야 한다.
    if result in {"FAILED", "CANCELED"} and (reason_code == 0 or not reason):
        raise PatrolValidationError("FAILED·CANCELED 보고에는 reason_code와 reason이 필요합니다.")
    patrol_id = _optional_id(payload, "patrol_id")
    if not patrol_id:
        raise PatrolValidationError("patrol_id 값이 필요합니다.")
    planned = _count(payload, "planned_visit_count")
    completed = _count(payload, "completed_visit_count")
    if completed > planned:
        raise PatrolValidationError("완료 방문 수가 계획 방문 수보다 클 수 없습니다.")
    return {
        "patrol_id": patrol_id,
        "report_id": _uuid_v4(payload.get("report_id"), "report_id"),
        "message_id": _uuid_v4(payload.get("message_id"), "message_id"),
        "robot_id": robot_id,
        "mission_id": _optional_id(payload, "mission_id"),
        "command_id": _optional_id(payload, "command_id"),
        "result": result,
        "reason_code": reason_code,
        "reason": reason,
        "started_at": _timestamp(payload.get("started_at"), current, "started_at"),
        "ended_at": _timestamp(
            payload.get("ended_at"), current, "ended_at", required=False
        ),
        "planned_visit_count": planned,
        "completed_visit_count": completed,
        "received_at": current.astimezone(timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z"),
    }


def receive_visit(payload, now=None):
    return patrol_model.store_visit(validate_visit(payload, now))


def receive_report(payload, now=None):
    return patrol_model.store_report(validate_report(payload, now))


def _display_time(value):
    if not value:
        return "—"
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone(timedelta(hours=9))).strftime("%m-%d %H:%M:%S")


def dashboard_patrol(visit_limit=10, report_limit=5):
    """최근 방문·보고와 결과가 오지 않은 순찰을 화면용 JSON으로 만든다."""
    visits = [{
        "visit_id": row["visit_id"], "robot_id": row["robot_id"],
        "robot_name": ROBOT_NAMES.get(row["robot_id"], row["robot_id"]),
        "patrol_id": row["patrol_id"], "waypoint_id": row["waypoint_id"],
        "result": row["result"], "result_label": VISIT_RESULTS[row["result"]],
        "reason_code": row["reason_code"], "reason": row["reason"],
        "arrived_at": row["arrived_at"], "arrived_label": _display_time(row["arrived_at"]),
    } for row in patrol_model.recent_visits(visit_limit)]
    reports = [{
        "patrol_id": row["patrol_id"], "robot_id": row["robot_id"],
        "robot_name": ROBOT_NAMES.get(row["robot_id"], row["robot_id"]),
        "result": row["result"], "result_label": REPORT_RESULTS[row["result"]],
        "reason_code": row["reason_code"], "reason": row["reason"],
        "planned_visit_count": row["planned_visit_count"],
        "completed_visit_count": row["completed_visit_count"],
        "started_label": _display_time(row["started_at"]),
        "ended_label": _display_time(row["ended_at"]),
    } for row in patrol_model.recent_reports(report_limit)]
    unreported = [{
        "patrol_id": row["patrol_id"], "robot_id": row["robot_id"],
        "robot_name": ROBOT_NAMES.get(row["robot_id"], row["robot_id"]),
        "visit_count": row["visit_count"],
        "last_arrived_label": _display_time(row["last_arrived_at"]),
        "result_label": UNREPORTED_LABEL,
    } for row in patrol_model.unreported_patrols(report_limit)]
    return {
        "visits": visits, "reports": reports, "unreported": unreported,
        "latest_visit": visits[0] if visits else None,
        "state_label": (
            f'{visits[0]["waypoint_id"]} {visits[0]["result_label"]}'
            if visits else "순찰 기록 대기"
        ),
    }
