"""관측점 방문과 순찰 결과 보고의 SQLite 접근 코드."""

from ..database import get_db


VISIT_COMPARE_COLUMNS = (
    "visit_id", "robot_id", "patrol_id", "waypoint_id", "result",
    "reason_code", "arrived_at",
)
REPORT_COMPARE_COLUMNS = (
    "patrol_id", "report_id", "robot_id", "result", "reason_code",
    "started_at", "planned_visit_count", "completed_visit_count",
)


class PatrolConflictError(Exception):
    """같은 ID가 서로 다른 순찰 내용을 가리킬 때 사용한다."""


def store_visit(record):
    """visit_id 재전송·충돌을 판정하고 신규 방문만 저장한다."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT * FROM patrol_visits WHERE visit_id = ? OR message_id = ?",
            (record["visit_id"], record["message_id"]),
        ).fetchone()
        if existing is not None:
            # [재전송 판별] 같은 내용이면 중복으로 인정하고 다른 내용이면 폐기한다.
            if not all(existing[column] == record[column] for column in VISIT_COMPARE_COLUMNS):
                raise PatrolConflictError(
                    f'visit_id {record["visit_id"]}에 다른 방문 내용이 이미 있습니다.'
                )
            db.commit()
            return "duplicate", dict(existing)
        db.execute(
            """
            INSERT INTO patrol_visits
                (visit_id, message_id, robot_id, patrol_id, mission_id, command_id,
                 waypoint_id, x, y, frame_id, result, reason_code, reason,
                 arrived_at, completed_at, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(record[column] for column in (
                "visit_id", "message_id", "robot_id", "patrol_id", "mission_id",
                "command_id", "waypoint_id", "x", "y", "frame_id", "result",
                "reason_code", "reason", "arrived_at", "completed_at", "received_at",
            )),
        )
        db.commit()
        return "accepted", record
    except Exception:
        db.rollback()
        raise


def store_report(record):
    """순찰 한 회의 결과 보고를 patrol_id 한 행으로 저장한다."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT * FROM patrol_runs WHERE patrol_id = ? OR message_id = ?",
            (record["patrol_id"], record["message_id"]),
        ).fetchone()
        if existing is not None:
            if not all(existing[column] == record[column] for column in REPORT_COMPARE_COLUMNS):
                raise PatrolConflictError(
                    f'patrol_id {record["patrol_id"]}에 다른 순찰 결과가 이미 있습니다.'
                )
            db.commit()
            return "duplicate", dict(existing)
        db.execute(
            """
            INSERT INTO patrol_runs
                (patrol_id, report_id, message_id, robot_id, mission_id, command_id,
                 result, reason_code, reason, started_at, ended_at,
                 planned_visit_count, completed_visit_count, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(record[column] for column in (
                "patrol_id", "report_id", "message_id", "robot_id", "mission_id",
                "command_id", "result", "reason_code", "reason", "started_at",
                "ended_at", "planned_visit_count", "completed_visit_count", "received_at",
            )),
        )
        db.commit()
        return "accepted", record
    except Exception:
        db.rollback()
        raise


def recent_visits(limit=20):
    return get_db().execute(
        """
        SELECT * FROM patrol_visits
         ORDER BY arrived_at DESC, visit_id DESC
         LIMIT ?
        """,
        (limit,),
    ).fetchall()


def recent_reports(limit=10):
    return get_db().execute(
        """
        SELECT * FROM patrol_runs
         ORDER BY started_at DESC, patrol_id DESC
         LIMIT ?
        """,
        (limit,),
    ).fetchall()


def unreported_patrols(limit=10):
    """방문 기록만 있고 결과 보고가 없는 순찰을 찾는다.

    계약상 관제는 없는 결과를 대필하지 않는다. 화면에서 UNREPORTED로 구분해 표시한다.
    """
    return get_db().execute(
        """
        SELECT v.patrol_id, v.robot_id,
               COUNT(*) AS visit_count,
               MIN(v.arrived_at) AS first_arrived_at,
               MAX(v.arrived_at) AS last_arrived_at
          FROM patrol_visits AS v
         WHERE v.patrol_id <> ''
           AND NOT EXISTS (
               SELECT 1 FROM patrol_runs AS p WHERE p.patrol_id = v.patrol_id
           )
         GROUP BY v.patrol_id, v.robot_id
         ORDER BY last_arrived_at DESC
         LIMIT ?
        """,
        (limit,),
    ).fetchall()
