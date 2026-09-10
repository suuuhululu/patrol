"""로그인 사용자의 순찰·안전 상태 모니터링 API."""

from flask import Blueprint, jsonify

from ..security import login_required
from ..services import patrol_service, safety_service


patrol_bp = Blueprint("patrol", __name__, url_prefix="/api")


@patrol_bp.get("/patrol/status")
@login_required
def patrol_status():
    # [20단계: 순찰 관측] 방문·보고는 ROS 토픽으로만 들어오므로 조회 경로만 연다.
    return jsonify(patrol_service.dashboard_patrol())


@patrol_bp.get("/safety/status")
@login_required
def safety_status():
    # [20단계: 안전 관측] E-stop도 표시 전용이며 관제는 명령을 만들지 않는다.
    return jsonify(safety_service.dashboard_safety())
