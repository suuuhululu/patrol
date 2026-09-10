"""ROS adapter가 저장한 로봇별 costmap의 로그인 사용자 조회 API."""

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file, url_for

from ..models import costmap as costmap_model
from ..security import login_required
from ..services import costmap_service


costmaps_bp = Blueprint("costmaps", __name__, url_prefix="/api/costmaps")


@costmaps_bp.get("")
@login_required
def list_costmaps():
    grids = costmap_service.dashboard_costmaps()
    for grid in grids:
        grid["image_url"] = (
            url_for(
                "costmaps.costmap_image",
                robot_id=grid["robot_id"], layer=grid["layer"],
                version=grid["content_hash"][:16],
            )
            if grid["available"] else None
        )
    return jsonify(costmaps=grids)


def nav_map_state(robot_id=None):
    """NAV 지도 패널이 그릴 상태에 바탕 costmap 이미지 주소를 붙인다."""
    data = costmap_service.dashboard_nav_map(robot_id)
    data["image_url"] = (
        url_for(
            "costmaps.costmap_image", robot_id=data["source_robot"],
            layer=costmap_service.NAV_LAYER, version=data["content_hash"][:16],
        )
        if data["available"] else None
    )
    return data


@costmaps_bp.get("/nav")
@login_required
def nav_map():
    try:
        return jsonify(nav_map_state(request.args.get("robot") or None))
    except costmap_service.CostmapValidationError as exc:
        return jsonify(error="invalid_robot", message=str(exc)), 400


@costmaps_bp.get("/<robot_id>/<layer>/image")
@login_required
def costmap_image(robot_id, layer):
    try:
        source = costmap_service.validate_source(robot_id, layer)
    except costmap_service.CostmapValidationError as exc:
        return jsonify(error="costmap_not_found", message=str(exc)), 404
    row = costmap_model.latest_costmap(*source)
    if row is None:
        return jsonify(error="costmap_not_found", message="수신된 costmap이 없습니다."), 404
    directory = Path(current_app.config["COSTMAP_DIR"]).resolve()
    image_path = (directory / row["image_path"]).resolve()
    # [경로 보호] DB 값이 변조되어도 costmap 전용 폴더 밖 파일은 제공하지 않는다.
    if image_path.parent != directory or not image_path.is_file():
        return jsonify(error="costmap_image_missing", message="costmap 이미지 파일을 찾을 수 없습니다."), 404
    return send_file(image_path, mimetype="image/png", conditional=True, max_age=0)
