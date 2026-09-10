"""임시 HTTP 로봇 상태를 내부 형식으로 검증하고 화면 표시값을 만든다."""

from datetime import datetime, timedelta, timezone
import math
import re

from flask import current_app

from ..models import robot as robot_model


ROBOT_NAMES = {"AMR1": "로봇 1", "AMR2": "로봇 2"}
MISSION_LABELS = {
    "IDLE": "대기", "PATROLLING": "순찰 중", "PAUSED": "일시정지",
    "RETURNING": "복귀 중", "DOCKING": "도킹 중", "CHARGING": "충전 중",
    "EVACUATING": "대피 중", "ERROR": "오류",
    # [12단계: 계약 매핑] v1 RobotStatus mission_state 이름. v1 이력 표시에 쓴다.
    "UNDOCKING": "도크 이탈 중",
    "MOVING_TO_SAFE_ZONE": "안전구역 이동 중",
    "WAITING_SAFE_ZONE": "안전구역 대기",
    "RETURNING_TO_DOCK": "도크 복귀 중",
    "COMPLETED": "완료",
    "FAILED": "실패",
    "CANCELED": "취소",
    # [v2 Patrol Feedback] task_state를 그대로 임무 상태로 쓴다.
    "WAITING_FOR_TOKEN": "주행 권한 대기",
    "INITIAL_POSE_READY": "초기 위치 확인",
    "DETECTION_PROCESSING": "감지 확인 중",
    "DETECTION_CONFIRMED": "감지 확정",
    "RESUMING": "순찰 재개 중",
    "BLOCKED": "주행 막힘",
    "WAYPOINT_REACHED": "관측점 도착",
}
CONNECTION_LABELS = {"ONLINE": "온라인", "OFFLINE": "오프라인", "UNKNOWN": "확인 불가"}
# [계약 매핑] v1 RobotStatus.safety_state. v2에는 안전 상태 토픽이 없어 새 행은 UNKNOWN이다. NORMAL은 이동 권한이 아니고
# ESTOPPED는 속도 0을 보장하지 않으므로 실제 정지 여부는 motion_stopped로 따로 붙인다.
SAFETY_LABELS = {
    "UNKNOWN": "확인 안 됨", "NORMAL": "정상", "STOPPING": "정지 중",
    "STOPPED": "정지 확인", "ESTOPPED": "E-stop 활성", "ERROR": "안전 계층 오류",
}
SAFETY_WARNING_STATES = {"ESTOPPED", "ERROR"}
MESSAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
FRAME_ID_PATTERN = re.compile(r"^[A-Za-z0-9_./-]{1,64}$")


class StatusValidationError(ValueError):
    """로봇 상태 입력 형식이 내부 규약과 다를 때 사용한다."""


def _required_text(payload, field):
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise StatusValidationError(f"{field} 값이 필요합니다.")
    return value.strip()


def _finite_number(payload, field):
    value = payload.get(field)
    # [숫자 검사] bool은 Python에서 int의 하위 형식이므로 좌표·배터리로 받지 않는다.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise StatusValidationError(f"{field} 값은 유한한 숫자여야 합니다.")
    return float(value)


def _utc_timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise StatusValidationError("observed_at은 시간대가 포함된 ISO 8601 시각이어야 합니다.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StatusValidationError("observed_at에 시간대가 필요합니다.")
    return parsed.astimezone(timezone.utc)


def validate_status(payload, now=None):
    """외부 메시지를 DB와 대시보드가 공통으로 쓰는 값으로 정규화한다."""
    if not isinstance(payload, dict):
        raise StatusValidationError("JSON 객체 형식의 상태가 필요합니다.")
    message_id = _required_text(payload, "message_id")
    if not MESSAGE_ID_PATTERN.fullmatch(message_id):
        raise StatusValidationError("message_id 형식이 올바르지 않습니다.")
    robot_id = _required_text(payload, "robot_id").upper()
    if robot_id not in ROBOT_NAMES:
        raise StatusValidationError("robot_id는 AMR1 또는 AMR2여야 합니다.")
    # [배터리 선택] v2에서는 배터리가 battery_state로 따로 온다. 아직 못 받았으면 비워 둔다.
    battery = None
    if payload.get("battery") is not None:
        battery = _finite_number(payload, "battery")
        if not 0 <= battery <= 100:
            raise StatusValidationError("battery는 0에서 100 사이여야 합니다.")
    # [위치 유효성] pose_valid를 그대로 받는다(v2는 Patrol 피드백 위치가 map 좌표계일 때만 유효).
    # 무효면 좌표를 저장하지 않고 배터리·임무·연결 상태만 남긴다.
    pose_valid = payload.get("pose_valid", True)
    if not isinstance(pose_valid, bool):
        raise StatusValidationError("pose_valid는 Bool이어야 합니다.")
    if pose_valid:
        x = _finite_number(payload, "x")
        y = _finite_number(payload, "y")
    else:
        x = None
        y = None
    last_valid_pose_at = payload.get("last_valid_pose_at")
    if last_valid_pose_at is not None:
        last_valid_pose_at = _utc_timestamp(last_valid_pose_at).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
    frame_id = _required_text(payload, "frame_id")
    if not FRAME_ID_PATTERN.fullmatch(frame_id):
        raise StatusValidationError("frame_id 형식이 올바르지 않습니다.")
    mission_status = _required_text(payload, "mission_status").upper()
    if mission_status not in MISSION_LABELS:
        raise StatusValidationError("지원하지 않는 mission_status입니다.")
    connection_status = _required_text(payload, "connection_status").upper()
    if connection_status not in CONNECTION_LABELS:
        raise StatusValidationError("connection_status는 ONLINE, OFFLINE, UNKNOWN 중 하나여야 합니다.")
    # [안전 상태] 임시 HTTP 경로는 값을 안 보낼 수 있으므로 UNKNOWN을 기본으로 둔다.
    safety_state = str(payload.get("safety_state") or "UNKNOWN").upper()
    if safety_state not in SAFETY_LABELS:
        raise StatusValidationError("지원하지 않는 safety_state입니다.")
    motion_stopped = payload.get("motion_stopped", False)
    if not isinstance(motion_stopped, bool):
        raise StatusValidationError("motion_stopped는 Bool이어야 합니다.")
    safety_reason_code = payload.get("safety_reason_code", 0)
    if isinstance(safety_reason_code, bool) or not isinstance(safety_reason_code, int) or safety_reason_code < 0:
        raise StatusValidationError("safety_reason_code는 0 이상의 정수여야 합니다.")
    safety_reason = payload.get("safety_reason", "")
    if not isinstance(safety_reason, str):
        raise StatusValidationError("safety_reason은 문자열이어야 합니다.")
    observed = _utc_timestamp(payload.get("observed_at"))
    current = now or datetime.now(timezone.utc)
    if observed > current + timedelta(minutes=5):
        raise StatusValidationError("observed_at이 서버 시각보다 5분 이상 미래입니다.")
    return {
        "robot_id": robot_id,
        "message_id": message_id,
        "battery": battery,
        "x": x,
        "y": y,
        "frame_id": frame_id,
        "pose_valid": int(pose_valid),
        "last_valid_pose_at": last_valid_pose_at,
        "mission_status": mission_status,
        "safety_state": safety_state,
        "motion_stopped": int(motion_stopped),
        "safety_reason_code": safety_reason_code,
        "safety_reason": safety_reason.strip(),
        "connection_status": connection_status,
        "observed_at": observed.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }


def receive_status(payload, now=None):
    # [수신 처리] 유효성 검사 뒤 모델 한 곳에서 중복·순서 검사와 두 테이블 저장을 수행한다.
    current = now or datetime.now(timezone.utc)
    status = validate_status(payload, current)
    received_at = current.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    min_interval = current_app.config.get("ROBOT_STATUS_HISTORY_MIN_INTERVAL_SECONDS") or 0.0
    return robot_model.store_status(
        status, received_at, float(min_interval), _history_cutoff(current)
    )


PRUNE_INTERVAL_SECONDS = 60


def _history_cutoff(current):
    """보존 기간이 켜져 있고 마지막 정리 뒤 1분이 지났으면 삭제 기준 시각을 돌려준다.

    2 Hz × 2대 수신마다 DELETE를 돌리지 않도록 앱 객체에 마지막 정리 시각을 기억한다.
    """
    retention_days = current_app.config.get("ROBOT_STATUS_HISTORY_RETENTION_DAYS")
    if not retention_days or retention_days <= 0:
        return None
    state = current_app.extensions.setdefault("sysmon_status_history_prune", {})
    last = state.get("last_pruned_at")
    if last is not None and (current - last).total_seconds() < PRUNE_INTERVAL_SECONDS:
        return None
    state["last_pruned_at"] = current
    cutoff = current.astimezone(timezone.utc) - timedelta(days=retention_days)
    return cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_stored_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _display_time(value):
    # [화면 시각] DB는 UTC로 보존하고 사용자 화면에는 한국 시각을 함께 표시한다.
    korea = timezone(timedelta(hours=9))
    return _parse_stored_time(value).astimezone(korea).strftime("%m-%d %H:%M:%S")


def dashboard_robots(now=None):
    """DB 최신 행을 AMR1·AMR2 카드와 JSON 응답에 맞는 형식으로 변환한다."""
    current = now or datetime.now(timezone.utc)
    rows = {row["robot_id"]: row for row in robot_model.list_latest()}
    stale_after = timedelta(seconds=current_app.config["ROBOT_OFFLINE_AFTER_SECONDS"])
    result = []
    for robot_id, name in ROBOT_NAMES.items():
        row = rows.get(robot_id)
        if row is None or row["message_id"] is None:
            result.append({
                "id": robot_id, "name": name, "has_status": False,
                "connection_status": "UNKNOWN", "connection_label": "수신 대기",
                "battery": None, "mission_status": None, "mission_label": "—",
                "x": None, "y": None, "frame_id": None, "location_label": "—",
                "pose_valid": False, "last_valid_x": None, "last_valid_y": None,
                "last_valid_label": "—",
                "safety_state": None, "safety_label": "—", "safety_warning": False,
                "motion_stopped": None, "safety_reason_code": None, "safety_reason": "",
                "observed_at": None, "received_at": None, "received_label": "—",
            })
            continue
        received = _parse_stored_time(row["received_at"])
        stale = current - received > stale_after
        effective = "OFFLINE" if stale else row["connection_status"]
        pose_valid = bool(row["pose_valid"])
        # [위치 표시] 현재 위치가 무효면 마지막으로 유효했던 위치를 따로 찾아 구분해 보여준다.
        last_valid = None if pose_valid else robot_model.last_valid_pose(robot_id)
        if pose_valid:
            location_label = f'{row["frame_id"]} ({row["x"]:.2f}, {row["y"]:.2f})'
        elif last_valid is not None:
            location_label = (
                f'마지막 유효 {last_valid["frame_id"]} '
                f'({last_valid["x"]:.2f}, {last_valid["y"]:.2f})'
            )
        else:
            location_label = "위치 확인 안 됨"
        result.append({
            "id": robot_id, "name": name, "has_status": True,
            "connection_status": effective, "connection_label": CONNECTION_LABELS[effective],
            "battery": row["battery"], "mission_status": row["mission_status"],
            "mission_label": MISSION_LABELS.get(row["mission_status"], row["mission_status"]),
            "x": row["x"], "y": row["y"], "frame_id": row["frame_id"],
            "location_label": location_label,
            "pose_valid": pose_valid,
            "last_valid_x": last_valid["x"] if last_valid else None,
            "last_valid_y": last_valid["y"] if last_valid else None,
            "last_valid_label": (
                _display_time(row["last_valid_pose_at"])
                if row["last_valid_pose_at"] else
                (_display_time(last_valid["observed_at"]) if last_valid else "—")
            ),
            "safety_state": row["safety_state"],
            "safety_label": _safety_label(row),
            "safety_warning": row["safety_state"] in SAFETY_WARNING_STATES,
            "motion_stopped": bool(row["motion_stopped"]),
            "safety_reason_code": row["safety_reason_code"],
            "safety_reason": row["safety_reason"],
            "observed_at": row["observed_at"], "received_at": row["received_at"],
            "received_label": _display_time(row["received_at"]),
        })
    return result


def _safety_label(row):
    """safety_state와 실제 정지 확인을 한 문구로 합친다. 서로 대체 관계가 아니라 둘 다 적는다."""
    label = SAFETY_LABELS.get(row["safety_state"], row["safety_state"])
    if row["safety_state"] == "UNKNOWN":
        return label
    motion = "정지 확인됨" if row["motion_stopped"] else "이동 가능 상태"
    if row["safety_reason_code"]:
        return f"{label} · {motion} · 원인 {row['safety_reason_code']}"
    return f"{label} · {motion}"


def fleet_summary(robots):
    online_count = sum(robot["connection_status"] == "ONLINE" for robot in robots)
    if online_count == len(robots):
        return "모든 로봇 온라인"
    if online_count:
        return f"로봇 {online_count}/{len(robots)} 온라인"
    if any(robot["has_status"] for robot in robots):
        return "연결된 로봇 없음"
    return "장비 연결 대기"
