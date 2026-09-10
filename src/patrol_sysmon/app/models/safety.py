"""E-stop 상태의 SQLite 접근 코드."""

from ..database import get_db


def store_estop(record):
    """대상(robot1·robot6·all)별 최신 E-stop을 갱신하고 상태가 바뀐 시점만 이력에 남긴다."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT active, reason, observed_at FROM estop_latest WHERE target_robot_id = ?",
            (record["target_robot_id"],),
        ).fetchone()
        if existing is not None and record["observed_at"] < existing["observed_at"]:
            db.commit()
            return "stale", record
        # [변경 판정] 같은 상태의 반복 발행은 최신 행만 갱신해 이력이 무한히 늘지 않게 한다.
        # 대표 원인이 바뀌는 것도 운영자가 봐야 할 변화라 이력에 남긴다.
        changed = (
            existing is None
            or bool(existing["active"]) != bool(record["active"])
            or existing["reason"] != record["reason"]
        )
        columns = (
            "target_robot_id", "active", "reason", "sequence", "observed_at", "received_at",
        )
        values = tuple(record[column] for column in columns)
        if changed:
            db.execute(
                """
                INSERT INTO estop_history
                    (target_robot_id, active, reason, sequence, observed_at, received_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        db.execute(
            """
            INSERT INTO estop_latest
                (target_robot_id, active, reason, sequence, observed_at, received_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(target_robot_id) DO UPDATE SET
                active = excluded.active,
                reason = excluded.reason,
                sequence = excluded.sequence,
                observed_at = excluded.observed_at,
                received_at = excluded.received_at
            """,
            values,
        )
        db.commit()
        return "changed" if changed else "refreshed", record
    except Exception:
        db.rollback()
        raise


def latest_estops():
    return get_db().execute(
        "SELECT * FROM estop_latest ORDER BY target_robot_id"
    ).fetchall()


def recent_estop_history(limit=10):
    return get_db().execute(
        "SELECT * FROM estop_history ORDER BY observed_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
