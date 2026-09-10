"""ReportDetection 서비스로 받은 확정 사건의 SQLite 저장·중복 판정.

사건 한 건은 events 한 행과 증거 사진 파일 한 장이다. 사진 경로는 events.image_path에 둔다.
"""

from ..database import get_db


class DetectionMessageConflictError(Exception):
    """같은 event_id에 다른 내용이 들어온 경우."""


REPORT_COLUMNS = (
    "event_id", "robot_id", "event_type", "occurred_at", "x", "y",
    "content_hash", "image_path", "captured_at",
)


def find_report(event_id):
    """중복 판정용으로 같은 event_id의 사건과 내용 해시를 읽는다."""
    return get_db().execute(
        f"SELECT {', '.join(REPORT_COLUMNS)} FROM events WHERE event_id = ?",
        (event_id,),
    ).fetchone()


def find_recent_report(robot_id, event_type, occurred_at, window_seconds):
    """같은 로봇·같은 종류 사건이 occurred_at ± window 안에 있으면 가장 가까운 것을 돌려준다."""
    return get_db().execute(
        f"""
        SELECT {', '.join(REPORT_COLUMNS)}
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
    """서비스로 받은 사건을 events 1행으로 저장한다. 사진 경로도 같은 행에 넣는다.

    같은 event_id 판정은 서비스 계층이 먼저 했지만 동시 호출을 대비해 transaction 안에서
    한 번 더 확인한다.
    """
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            f"SELECT {', '.join(REPORT_COLUMNS)} FROM events WHERE event_id = ?",
            (record["event_id"],),
        ).fetchone()
        if existing is not None:
            if existing["content_hash"] != record["content_hash"]:
                raise DetectionMessageConflictError("같은 event_id에 다른 내용이 이미 저장돼 있습니다.")
            db.commit()
            return "duplicate", dict(existing)
        # [로봇 참조 준비] 상태 메시지보다 사건이 먼저 도착해도 AMR 식별 관계를 보존한다.
        db.execute(
            "INSERT OR IGNORE INTO robots (robot_id, name) VALUES (?, ?)",
            (record["robot_id"], record["robot_name"]),
        )
        db.execute(
            """
            INSERT INTO events
                (event_id, robot_id, event_type, occurred_at, x, y, frame_id,
                 status, received_at, content_hash, image_path, captured_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW', ?, ?, ?, ?)
            """,
            (
                record["event_id"], record["robot_id"], record["event_type"],
                record["occurred_at"], record["x"], record["y"], record["frame_id"],
                record["received_at"], record["content_hash"], image_name,
                record["occurred_at"],
            ),
        )
        stored = db.execute(
            "SELECT * FROM events WHERE event_id = ?", (record["event_id"],)
        ).fetchone()
        db.commit()
        return "accepted", dict(stored)
    except Exception:
        db.rollback()
        raise
