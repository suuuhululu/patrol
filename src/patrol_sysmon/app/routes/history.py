"""로그인 사용자의 통합 이력 검색 페이지와 JSON API."""

from urllib.parse import urlencode

from flask import Blueprint, jsonify, render_template, request, url_for

from ..security import login_required
from ..services import event_service, history_service


history_bp = Blueprint("history", __name__)


def _with_links(record):
    item = dict(record)
    if item["has_evidence"] and item["record_type"] == "EVENT":
        item["evidence_url"] = url_for("events.evidence_image", event_id=item["event_id"])
    else:
        item["evidence_url"] = None
    return item


def _page_url(page):
    values = request.args.to_dict(flat=True)
    values["page"] = page
    return url_for("history.index") + "?" + urlencode(values)


@history_bp.get("/history")
@login_required
def index():
    error = None
    try:
        result = history_service.search_history(request.args)
    except history_service.HistoryValidationError as exc:
        error = str(exc)
        result = history_service.search_history({})
    result["records"] = [_with_links(record) for record in result["records"]]
    result["previous_url"] = _page_url(result["page"] - 1) if result["page"] > 1 else None
    result["next_url"] = _page_url(result["page"] + 1) if result["page"] < result["pages"] else None
    return render_template(
        "history.html", result=result, error=error,
        type_labels=history_service.RECORD_TYPE_LABELS,
        status_labels=event_service.STATUS_LABELS,
    ), 400 if error else 200


@history_bp.get("/api/history")
@login_required
def search_api():
    try:
        result = history_service.search_history(request.args)
    except history_service.HistoryValidationError as exc:
        return jsonify(error="invalid_filter", message=str(exc)), 400
    result["records"] = [_with_links(record) for record in result["records"]]
    # [내부 검색값 제거] UTC 변환값은 서버 조회용이며 브라우저 응답에 중복 노출하지 않는다.
    filters = result["filters"]
    result["filters"] = {
        "type": filters["record_type"], "robot": filters["robot_id"] or "ALL",
        "status": filters["event_status"] or "ALL",
        "from": filters["from_date"], "to": filters["to_date"], "keyword": filters["keyword"],
    }
    return jsonify(result)
