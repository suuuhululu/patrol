"""이상 이벤트 목록·상세·증거 이미지 조회와 관제 처리 상태 변경 API.

사건 수신은 ROS 서비스 ReportDetection(app/ros/node.py)이 맡는다. HTTP로는 받지 않는다.
"""

from pathlib import Path
import sqlite3

from flask import Blueprint, current_app, g, jsonify, request, send_file, url_for

from ..models import event as event_model
from ..models import dashboard_state as dashboard_state_model
from ..models.event import EventNotFoundError, EventStatusTransitionError
from ..security import login_required, roles_required
from ..services import event_service


events_bp = Blueprint("events", __name__, url_prefix="/api/events")


def _with_evidence_url(event):
    data = dict(event)
    data["evidence_url"] = (
        url_for("events.evidence_image", event_id=event["event_id"])
        if event["has_evidence"] else None
    )
    return data


@events_bp.get("")
@login_required
def list_events():
    # [8단계: 이벤트 목록] 브라우저에는 최근 50건의 표시값과 보호된 이미지 URL만 제공한다.
    after = dashboard_state_model.get_clear_state(g.user["id"])["events"]
    events = [_with_evidence_url(event) for event in event_service.recent_events(50, after)]
    return jsonify(events=events, count=len(events))


@events_bp.get("/<event_id>")
@login_required
def event_detail(event_id):
    event = event_service.event_detail(event_id)
    if event is None:
        return jsonify(error="event_not_found", message="이벤트를 찾을 수 없습니다."), 404
    return jsonify(event=_with_evidence_url(event))


@events_bp.post("/<event_id>/status")
@roles_required("ADMIN", "OPERATOR")
def change_status(event_id):
    """관제 처리 상태와 메모를 기록하며 로봇 운영 명령은 생성하지 않는다."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="invalid_request", message="JSON 객체가 필요합니다."), 400
    try:
        previous, current = event_service.change_event_status(
            event_id, g.user["id"], payload.get("status"), payload.get("memo", "")
        )
    except event_service.EventValidationError as exc:
        return jsonify(error="invalid_status", message=str(exc)), 400
    except EventNotFoundError:
        return jsonify(error="event_not_found", message="이벤트를 찾을 수 없습니다."), 404
    except EventStatusTransitionError as exc:
        previous = exc.args[0]
        return jsonify(
            error="invalid_transition",
            message=f'{event_service.STATUS_LABELS[previous]} 상태에서 요청한 단계로 변경할 수 없습니다.',
            current_status=previous,
        ), 409
    except sqlite3.OperationalError:
        current_app.logger.exception("이벤트 상태 DB 작업 실패")
        return jsonify(error="storage_unavailable", message="이벤트 저장소를 잠시 사용할 수 없습니다."), 503
    except sqlite3.Error:
        current_app.logger.exception("이벤트 상태 저장 실패")
        return jsonify(error="storage_error", message="처리 상태를 저장하지 못했습니다."), 500
    return jsonify(
        result="updated", previous_status=previous, status=current,
        status_label=event_service.STATUS_LABELS[current],
    )


@events_bp.get("/<event_id>/evidence")
@login_required
def evidence_image(event_id):
    row = event_model.find_event(event_id)
    if row is None or not row["image_path"]:
        return jsonify(error="evidence_not_found", message="증거 이미지를 찾을 수 없습니다."), 404
    evidence_dir = Path(current_app.config["EVIDENCE_DIR"]).resolve()
    image_path = (evidence_dir / row["image_path"]).resolve()
    # [경로 보호] DB 파일명이 변조되어도 증거 폴더 밖의 파일은 제공하지 않는다.
    if image_path.parent != evidence_dir or not image_path.is_file():
        return jsonify(error="evidence_not_found", message="증거 이미지를 찾을 수 없습니다."), 404
    mimetype = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    return send_file(image_path, mimetype=mimetype, conditional=True)
