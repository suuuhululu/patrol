"""로봇 상태의 임시 HTTP 수신과 로그인 사용자 조회 API."""

import sqlite3

from flask import Blueprint, current_app, jsonify, request

from ..models.robot import MessageIdConflictError, StaleStatusError
from ..security import device_token_is_authorized, login_required
from ..services import robot_service


robots_bp = Blueprint("robots", __name__, url_prefix="/api/robots")


@robots_bp.post("/status")
def receive_status():
    """ROS 토픽 확정 전 로봇 상태를 같은 내부 서비스에 전달한다."""
    if not current_app.config.get("ROBOT_API_KEY"):
        return jsonify(error="robot_api_disabled", message="로봇 수신 토큰이 설정되지 않았습니다."), 503
    if not device_token_is_authorized():
        return jsonify(error="unauthorized", message="로봇 수신 토큰을 확인하세요."), 401
    if not request.is_json:
        return jsonify(error="invalid_content_type", message="application/json 요청이 필요합니다."), 415
    try:
        outcome, stored = robot_service.receive_status(request.get_json(silent=True))
    except robot_service.StatusValidationError as exc:
        current_app.logger.warning("로봇 상태 입력 거부: %s", exc)
        return jsonify(error="invalid_status", message=str(exc)), 400
    except MessageIdConflictError:
        current_app.logger.warning("로봇 상태 message_id 충돌")
        return jsonify(error="message_id_conflict", message="같은 message_id에 다른 내용이 있습니다."), 409
    except StaleStatusError as exc:
        current_app.logger.info("오래된 로봇 상태 무시: latest=%s", exc.args[0])
        return jsonify(error="stale_status", message="현재 상태보다 오래된 메시지입니다.", latest_observed_at=exc.args[0]), 409
    except sqlite3.OperationalError:
        # [잠금·저장소 오류] 로봇이 재시도할 수 있게 일시 실패를 JSON으로 구분한다.
        current_app.logger.exception("로봇 상태 DB 작업 실패")
        return jsonify(error="storage_unavailable", message="상태 저장소를 잠시 사용할 수 없습니다."), 503
    except sqlite3.Error:
        current_app.logger.exception("로봇 상태 DB 저장 실패")
        return jsonify(error="storage_error", message="상태를 저장하지 못했습니다."), 500
    code = 201 if outcome == "accepted" else 200
    return jsonify(result=outcome, robot_id=stored["robot_id"], message_id=stored["message_id"]), code


@robots_bp.get("/status")
@login_required
def list_status():
    # [화면 갱신] 비로그인 외부에는 로봇 좌표·상태를 공개하지 않는다.
    robots = robot_service.dashboard_robots()
    return jsonify(robots=robots, fleet_status=robot_service.fleet_summary(robots))
