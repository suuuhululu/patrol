"""로봇 최신 상태와 수신 이력의 SQLite 접근 코드."""

from datetime import datetime

from ..database import get_db


STATUS_COLUMNS = (
    "robot_id", "message_id", "battery", "x", "y", "frame_id",
    "pose_valid", "last_valid_pose_at",
    "mission_status", "safety_state", "motion_stopped",
    "safety_reason_code", "safety_reason",
    "connection_status", "observed_at",
)


class MessageIdConflictError(Exception):
    """같은 메시지 ID에 서로 다른 내용이 들어온 경우."""


class StaleStatusError(Exception):
    """현재 저장된 값보다 오래된 상태가 들어온 경우."""


def list_latest():
    # [대시보드 조회] 로봇 기본 정보가 없어도 서비스가 AMR1·AMR2 빈 카드를 만든다.
    return get_db().execute(
        """
        SELECT r.robot_id, r.name, s.message_id, s.battery, s.x, s.y,
               s.frame_id, s.pose_valid, s.last_valid_pose_at,
               s.mission_status, s.safety_state, s.motion_stopped,
               s.safety_reason_code, s.safety_reason, s.connection_status,
               s.observed_at, s.received_at
          FROM robots AS r
          LEFT JOIN robot_latest_status AS s ON s.robot_id = r.robot_id
         WHERE r.robot_id IN ('AMR1', 'AMR2')
         ORDER BY r.robot_id
        """
    ).fetchall()


def _seconds_between(earlier, later):
    """저장 형식(ISO 8601, 밀리초, Z)의 두 시각 차이를 초로 돌려준다."""
    start = datetime.fromisoformat(earlier.replace("Z", "+00:00"))
    end = datetime.fromisoformat(later.replace("Z", "+00:00"))
    return (end - start).total_seconds()


def _same_message(existing, status):
    # [재전송 판별] ID만 같고 내용이 바뀐 메시지는 정상 재전송으로 처리하지 않는다.
    return all(existing[column] == status[column] for column in STATUS_COLUMNS)


def store_status(status, received_at, history_min_interval_seconds=0.0, history_cutoff=None):
    """검증을 마친 상태를 최신 행과 이력에 원자적으로 저장한다.

    history_min_interval_seconds: 로봇별 직전 이력 관측 시각과 이보다 가까우면 이력 행을 만들지
        않고 최신 행만 갱신한다. 0이면 모든 관측을 이력에 남긴다.
    history_cutoff: ISO 시각 문자열. 주어지면 이보다 오래된 이력 행을 같은 transaction에서 지운다.
    """
    db = get_db()
    try:
        # [쓰기 순서 보호] 중복·시각 비교부터 두 테이블 저장까지 다른 쓰기가 끼어들지 않게 한다.
        db.execute("BEGIN IMMEDIATE")
        duplicate = db.execute(
            "SELECT robot_id, message_id, battery, x, y, frame_id, pose_valid, "
            "last_valid_pose_at, mission_status, safety_state, motion_stopped, "
            "safety_reason_code, safety_reason, connection_status, observed_at, "
            "received_at FROM robot_status_history WHERE message_id = ?",
            (status["message_id"],),
        ).fetchone()
        if duplicate is not None:
            if not _same_message(duplicate, status):
                raise MessageIdConflictError
            db.commit()
            return "duplicate", dict(duplicate)

        latest = db.execute(
            "SELECT observed_at FROM robot_latest_status WHERE robot_id = ?",
            (status["robot_id"],),
        ).fetchone()
        if latest is not None and status["observed_at"] <= latest["observed_at"]:
            raise StaleStatusError(latest["observed_at"])
        # [이력 샘플링] 최신 행은 항상 갱신한다. 이력은 직전 이력과 간격이 짧으면 건너뛰어
        # 2 Hz 수신을 1 Hz 기록으로 줄인다. 지나온 길(최근 120행)·이력 검색은 그대로 동작한다.
        record_history = True
        if history_min_interval_seconds > 0 and latest is not None:
            previous = db.execute(
                "SELECT observed_at FROM robot_status_history "
                "WHERE robot_id = ? ORDER BY observed_at DESC LIMIT 1",
                (status["robot_id"],),
            ).fetchone()
            if previous is not None:
                gap = _seconds_between(previous["observed_at"], status["observed_at"])
                record_history = gap >= history_min_interval_seconds

        # [기본 정보 등록] 허용된 로봇의 첫 상태를 받을 때만 기본 행을 만든다.
        robot_name = "로봇 1" if status["robot_id"] == "AMR1" else "로봇 2"
        db.execute(
            "INSERT INTO robots (robot_id, name) VALUES (?, ?) "
            "ON CONFLICT(robot_id) DO UPDATE SET name = excluded.name",
            (status["robot_id"], robot_name),
        )
        values = tuple(status[column] for column in STATUS_COLUMNS) + (received_at,)
        if record_history:
            db.execute(
                """
                INSERT INTO robot_status_history
                    (robot_id, message_id, battery, x, y, frame_id, pose_valid,
                     last_valid_pose_at, mission_status, safety_state, motion_stopped,
                     safety_reason_code, safety_reason, connection_status,
                     observed_at, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        db.execute(
            """
            INSERT INTO robot_latest_status
                (robot_id, message_id, battery, x, y, frame_id, pose_valid,
                 last_valid_pose_at, mission_status, safety_state, motion_stopped,
                 safety_reason_code, safety_reason, connection_status,
                 observed_at, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(robot_id) DO UPDATE SET
                message_id = excluded.message_id,
                battery = excluded.battery,
                x = excluded.x,
                y = excluded.y,
                frame_id = excluded.frame_id,
                pose_valid = excluded.pose_valid,
                last_valid_pose_at = excluded.last_valid_pose_at,
                mission_status = excluded.mission_status,
                safety_state = excluded.safety_state,
                motion_stopped = excluded.motion_stopped,
                safety_reason_code = excluded.safety_reason_code,
                safety_reason = excluded.safety_reason,
                connection_status = excluded.connection_status,
                observed_at = excluded.observed_at,
                received_at = excluded.received_at
            """,
            values,
        )
        pruned = 0
        if history_cutoff:
            # [보존 정리] 같은 transaction에서 오래된 이력을 지워 표 크기를 보존 기간 안에 묶는다.
            # idx_status_robot_time 인덱스가 observed_at 범위 삭제를 빠르게 한다.
            pruned = db.execute(
                "DELETE FROM robot_status_history WHERE observed_at < ?", (history_cutoff,)
            ).rowcount
        db.commit()
        return "accepted", {
            **status, "received_at": received_at,
            "history_recorded": record_history, "history_pruned": pruned,
        }
    except Exception:
        # [저장 실패] 최신 상태와 이력이 한쪽만 남지 않도록 전체 저장을 되돌린다.
        db.rollback()
        raise


def last_valid_pose(robot_id):
    """현재 위치가 무효일 때 화면에 함께 보여줄 마지막 유효 위치를 찾는다."""
    return get_db().execute(
        """
        SELECT x, y, frame_id, observed_at
          FROM robot_status_history
         WHERE robot_id = ? AND pose_valid = 1 AND x IS NOT NULL AND y IS NOT NULL
         ORDER BY observed_at DESC
         LIMIT 1
        """,
        (robot_id,),
    ).fetchone()
