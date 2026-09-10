"""이상 이벤트와 증거 이미지 경로의 SQLite 접근 코드."""

from ..database import get_db


class EventNotFoundError(Exception):
    """상태를 변경할 이벤트가 존재하지 않는 경우."""


class EventStatusTransitionError(Exception):
    """현재 처리 상태에서 요청한 다음 상태로 이동할 수 없는 경우."""


def find_event(event_id):
    return get_db().execute(
        """
        SELECT e.*, evidence.image_path, evidence.captured_at
          FROM events AS e
          LEFT JOIN event_evidence AS evidence ON evidence.event_id = e.event_id
         WHERE e.event_id = ?
        """,
        (event_id,),
    ).fetchone()


def list_recent(limit=50, after=None):
    """대시보드에 표시할 최근 이벤트와 증거 경로를 발생 시각 역순으로 읽는다."""
    return get_db().execute(
        """
        SELECT e.*, robots.name AS robot_name,
               evidence.image_path, evidence.captured_at
          FROM events AS e
          JOIN robots ON robots.robot_id = e.robot_id
          LEFT JOIN event_evidence AS evidence ON evidence.event_id = e.event_id
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
