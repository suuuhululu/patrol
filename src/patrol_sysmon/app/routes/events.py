"""화재·누수·장애물 이벤트 수신과 보호된 증거 이미지 조회 API."""

import json
from pathlib import Path
import sqlite3

from flask import Blueprint, current_app, g, jsonify, request, send_file, url_for

from ..models import event as event_model
from ..models import dashboard_state as dashboard_state_model
from ..models.detection import DetectionMessageConflictError
from ..models.event import EventNotFoundError, EventStatusTransitionError
from ..security import device_token_is_authorized, login_required, roles_required
from ..services import detection_service, event_service


events_bp = Blueprint("events", __name__, url_prefix="/api/events")


def _with_evidence_url(event):
    data = dict(event)
    data["evidence_url"] = (
        url_for("events.evidence_image", event_id=event["event_id"])
        if event["has_evidence"] else None
    )
    return data


@events_bp.post("")
def receive_event():
    """ROS 없이 시험할 때 ReportDetection과 같은 사건 한 건을 HTTP로 받는다.

    metadata JSON: robot_id(AMR1|AMR2), event_id(소문자 UUID v4), detected_at(ISO 8601),
    x, y, event_type(FIRE|LEAK|OBSTACLE). image: 증거 사진 파일 한 장.
    검증·중복 판정·저장은 ReportDetection 서비스와 같은 코드를 쓴다.
    """
    if not current_app.config.get("ROBOT_API_KEY"):
        return jsonify(error="event_api_disabled", message="이벤트 수신 토큰이 설정되지 않았습니다."), 503
    if not device_token_is_authorized():
        return jsonify(error="unauthorized", message="이벤트 수신 토큰을 확인하세요."), 401
    if not request.mimetype or not request.mimetype.startswith("multipart/form-data"):
        return jsonify(error="invalid_content_type", message="multipart/form-data 요청이 필요합니다."), 415
    try:
        metadata = json.loads(request.form.get("metadata", ""))
    except (json.JSONDecodeError, TypeError):
        return jsonify(error="invalid_metadata", message="metadata에 JSON 객체가 필요합니다."), 400
    if not isinstance(metadata, dict):
        return jsonify(error="invalid_metadata", message="metadata에 JSON 객체가 필요합니다."), 400
    image = request.files.get("image")
    # 크기 제한 검사는 서비스가 한다. 제한보다 1바이트 더 읽어 초과 여부만 알 수 있게 한다.
    limit = current_app.config["REPORT_IMAGE_MAX_BYTES"]
    payload = {**metadata, "image": image.stream.read(limit + 1) if image else b""}
    try:
        outcome, stored = detection_service.receive_report(payload)
    except detection_service.DetectionValidationError as exc:
        current_app.logger.warning("이벤트 입력 거부: %s", exc)
        return jsonify(error="invalid_event", message=str(exc)), 400
    except DetectionMessageConflictError:
        return jsonify(error="event_conflict", message="같은 event_id에 다른 내용이 이미 저장돼 있습니다."), 409
    except sqlite3.OperationalError:
        current_app.logger.exception("이벤트 DB 작업 실패")
        return jsonify(error="storage_unavailable", message="이벤트 저장소를 잠시 사용할 수 없습니다."), 503
    except (OSError, sqlite3.Error):
        current_app.logger.exception("이벤트 이미지 또는 DB 저장 실패")
        return jsonify(error="storage_error", message="이벤트를 저장하지 못했습니다."), 500
    code = 201 if outcome == "accepted" else 200
    return jsonify(
        result=outcome,
        event_id=stored["event_id"],
        detail=stored.get("detail", ""),
    ), code


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
