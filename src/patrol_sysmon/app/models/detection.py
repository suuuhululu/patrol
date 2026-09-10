"""ReportDetection 서비스로 받은 확정 사건·증거 사진의 SQLite 저장과 중복 판정."""

from ..database import get_db


class DetectionMessageConflictError(Exception):
    """같은 event_id에 서로 다른 내용이 들어온 경우."""


def find_report(event_id):
    """ReportDetection 중복 판정용으로 같은 event_id의 사건과 내용 해시를 읽는다."""
    return get_db().execute(
        "SELECT event_id, robot_id, occurred_at, x, y, content_hash FROM events WHERE event_id = ?",
        (event_id,),
    ).fetchone()


def find_recent_report(robot_id, event_type, occurred_at, window_seconds):
    """같은 로봇·같은 종류 사건이 occurred_at ± window 안에 있으면 가장 가까운 것을 돌려준다."""
    return get_db().execute(
        """
        SELECT event_id, robot_id, event_type, occurred_at, x, y, content_hash
          FROM events
         WHERE robot_id = ? AND event_type = ?
           AND occurred_at BETWEEN strftime('%Y-%m-%dT%H:%M:%fZ', ?, ?)
                            AND strftime('%Y-%m-%dT%H:%M:%fZ', ?, ?)
         ORDER BY ABS(julianday(occurred_at) - julianday(?)) LIMIT 1
        """,
        (
            robot_id, event_type,
            occurred_at, f"-{int(window_seconds)} seconds",
            occurred_at, f"+{int(window_seconds)} seconds",
            occurred_at,
        ),
    ).fetchone()


def store_report(record, image_name):
    """서비스로 받은 사건을 events 1행과 event_evidence 1행으로 한 transaction에 저장한다.

    같은 event_id 판정은 서비스 계층이 먼저 했지만 동시 호출을 대비해 transaction 안에서 한 번 더 확인한다.
    """
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT event_id, robot_id, occurred_at, x, y, content_hash FROM events WHERE event_id = ?",
            (record["event_id"],),
        ).fetchone()
        if existing is not None:
            if existing["content_hash"] != record["content_hash"]:
                raise DetectionMessageConflictError("같은 event_id에 다른 내용이 이미 저장돼 있습니다.")
            db.commit()
            return "duplicate", dict(existing)
        db.execute(
            "INSERT OR IGNORE INTO robots (robot_id, name) VALUES (?, ?)",
            (record["robot_id"], record["robot_name"]),
        )
        db.execute(
            """
            INSERT INTO events
                (event_id, robot_id, event_type, occurred_at, x, y, frame_id,
                 status, received_at, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW', ?, ?)
            """,
            (
                record["event_id"], record["robot_id"], record["event_type"],
                record["occurred_at"],
                record["x"], record["y"], record["frame_id"], record["received_at"],
                record["content_hash"],
            ),
        )
        db.execute(
            """
            INSERT INTO event_evidence (event_id, image_path, captured_at)
            VALUES (?, ?, ?)
            """,
            (record["event_id"], image_name, record["occurred_at"]),
        )
        stored = db.execute(
            "SELECT * FROM events WHERE event_id = ?", (record["event_id"],)
        ).fetchone()
        db.commit()
        return "accepted", {**dict(stored), "image_path": image_name}
    except Exception:
        db.rollback()
        raise
