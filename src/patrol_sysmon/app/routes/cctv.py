"""로그인 사용자의 CCTV 상태·순찰 허용 모니터링 API."""

from flask import Blueprint, jsonify

from ..security import login_required
from ..services import cctv_service


cctv_bp = Blueprint("cctv", __name__, url_prefix="/api/cctv")


@cctv_bp.get("/status")
@login_required
def status():
    return jsonify(cctv_service.dashboard_cctv())
