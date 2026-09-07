"""고정 웹캠 차량 입출차 기록의 SQLite 접근 코드."""

from ..database import get_db


COMPARE_COLUMNS = (
    "access_id", "message_id", "camera_id", "direction", "detected_at",
)


class VehicleAccessConflictError(Exception):
    """같은 ID가 서로 다른 입출차 내용을 가리키는 경우."""


def _same(existing, record):
    return all(existing[column] == record[column] for column in COMPARE_COLUMNS)


def find(access_id):
    return get_db().execute(
        "SELECT * FROM vehicle_access_logs WHERE access_id = ?", (access_id,)
    ).fetchone()


def list_recent(limit=50, after=None):
    return get_db().execute(
        """
        SELECT * FROM vehicle_access_logs
         WHERE (? IS NULL OR received_at > ?)
         ORDER BY detected_at DESC, access_id DESC
         LIMIT ?
        """,
        (after, after, limit),
    ).fetchall()


def store(record):
    """중복 확인과 신규 기록 INSERT를 한 트랜잭션으로 처리한다."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT * FROM vehicle_access_logs WHERE access_id = ? OR message_id = ?",
            (record["access_id"], record["message_id"]),
        ).fetchone()
        if existing is not None:
            if not _same(existing, record):
                raise VehicleAccessConflictError
            db.commit()
            return "duplicate", dict(existing)
        db.execute(
            """
            INSERT INTO vehicle_access_logs
                (access_id, message_id, camera_id, direction, detected_at, received_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            tuple(record[column] for column in (
                "access_id", "message_id", "camera_id", "direction", "detected_at", "received_at",
            )),
        )
        db.commit()
        return "accepted", record
    except Exception:
        db.rollback()
        raise
