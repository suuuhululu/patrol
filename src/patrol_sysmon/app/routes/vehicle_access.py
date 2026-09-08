"""고정 웹캠 차량 입출차 내역 수신·목록 API."""

import sqlite3

from flask import Blueprint, current_app, g, jsonify, request

from ..models import dashboard_state as dashboard_state_model
from ..models.vehicle_access import VehicleAccessConflictError
from ..security import device_token_is_authorized, login_required
from ..services import vehicle_access_service


vehicle_access_bp = Blueprint("vehicle_access", __name__, url_prefix="/api/vehicle-access")


@vehicle_access_bp.post("")
def receive_access():
    """실제 토픽 연결 전 입차·출차 JSON 내역을 수신한다."""
    if not current_app.config.get("ROBOT_API_KEY"):
        return jsonify(error="access_api_disabled", message="입출차 수신 토큰이 설정되지 않았습니다."), 503
    if not device_token_is_authorized():
        return jsonify(error="unauthorized", message="입출차 수신 토큰을 확인하세요."), 401
    payload = request.get_json(silent=True)
    try:
        outcome, stored = vehicle_access_service.receive_access(payload)
    except vehicle_access_service.VehicleAccessValidationError as exc:
        return jsonify(error="invalid_vehicle_access", message=str(exc)), 400
    except VehicleAccessConflictError:
        return jsonify(error="vehicle_access_conflict", message="ID가 기존 기록과 충돌합니다."), 409
    except sqlite3.OperationalError:
        current_app.logger.exception("차량 입출차 DB 작업 실패")
        return jsonify(error="storage_unavailable", message="입출차 저장소를 사용할 수 없습니다."), 503
    except sqlite3.Error:
        current_app.logger.exception("차량 입출차 저장 실패")
        return jsonify(error="storage_error", message="입출차 기록을 저장하지 못했습니다."), 500
    return jsonify(result=outcome, access_id=stored["access_id"]), 201 if outcome == "accepted" else 200


@vehicle_access_bp.get("")
@login_required
def list_accesses():
    after = dashboard_state_model.get_clear_state(g.user["id"])["vehicle-access"]
    items = vehicle_access_service.recent_accesses(50, after)
    return jsonify(accesses=items, count=len(items))
