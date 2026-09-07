"""CCTV 차량 상태와 순찰 허용 조건의 SQLite 저장 코드."""

from ..database import get_db


EVENT_COMPARE_COLUMNS = (
    "event_id", "camera_id", "state", "confidence", "observed_at",
)


class CctvEventConflictError(Exception):
    """같은 event_id가 서로 다른 CameraState 내용을 가리킬 때 사용한다."""


def store_event(record):
    """CameraState 중복·충돌 판정과 신규 저장을 한 트랜잭션에서 수행한다."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT * FROM cctv_state_events WHERE event_id = ?",
            (record["event_id"],),
        ).fetchone()
        if existing is not None:
            if not all(existing[column] == record[column] for column in EVENT_COMPARE_COLUMNS):
                raise CctvEventConflictError
            db.commit()
            return "duplicate", dict(existing)
        db.execute(
            """
            INSERT INTO cctv_state_events
                (event_id, camera_id, state, confidence, observed_at, received_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            tuple(record[column] for column in (
                "event_id", "camera_id", "state", "confidence",
                "observed_at", "received_at",
            )),
        )
        db.commit()
        return "accepted", record
    except Exception:
        db.rollback()
        raise


def store_permit(allowed, received_at):
    """최신 heartbeat는 갱신하고 실제 Bool 변경만 이력에 추가한다."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT allowed FROM patrol_permit_latest WHERE singleton = 1"
        ).fetchone()
        changed = existing is None or bool(existing["allowed"]) != allowed
        if changed:
            db.execute(
                "INSERT INTO patrol_permit_history (allowed, received_at) VALUES (?, ?)",
                (int(allowed), received_at),
            )
        db.execute(
            """
            INSERT INTO patrol_permit_latest (singleton, allowed, received_at)
            VALUES (1, ?, ?)
            ON CONFLICT(singleton) DO UPDATE SET
                allowed = excluded.allowed,
                received_at = excluded.received_at
            """,
            (int(allowed), received_at),
        )
        db.commit()
        return "changed" if changed else "refreshed"
    except Exception:
        db.rollback()
        raise


def latest_permit():
    return get_db().execute(
        "SELECT allowed, received_at FROM patrol_permit_latest WHERE singleton = 1"
    ).fetchone()


def list_recent_events(limit=20):
    return get_db().execute(
        """
        SELECT * FROM cctv_state_events
         ORDER BY observed_at DESC, event_id DESC
         LIMIT ?
        """,
        (limit,),
    ).fetchall()


def list_center_states(limit=50, after=None):
    """센터 CCTV의 확정 상태를 최근 순으로 읽는다.

    사용자별 표시 초기화 기준(after)은 입출차 목록과 같게 수신 시각으로 비교한다.
    """
    return get_db().execute(
        """
        SELECT * FROM cctv_state_events
         WHERE camera_id = 'center_cam'
           AND (? IS NULL OR received_at > ?)
         ORDER BY observed_at DESC, event_id DESC
         LIMIT ?
        """,
        (after, after, limit),
    ).fetchall()
