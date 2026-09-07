"""Nav2 지도 임시 수신과 로그인 사용자용 지도 조회 API."""

from pathlib import Path
import sqlite3

from flask import Blueprint, current_app, jsonify, request, send_file, url_for

from ..models import map as map_model
from ..models.map import MapMessageConflictError, StaleMapError
from ..security import device_token_is_authorized, login_required
from ..services import map_service


maps_bp = Blueprint("maps", __name__, url_prefix="/api/maps")


@maps_bp.post("/current")
def receive_map():
    """ROS 연결 전 OccupancyGrid 형태의 JSON을 지도 서비스에 전달한다."""
    if not current_app.config.get("ROBOT_API_KEY"):
        return jsonify(error="map_api_disabled", message="지도 수신 토큰이 설정되지 않았습니다."), 503
    if not device_token_is_authorized():
        return jsonify(error="unauthorized", message="지도 수신 토큰을 확인하세요."), 401
    if not request.is_json:
        return jsonify(error="invalid_content_type", message="application/json 요청이 필요합니다."), 415
    try:
        outcome, stored = map_service.receive_map(request.get_json(silent=True))
    except map_service.MapValidationError as exc:
        current_app.logger.warning("지도 입력 거부: %s", exc)
        return jsonify(error="invalid_map", message=str(exc)), 400
    except MapMessageConflictError:
        return jsonify(error="message_id_conflict", message="같은 message_id에 다른 지도 내용이 있습니다."), 409
    except StaleMapError as exc:
        return jsonify(error="stale_map", message="현재 지도보다 오래된 메시지입니다.",
                       latest_observed_at=exc.args[0]), 409
    except sqlite3.OperationalError:
        current_app.logger.exception("지도 DB 작업 실패")
        return jsonify(error="storage_unavailable", message="지도 저장소를 잠시 사용할 수 없습니다."), 503
    except (OSError, sqlite3.Error):
        current_app.logger.exception("지도 파일 또는 DB 저장 실패")
        return jsonify(error="storage_error", message="지도를 저장하지 못했습니다."), 500
    code = 201 if outcome == "accepted" else 200
    return jsonify(result=outcome, message_id=stored["message_id"]), code


@maps_bp.get("/current")
@login_required
def current_map():
    data = map_service.dashboard_map()
    if data["available"]:
        data["image_url"] = url_for("maps.current_image", version=data["content_hash"][:16])
    return jsonify(data)


@maps_bp.get("/current/image")
@login_required
def current_image():
    row = map_model.current_map()
    if row is None:
        return jsonify(error="map_not_found", message="수신된 지도가 없습니다."), 404
    map_dir = Path(current_app.config["MAP_DIR"]).resolve()
    image_path = (map_dir / row["image_path"]).resolve()
    # [경로 보호] DB 값이 변조되어도 지도 폴더 밖의 파일을 제공하지 않는다.
    if image_path.parent != map_dir or not image_path.is_file():
        return jsonify(error="map_image_missing", message="지도 이미지 파일을 찾을 수 없습니다."), 404
    return send_file(image_path, mimetype="image/png", conditional=True)
