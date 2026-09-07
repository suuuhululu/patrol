"""네 카메라의 임시 최신 프레임 수신과 로그인 사용자용 영상 API."""

from flask import Blueprint, current_app, jsonify, request, send_file, url_for

from ..security import device_token_is_authorized, login_required
from ..services import camera_service
from ..services.camera_service import CameraFrameConflictError, StaleCameraFrameError


cameras_bp = Blueprint("cameras", __name__, url_prefix="/api/cameras")


@cameras_bp.post("/<camera_id>/frame")
def receive_frame(camera_id):
    """ROS 연결 전 PNG/JPEG 한 장을 받아 해당 카메라의 최신 프레임으로 교체한다."""
    if not current_app.config.get("ROBOT_API_KEY"):
        return jsonify(error="camera_api_disabled", message="영상 수신 토큰이 설정되지 않았습니다."), 503
    if not device_token_is_authorized():
        return jsonify(error="unauthorized", message="영상 수신 토큰을 확인하세요."), 401
    if request.mimetype not in {"image/png", "image/jpeg"}:
        return jsonify(error="invalid_content_type", message="image/png 또는 image/jpeg 요청이 필요합니다."), 415
    try:
        outcome, stored = camera_service.receive_frame(
            camera_id,
            request.headers.get("X-Frame-Id"),
            request.headers.get("X-Captured-At"),
            request.stream,
        )
    except camera_service.CameraValidationError as exc:
        current_app.logger.warning("영상 입력 거부: %s", exc)
        return jsonify(error="invalid_frame", message=str(exc)), 400
    except CameraFrameConflictError:
        return jsonify(error="frame_id_conflict", message="같은 frame_id에 다른 영상이 있습니다."), 409
    except StaleCameraFrameError as exc:
        return jsonify(error="stale_frame", message="현재 영상보다 오래된 프레임입니다.",
                       latest_captured_at=exc.args[0]), 409
    except OSError:
        current_app.logger.exception("최신 영상 파일 저장 실패")
        return jsonify(error="storage_error", message="영상 프레임을 저장하지 못했습니다."), 500
    code = 201 if outcome == "accepted" else 200
    return jsonify(result=outcome, camera_id=stored["camera_id"], frame_id=stored["frame_id"]), code


@cameras_bp.get("")
@login_required
def list_cameras():
    # [9단계: 영상 상태] 장치 토큰을 노출하지 않고 로그인 세션으로 네 카메라 상태만 조회한다.
    cameras = camera_service.dashboard_cameras()
    for camera in cameras:
        camera["frame_url"] = (
            url_for("cameras.latest_frame", camera_id=camera["id"], version=camera["version"])
            if camera["available"] else None
        )
    return jsonify(cameras=cameras)


@cameras_bp.get("/<camera_id>/frame")
@login_required
def latest_frame(camera_id):
    try:
        metadata = camera_service.frame_metadata(camera_id)
    except camera_service.CameraValidationError as exc:
        return jsonify(error="camera_not_found", message=str(exc)), 404
    if metadata is None:
        return jsonify(error="frame_not_found", message="수신된 영상 프레임이 없습니다."), 404
    image_path = camera_service.frame_path(camera_id)
    return send_file(image_path, mimetype=metadata["mimetype"], conditional=True, max_age=0)
