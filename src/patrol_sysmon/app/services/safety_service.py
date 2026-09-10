"""EStop 계약 검증과 안전 상태 화면 표시 처리."""

from datetime import datetime, timedelta, timezone

from flask import current_app

from ..models import safety as safety_model
from ..ros.registry import ESTOP_REASONS, ESTOP_TARGETS


# [계약] interfaces.md 3.1절 EStop 대상과 대표 원인(2026-09-08). 관제가 정한 값만 표시한다.
ESTOP_TARGET_NAMES = {"robot1": "로봇 1", "robot6": "로봇 2", "all": "전체"}
ESTOP_REASON_LABELS = {
    "UNKNOWN": "원인 미분류", "OPERATOR": "운영자 정지 요청",
    "COMMUNICATION": "안전 통신 상실", "TOKEN": "주행 권한 없음",
    "OBSTACLE": "장애물 안전 차단", "KEEPOUT_FAILURE": "Keepout 적용 실패",
    "SYSTEM_FAULT": "시스템 고장",
}


class SafetyValidationError(ValueError):
    """E-stop 계약 필드가 확정 형식과 다를 때 사용한다."""


def _timestamp(value, now, field):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise SafetyValidationError(f"{field}는 시간대가 포함된 ISO 8601 시각이어야 합니다.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SafetyValidationError(f"{field}에 시간대가 필요합니다.")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > now + timedelta(minutes=5):
        raise SafetyValidationError(f"{field}가 서버 시각보다 5분 이상 미래입니다.")
    return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _flag(payload, field):
    value = payload.get(field)
    if not isinstance(value, bool):
        raise SafetyValidationError(f"{field}는 Bool이어야 합니다.")
    return int(value)


def validate_estop(payload, now=None):
    """계약 EStop 값을 저장 가능한 형식으로 정규화한다."""
    if not isinstance(payload, dict):
        raise SafetyValidationError("EStop 객체가 필요합니다.")
    current = now or datetime.now(timezone.utc)
    target = payload.get("target_robot_id")
    if target not in ESTOP_TARGETS:
        raise SafetyValidationError("target_robot_id는 robot1, robot6, all 중 하나여야 합니다.")
    reason = payload.get("reason", 0)
    if isinstance(reason, bool) or reason not in ESTOP_REASONS:
        raise SafetyValidationError("reason은 계약 E-stop 원인 enum(0~6) 중 하나여야 합니다.")
    sequence = payload.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise SafetyValidationError("sequence는 0 이상의 정수여야 합니다.")
    return {
        "target_robot_id": target,
        "active": _flag(payload, "active"),
        "reason": reason,
        "sequence": sequence,
        "observed_at": _timestamp(payload.get("observed_at"), current, "observed_at"),
        "received_at": current.astimezone(timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z"),
    }


def receive_estop(payload, now=None):
    return safety_model.store_estop(validate_estop(payload, now))


def _display_time(value):
    if not value:
        return "—"
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone(timedelta(hours=9))).strftime("%m-%d %H:%M:%S")


def _seconds_since(value, now):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (now - parsed).total_seconds()


def dashboard_safety(now=None):
    """E-stop 최신 상태와 최근 변경 이력을 화면용 JSON으로 만든다."""
    current = now or datetime.now(timezone.utc)
    timeout = current_app.config["ESTOP_STALE_AFTER_SECONDS"]
    estop = _estop_view(safety_model.latest_estops(), current, timeout)
    history = [{
        "target_robot_id": row["target_robot_id"],
        "target_name": ESTOP_TARGET_NAMES[row["target_robot_id"]],
        "active": bool(row["active"]),
        "state_label": "활성" if row["active"] else "해제",
        "reason_code": row["reason"], "reason": _reason_label(row["reason"]),
        "observed_label": _display_time(row["observed_at"]),
    } for row in safety_model.recent_estop_history()]
    return {"estop": estop, "estop_history": history}


def _reason_label(value):
    name = ESTOP_REASONS.get(value, "UNKNOWN")
    return ESTOP_REASON_LABELS[name]


def _estop_view(rows, current, timeout):
    """대상별 마지막 EStop을 화면 요약으로 만든다.

    `all` 대상이 활성이면 두 로봇 모두 정지 대상이다. 정지 명령이 있었다는 사실만 보여 주고,
    실제 정지 여부는 로봇 쪽 상태로 따로 확인해야 한다(v2에는 안전 상태 토픽이 없다).
    """
    by_target = {row["target_robot_id"]: row for row in rows}
    if not by_target:
        # [미수신 구분] E-stop을 받은 적이 없는 상태와 해제 상태를 같은 값으로 표시하지 않는다.
        return {
            "available": False, "active": None, "state_label": "E-stop 수신 대기",
            "stale": False, "reason_code": None, "reason": "", "received_label": "—",
            "targets": [],
        }
    targets = []
    for target in ESTOP_TARGETS:
        row = by_target.get(target)
        if row is None:
            targets.append({
                "target_robot_id": target, "target_name": ESTOP_TARGET_NAMES[target],
                "available": False, "active": False, "stale": False,
                "reason_code": None, "reason": "", "sequence": None,
                "observed_label": "—", "received_label": "—",
            })
            continue
        targets.append({
            "target_robot_id": target, "target_name": ESTOP_TARGET_NAMES[target],
            "available": True, "active": bool(row["active"]),
            # [단절 표시] 마지막 값을 유지하고 오래된 수신임을 따로 알린다.
            "stale": _seconds_since(row["received_at"], current) > timeout,
            "reason_code": row["reason"], "reason": _reason_label(row["reason"]),
            "sequence": row["sequence"],
            "observed_label": _display_time(row["observed_at"]),
            "received_label": _display_time(row["received_at"]),
        })
    active_targets = [item for item in targets if item["active"]]
    latest = max(by_target.values(), key=lambda row: row["received_at"])
    if active_targets:
        names = ", ".join(item["target_name"] for item in active_targets)
        # 대표 원인은 가장 최근에 받은 활성 대상의 값을 보여 준다.
        primary = max(
            (by_target[item["target_robot_id"]] for item in active_targets),
            key=lambda row: row["received_at"],
        )
        state_label = f"비상정지 활성 ({names})"
        reason_code, reason = primary["reason"], _reason_label(primary["reason"])
    else:
        state_label = "정상"
        reason_code, reason = latest["reason"], ""
    return {
        "available": True, "active": bool(active_targets), "state_label": state_label,
        "stale": any(item["stale"] for item in targets if item["available"]),
        "reason_code": reason_code, "reason": reason,
        "received_label": _display_time(latest["received_at"]),
        "targets": targets,
    }
