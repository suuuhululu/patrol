"""Nav2 지도 메타데이터와 로봇 이동 경로의 SQLite 접근 코드."""

from ..database import get_db


MAP_COMPARE_COLUMNS = (
    "message_id", "frame_id", "resolution", "width", "height",
    "origin_x", "origin_y", "origin_yaw", "content_hash",
)


class MapMessageConflictError(Exception):
    """같은 지도 메시지 ID에 서로 다른 내용이 들어온 경우."""


class StaleMapError(Exception):
    """현재 지도보다 오래된 지도가 들어온 경우."""


def current_map():
    return get_db().execute(
        """
        SELECT m.*
          FROM map_latest AS latest
          JOIN maps AS m ON m.id = latest.map_id
         WHERE latest.singleton = 1
        """
    ).fetchone()


def _same_map(existing, map_record):
    # [재전송 판별] 메시지 ID만 같고 격자나 좌표 기준이 바뀐 입력은 충돌로 처리한다.
    return all(existing[column] == map_record[column] for column in MAP_COMPARE_COLUMNS)


def store_map(map_record):
    """지도 이력을 보존하고 현재 지도 포인터를 한 트랜잭션에서 갱신한다."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        duplicate = db.execute(
            "SELECT * FROM maps WHERE message_id = ?", (map_record["message_id"],)
        ).fetchone()
        if duplicate is not None:
            if not _same_map(duplicate, map_record):
                raise MapMessageConflictError
            db.commit()
            return "duplicate", dict(duplicate)

        latest = current_map()
        if latest is not None and map_record["observed_at"] <= latest["observed_at"]:
            raise StaleMapError(latest["observed_at"])

        cursor = db.execute(
            """
            INSERT INTO maps
                (message_id, frame_id, resolution, width, height,
                 origin_x, origin_y, origin_yaw, content_hash, image_path,
                 observed_at, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(map_record[column] for column in (
                "message_id", "frame_id", "resolution", "width", "height",
                "origin_x", "origin_y", "origin_yaw", "content_hash", "image_path",
                "observed_at", "received_at",
            )),
        )
        db.execute(
            """
            INSERT INTO map_latest (singleton, map_id) VALUES (1, ?)
            ON CONFLICT(singleton) DO UPDATE SET map_id = excluded.map_id
            """,
            (cursor.lastrowid,),
        )
        db.commit()
        return "accepted", {**map_record, "id": cursor.lastrowid}
    except Exception:
        # [지도 저장 실패] 현재 지도 포인터와 이력이 서로 다른 상태로 남지 않게 되돌린다.
        db.rollback()
        raise


def recent_positions(robot_id, frame_id, limit=120):
    # [경로 조회] 최신 위치부터 제한해서 읽은 뒤 지도에는 시간 순서로 전달한다.
    rows = get_db().execute(
        """
        SELECT x, y, observed_at
          FROM robot_status_history
         WHERE robot_id = ? AND frame_id = ? AND x IS NOT NULL AND y IS NOT NULL
         ORDER BY observed_at DESC
         LIMIT ?
        """,
        (robot_id, frame_id, limit),
    ).fetchall()
    return list(reversed(rows))
