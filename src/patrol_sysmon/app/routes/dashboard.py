from datetime import datetime, timezone
import sqlite3

from flask import Blueprint, current_app, g, jsonify, render_template

from ..models import dashboard_state as dashboard_state_model
from ..security import login_required
from ..services import (
    camera_service, cctv_service, event_service,
    patrol_service, robot_service, safety_service, vehicle_access_service,
)
from .costmaps import nav_map_state

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/")
@login_required
def index():
    clear_state = dashboard_state_model.get_clear_state(g.user["id"])
    # [5단계: 초기 상태] 첫 화면부터 DB 최신 값을 표시하고 이후에는 브라우저가 API로 갱신한다.
    robots = robot_service.dashboard_robots()
    fleet_status = robot_service.fleet_summary(robots)
    # [NAV 지도 초기 상태] 최근 받은 로봇의 global costmap을 바탕으로 로봇 좌표를 첫 화면에 함께 전달한다.
    map_state = nav_map_state()
    # [8단계: 이벤트 초기 목록] JavaScript 갱신 전에도 최근 이벤트를 표에 표시한다.
    events = event_service.recent_events(50, clear_state["events"])
    # [9단계: 영상 초기 상태] 저장된 최신 프레임의 유무와 최근 수신 여부를 첫 화면에 표시한다.
    cameras = camera_service.dashboard_cameras()
    # [19단계: CCTV 판단 상태] permit 미수신·정상·단절 상태를 첫 화면부터 구분한다.
    cctv_state = cctv_service.dashboard_cctv()
    # [20단계: 순찰·안전 초기 상태] 방문·보고와 E-stop을 첫 화면부터 표시한다.
    patrol_state = patrol_service.dashboard_patrol()
    safety_state = safety_service.dashboard_safety()
    # [11단계: 입출차 초기 목록] 새로고침 직후에도 최근 차량 통과 기록을 바로 표시한다.
    vehicle_accesses = vehicle_access_service.recent_accesses(
        50, clear_state["vehicle-access"]
    )
    return render_template("index.html", patrol_state=patrol_state, safety_state=safety_state,
                           robots=robots, cameras=cameras, events=events,
                           vehicle_accesses=vehicle_accesses,
                           fleet_status=fleet_status, map_state=map_state,
                           cctv_state=cctv_state)


@dashboard_bp.post("/api/dashboard/clear/<log_name>")
@login_required
def clear_recent_log(log_name):
    """DB 행은 유지하고 현재 사용자의 최근 목록 표시 기준만 현재 시각으로 옮긴다."""
    if log_name not in dashboard_state_model.COLUMNS:
        return jsonify(error="invalid_log", message="초기화할 로그 종류가 올바르지 않습니다."), 404
    cleared_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
    try:
        dashboard_state_model.set_cleared_at(g.user["id"], log_name, cleared_at)
    except sqlite3.Error:
        current_app.logger.exception("대시보드 표시 초기화 저장 실패")
        return jsonify(error="storage_error", message="표시 초기화 기준을 저장하지 못했습니다."), 500
    return jsonify(result="cleared", log=log_name, cleared_at=cleared_at)
