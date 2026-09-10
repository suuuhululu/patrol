"""통합 이력 검색 조건 검증과 DB 코드의 화면 표시값 변환."""

from datetime import date, datetime, time, timedelta, timezone
from math import ceil
from zoneinfo import ZoneInfo

from . import event_service, robot_service
from ..models import history as history_model


KST = ZoneInfo("Asia/Seoul")
RECORD_TYPE_LABELS = {
    "ALL": "전체 기록", "EVENT": "이상 이벤트", "EVENT_CHANGE": "이벤트 처리",
    "ROBOT_STATUS": "로봇 상태", "PATROL": "순찰", "HANDOVER": "로봇 교대",
    "VEHICLE_ACCESS": "차량 입출차",
    "CCTV_STATE": "CCTV 차량 상태", "PATROL_PERMIT": "순찰 허용 조건",
    "PATROL_VISIT": "관측점 방문", "ESTOP": "비상정지",
}
PATROL_STATUS_LABELS = {
    # [20단계] 순찰 결과 이름. v2에서는 Patrol Action 목표 상태에서 옮긴다.
    "SUCCEEDED": "완료", "FAILED": "실패", "CANCELED": "취소",
}
HANDOVER_STATUS_LABELS = {
    "REQUESTED": "요청", "IN_PROGRESS": "진행중", "COMPLETED": "완료", "FAILED": "실패",
}
VEHICLE_DIRECTION_LABELS = {"ENTRY": "입차", "EXIT": "출차"}
PATROL_VISIT_LABELS = {"SUCCEEDED": "완료", "SKIPPED": "건너뜀", "FAILED": "실패"}
CCTV_STATE_LABELS = {
    "ENTERING": "진입 중", "PARKED": "주차 완료",
    "EXITING": "출차 중", "EXITED": "출차 완료",
}
PERMIT_STATUS_LABELS = {"ALLOWED": "순찰 허용", "BLOCKED": "순찰 제한"}
PER_PAGE = 50


class HistoryValidationError(ValueError):
    """검색 조건이 허용 목록·날짜·길이 범위를 벗어날 때 사용한다."""


def _choice(args, key, allowed, default="ALL"):
    value = (args.get(key, default) or default).strip().upper()
    if value not in allowed:
        raise HistoryValidationError(f"{key} 검색 조건이 올바르지 않습니다.")
    return None if value == "ALL" else value


def _date_value(args, key):
    value = (args.get(key, "") or "").strip()
    if not value:
        return None, ""
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise HistoryValidationError(f"{key}는 YYYY-MM-DD 날짜여야 합니다.") from exc
    return parsed, value


def validate_filters(args):
    """브라우저와 API가 공유할 검색값을 고정된 내부 코드와 UTC 범위로 바꾼다."""
    raw_type = (args.get("type", "ALL") or "ALL").strip().upper()
    if raw_type not in RECORD_TYPE_LABELS:
        raise HistoryValidationError("type 검색 조건이 올바르지 않습니다.")
    robot_id = _choice(args, "robot", {"ALL", "AMR1", "AMR2"})
    event_status = _choice(args, "status", {"ALL", *event_service.STATUS_LABELS})
    from_date, from_text = _date_value(args, "from")
    to_date, to_text = _date_value(args, "to")
    if from_date and to_date and from_date > to_date:
        raise HistoryValidationError("시작 날짜는 종료 날짜보다 늦을 수 없습니다.")
    keyword = (args.get("keyword", "") or "").strip()
    if len(keyword) > 100:
        raise HistoryValidationError("검색어는 100자 이하여야 합니다.")
    try:
        page = int(args.get("page", 1))
    except (TypeError, ValueError) as exc:
        raise HistoryValidationError("page는 1 이상의 정수여야 합니다.") from exc
    if not 1 <= page <= 100_000:
        raise HistoryValidationError("page는 1 이상의 정수여야 합니다.")

    start_utc = None
    end_utc = None
    if from_date:
        start_utc = datetime.combine(from_date, time.min, KST).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if to_date:
        end_utc = datetime.combine(to_date + timedelta(days=1), time.min, KST).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "record_type": raw_type, "robot_id": robot_id,
        "event_status": event_status, "keyword": keyword,
        "from_date": from_text, "to_date": to_text,
        "start_utc": start_utc, "end_utc": end_utc,
        "page": page, "per_page": PER_PAGE,
    }


def _local_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(KST)


def _status_label(record_type, status):
    if record_type in {"EVENT", "EVENT_CHANGE"}:
        return event_service.STATUS_LABELS.get(status, status)
    if record_type == "ROBOT_STATUS":
        return robot_service.MISSION_LABELS.get(status, status)
    if record_type == "PATROL":
        return PATROL_STATUS_LABELS.get(status, status)
    if record_type == "VEHICLE_ACCESS":
        return VEHICLE_DIRECTION_LABELS.get(status, status)
    if record_type == "PATROL_VISIT":
        return PATROL_VISIT_LABELS.get(status, status)
    if record_type == "ESTOP":
        return "활성" if status == "ACTIVE" else "해제"
    if record_type == "CCTV_STATE":
        return CCTV_STATE_LABELS.get(status, status)
    if record_type == "PATROL_PERMIT":
        return PERMIT_STATUS_LABELS.get(status, status)
    return HANDOVER_STATUS_LABELS.get(status, status)


def _record(row):
    local = _local_time(row["recorded_at"])
    record_type = row["record_type"]
    title = (
        event_service.EVENT_TYPE_LABELS.get(row["title_code"], row["title_code"])
        if record_type == "EVENT" else RECORD_TYPE_LABELS[record_type]
    )
    return {
        "record_type": record_type,
        "record_type_label": RECORD_TYPE_LABELS[record_type],
        "record_id": row["record_id"],
        "recorded_at": row["recorded_at"],
        "recorded_label": local.strftime("%Y-%m-%d %H:%M:%S"),
        "robot_id": row["robot_id"], "robot_name": row["robot_name"],
        "title": title, "summary": row["summary"],
        "status_code": row["status_code"],
        "status_label": _status_label(record_type, row["status_code"]),
        "event_id": row["event_id"], "actor": row["actor"],
        "has_evidence": bool(row["has_evidence"]),
    }


def search_history(args):
    filters = validate_filters(args)
    rows, total = history_model.search(filters)
    pages = max(1, ceil(total / filters["per_page"]))
    if total and filters["page"] > pages:
        # [페이지 경계] 데이터 삭제 후 오래된 페이지 URL을 열어도 마지막 페이지를 보여준다.
        filters["page"] = pages
        rows, total = history_model.search(filters)
    return {
        "records": [_record(row) for row in rows],
        "total": total, "page": filters["page"], "pages": pages,
        "per_page": filters["per_page"], "filters": filters,
    }
