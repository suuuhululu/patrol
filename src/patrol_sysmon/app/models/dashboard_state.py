"""사용자별 대시보드 최근 목록 표시 기준의 SQLite 접근 코드."""

from ..database import get_db


COLUMNS = {
    "events": "event_cleared_at",
    "vehicle-access": "vehicle_access_cleared_at",
}


def get_clear_state(user_id):
    row = get_db().execute(
        "SELECT event_cleared_at, vehicle_access_cleared_at FROM dashboard_clear_state WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return {"events": None, "vehicle-access": None}
    return {"events": row["event_cleared_at"], "vehicle-access": row["vehicle_access_cleared_at"]}


def set_cleared_at(user_id, log_name, cleared_at):
    """허용된 열만 갱신하며 다른 로그의 표시 기준은 유지한다."""
    column = COLUMNS[log_name]
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT OR IGNORE INTO dashboard_clear_state(user_id) VALUES (?)", (user_id,)
        )
        db.execute(
            f"UPDATE dashboard_clear_state SET {column} = ?, updated_at = ? WHERE user_id = ?",
            (cleared_at, cleared_at, user_id),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
