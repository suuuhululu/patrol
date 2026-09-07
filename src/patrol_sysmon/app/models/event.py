"""이상 이벤트와 증거 이미지 경로의 SQLite 접근 코드."""

from ..database import get_db


EVENT_COMPARE_COLUMNS = (
    "event_id", "message_id", "robot_id", "event_type", "occurred_at",
    "x", "y", "frame_id", "risk_level",
)


class EventMessageConflictError(Exception):
    """event_id 또는 message_id가 기존 이벤트와 다른 내용을 가리키는 경우."""


class EventNotFoundError(Exception):
    """상태를 변경할 이벤트가 존재하지 않는 경우."""


class EventStatusTransitionError(Exception):
    """현재 처리 상태에서 요청한 다음 상태로 이동할 수 없는 경우."""


def _same_event(existing, event_record):
    # [재전송 판별] 이벤트 메타데이터와 증거 이미지 경로가 모두 같아야 같은 요청이다.
    metadata_matches = all(
        existing[column] == event_record[column] for column in EVENT_COMPARE_COLUMNS
    )
    return (
        metadata_matches
        and existing["image_path"] == event_record["image_path"]
        and existing["captured_at"] == event_record["captured_at"]
    )


def find_event(event_id):
    return get_db().execute(
        """
        SELECT e.*, evidence.image_path, evidence.captured_at,
               ingestion.status AS evidence_status,
               ingestion.updated_at AS evidence_updated_at
          FROM events AS e
          LEFT JOIN event_evidence AS evidence ON evidence.event_id = e.event_id
          LEFT JOIN evidence_ingestions AS ingestion ON ingestion.event_id = e.event_id
         WHERE e.event_id = ?
        """,
        (event_id,),
    ).fetchone()


def list_recent(limit=50, after=None):
    """대시보드에 표시할 최근 이벤트와 증거 경로를 발생 시각 역순으로 읽는다."""
    return get_db().execute(
        """
        SELECT e.*, robots.name AS robot_name,
               evidence.image_path, evidence.captured_at,
               ingestion.status AS evidence_status,
               ingestion.updated_at AS evidence_updated_at
          FROM events AS e
          JOIN robots ON robots.robot_id = e.robot_id
          LEFT JOIN event_evidence AS evidence ON evidence.event_id = e.event_id
          LEFT JOIN evidence_ingestions AS ingestion ON ingestion.event_id = e.event_id
         WHERE (? IS NULL OR e.received_at > ?)
         ORDER BY e.occurred_at DESC, e.event_id DESC
         LIMIT ?
        """,
        (after, after, limit),
    ).fetchall()


def list_changes(event_id):
    """누가 이벤트 처리 상태와 메모를 변경했는지 시간 순서로 읽는다."""
    return get_db().execute(
        """
        SELECT changes.previous_status, changes.new_status, changes.memo,
               changes.changed_at, users.username
          FROM event_changes AS changes
          JOIN users ON users.id = changes.user_id
         WHERE changes.event_id = ?
         ORDER BY changes.changed_at ASC, changes.id ASC
        """,
        (event_id,),
    ).fetchall()


def change_status(event_id, user_id, new_status, memo, allowed_transition):
    """현재 상태 확인·갱신·변경 이력 INSERT를 한 트랜잭션으로 처리한다."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        event = db.execute(
            "SELECT status FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if event is None:
            raise EventNotFoundError
        previous_status = event["status"]
        if allowed_transition.get(previous_status) != new_status:
            raise EventStatusTransitionError(previous_status)
        db.execute(
            "UPDATE events SET status = ? WHERE event_id = ? AND status = ?",
            (new_status, event_id, previous_status),
        )
        db.execute(
            """
            INSERT INTO event_changes
                (event_id, user_id, previous_status, new_status, memo)
            VALUES (?, ?, ?, ?, ?)
            """,
            (event_id, user_id, previous_status, new_status, memo),
        )
        db.commit()
        return previous_status, new_status
    except Exception:
        # [상태 변경 원자성] 현재 상태와 감사 이력이 서로 다르게 남지 않게 되돌린다.
        db.rollback()
        raise


def store_event(event_record):
    """이벤트와 증거 이미지 경로를 한 트랜잭션에서 저장한다."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            """
            SELECT e.*, evidence.image_path, evidence.captured_at
              FROM events AS e
              LEFT JOIN event_evidence AS evidence ON evidence.event_id = e.event_id
             WHERE e.event_id = ? OR e.message_id = ?
            """,
            (event_record["event_id"], event_record["message_id"]),
        ).fetchone()
        if existing is not None:
            if not _same_event(existing, event_record):
                raise EventMessageConflictError
            db.commit()
            return "duplicate", dict(existing)

        # [로봇 참조 준비] 상태 메시지보다 이벤트가 먼저 도착해도 AMR 식별 관계를 보존한다.
        db.execute(
            "INSERT OR IGNORE INTO robots (robot_id, name) VALUES (?, ?)",
            (event_record["robot_id"], event_record["robot_name"]),
        )
        db.execute(
            """
            INSERT INTO events
                (event_id, message_id, robot_id, event_type, occurred_at,
                 x, y, frame_id, risk_level, status, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'NEW', ?)
            """,
            tuple(event_record[column] for column in (
                "event_id", "message_id", "robot_id", "event_type", "occurred_at",
                "x", "y", "frame_id", "risk_level", "received_at",
            )),
        )
        db.execute(
            """
            INSERT INTO event_evidence (event_id, image_path, captured_at)
            VALUES (?, ?, ?)
            """,
            (event_record["event_id"], event_record["image_path"], event_record["captured_at"]),
        )
        db.commit()
        return "accepted", event_record
    except Exception:
        # [원자적 저장] 이벤트와 증거 경로 중 하나만 남지 않도록 전체 작업을 되돌린다.
        db.rollback()
        raise
