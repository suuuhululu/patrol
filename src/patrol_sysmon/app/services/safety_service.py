"""KeepoutStatus·EStopState 계약 검증과 안전 상태 화면 표시 처리."""

from datetime import datetime, timedelta, timezone
import re
import uuid

from flask import current_app

from ..models import safety as safety_model


UUID_V4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
ROBOT_NAMES = {"AMR1": "로봇 1", "AMR2": "로봇 2"}
KEEPOUT_STATES = {
    "UNKNOWN": "확인 안 됨", "DISABLED": "해제", "APPLIED": "적용",
    "ROLLED_BACK": "되돌림", "ROLLBACK_FAILED": "되돌리기 실패",
}
# 되돌리기 실패는 로봇이 금지 구역 설정을 원래대로 되돌리지 못한 상태다. 화면에서 경고로 구분한다.
KEEPOUT_WARNING_STATES = {"ROLLBACK_FAILED"}


class SafetyValidationError(ValueError):
    """Keepout·E-stop 계약 필드가 확정 형식과 다를 때 사용한다."""


def _uuid_v4(value, field):
    if not isinstance(value, str) or not UUID_V4_PATTERN.fullmatch(value):
        raise SafetyValidationError(f"{field}는 소문자 UUID v4여야 합니다.")
    if str(uuid.UUID(value, version=4)) != value:
        raise SafetyValidationError(f"{field}는 소문자 UUID v4여야 합니다.")
    return value


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


def _reason_code(payload):
    value = payload.get("reason_code", 0)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 65535:
        raise SafetyValidationError("reason_code는 0에서 65535 사이의 정수여야 합니다.")
    return value


def validate_keepout(payload, now=None):
    """KeepoutStatus를 저장 가능한 계약 값으로 정규화한다."""
    if not isinstance(payload, dict):
        raise SafetyValidationError("KeepoutStatus 객체가 필요합니다.")
    current = now or datetime.now(timezone.utc)
    robot_id = payload.get("robot_id")
    if robot_id not in ROBOT_NAMES:
        raise SafetyValidationError("robot_id는 AMR1 또는 AMR2여야 합니다.")
    state = payload.get("state")
    if state not in KEEPOUT_STATES:
        raise SafetyValidationError("state는 Keepout 계약 enum 중 하나여야 합니다.")
    transaction_id = payload.get("transaction_id", "")
    if not isinstance(transaction_id, str):
        raise SafetyValidationError("transaction_id는 문자열이어야 합니다.")
    return {
        "robot_id": robot_id,
        "message_id": _uuid_v4(payload.get("message_id"), "message_id"),
        "transaction_id": transaction_id.strip(),
        "state": state,
        "global_enabled": _flag(payload, "global_enabled"),
        "local_enabled": _flag(payload, "local_enabled"),
        "reason_code": _reason_code(payload),
        "detail": str(payload.get("detail", "")),
        "observed_at": _timestamp(payload.get("observed_at"), current, "observed_at"),
        "received_at": current.astimezone(timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z"),
    }


def validate_estop(payload, now=None):
    """EStopState를 저장 가능한 계약 값으로 정규화한다."""
    if not isinstance(payload, dict):
        raise SafetyValidationError("EStopState 객체가 필요합니다.")
    current = now or datetime.now(timezone.utc)
    sequence = payload.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise SafetyValidationError("sequence는 0 이상의 정수여야 합니다.")
    source_id = payload.get("source_id", "")
    if not isinstance(source_id, str):
        raise SafetyValidationError("source_id는 문자열이어야 합니다.")
    return {
        "estop_id": _uuid_v4(payload.get("estop_id"), "estop_id"),
        "message_id": _uuid_v4(payload.get("message_id"), "message_id"),
        "active": _flag(payload, "active"),
        "reason_code": _reason_code(payload),
        "reason": str(payload.get("reason", "")),
        "manual_reset_required": _flag(payload, "manual_reset_required"),
        "source_id": source_id.strip(),
        "sequence": sequence,
        "observed_at": _timestamp(payload.get("observed_at"), current, "observed_at"),
        "received_at": current.astimezone(timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z"),
    }


def receive_keepout(payload, now=None):
    return safety_model.store_keepout(validate_keepout(payload, now))


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
    """Keepout·E-stop 최신 상태와 최근 변경 이력을 화면용 JSON으로 만든다."""
    current = now or datetime.now(timezone.utc)
    timeout = current_app.config["ESTOP_STALE_AFTER_SECONDS"]
    keepouts = []
    for row in safety_model.latest_keepouts():
        keepouts.append({
            "robot_id": row["robot_id"],
            "robot_name": ROBOT_NAMES.get(row["robot_id"], row["robot_id"]),
            "state": row["state"], "state_label": KEEPOUT_STATES[row["state"]],
            "warning": row["state"] in KEEPOUT_WARNING_STATES,
            "global_enabled": bool(row["global_enabled"]),
            "local_enabled": bool(row["local_enabled"]),
            "reason_code": row["reason_code"], "detail": row["detail"],
            "observed_label": _display_time(row["observed_at"]),
        })
    latest = safety_model.latest_estop()
    if latest is None:
        # [미수신 구분] E-stop을 받은 적이 없는 상태와 해제 상태를 같은 값으로 표시하지 않는다.
        estop = {
            "available": False, "active": None, "state_label": "E-stop 수신 대기",
            "stale": False, "reason_code": None, "reason": "",
            "manual_reset_required": False, "received_label": "—",
        }
    else:
        stale = _seconds_since(latest["received_at"], current) > timeout
        estop = {
            "available": True, "active": bool(latest["active"]),
            "state_label": "비상정지 활성" if latest["active"] else "정상",
            # [단절 표시] 마지막 값을 유지하고 오래된 수신임을 따로 알린다.
            "stale": stale,
            "estop_id": latest["estop_id"],
            "reason_code": latest["reason_code"], "reason": latest["reason"],
            "manual_reset_required": bool(latest["manual_reset_required"]),
            "source_id": latest["source_id"], "sequence": latest["sequence"],
            "observed_label": _display_time(latest["observed_at"]),
            "received_label": _display_time(latest["received_at"]),
        }
    history = [{
        "estop_id": row["estop_id"], "active": bool(row["active"]),
        "state_label": "활성" if row["active"] else "해제",
        "reason_code": row["reason_code"], "reason": row["reason"],
        "observed_label": _display_time(row["observed_at"]),
    } for row in safety_model.recent_estop_history()]
    warning_count = sum(1 for item in keepouts if item["warning"])
    return {
        "keepouts": keepouts, "estop": estop, "estop_history": history,
        "keepout_warning_count": warning_count,
        "keepout_state_label": (
            "되돌리기 실패" if warning_count
            else (keepouts[0]["state_label"] if keepouts else "Keepout 수신 대기")
        ),
    }
