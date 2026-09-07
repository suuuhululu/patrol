"""로봇별 global/local costmap 최신 메타데이터의 SQLite 접근 코드."""

from ..database import get_db


COSTMAP_COMPARE_COLUMNS = (
    "message_id", "frame_id", "resolution", "width", "height",
    "origin_x", "origin_y", "origin_yaw", "content_hash",
)


class CostmapMessageConflictError(Exception):
    """같은 로봇·계층·메시지 ID에 서로 다른 내용이 들어온 경우."""


class StaleCostmapError(Exception):
    """해당 로봇·계층의 최신 costmap보다 오래된 격자가 들어온 경우."""


def latest_costmap(robot_id, layer):
    return get_db().execute(
        "SELECT * FROM costmap_latest WHERE robot_id = ? AND layer = ?",
        (robot_id, layer),
    ).fetchone()


def all_latest_costmaps():
    return get_db().execute(
        "SELECT * FROM costmap_latest ORDER BY robot_id, layer"
    ).fetchall()


def _same_costmap(existing, record):
    # [재전송 판별] ID만 같고 격자 또는 좌표 기준이 바뀐 입력은 충돌로 처리한다.
    return all(existing[column] == record[column] for column in COSTMAP_COMPARE_COLUMNS)


def store_costmap(record):
    """로봇·계층별 최신 한 행을 원자적으로 교체하고 이전 이미지 이름을 반환한다."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = latest_costmap(record["robot_id"], record["layer"])
        if existing is not None and existing["message_id"] == record["message_id"]:
            if not _same_costmap(existing, record):
                raise CostmapMessageConflictError
            db.commit()
            return "duplicate", dict(existing), None
        if existing is not None and record["observed_at"] <= existing["observed_at"]:
            raise StaleCostmapError(existing["observed_at"])

        previous_image = existing["image_path"] if existing is not None else None
        columns = (
            "robot_id", "layer", "message_id", "frame_id", "resolution",
            "width", "height", "origin_x", "origin_y", "origin_yaw",
            "content_hash", "image_path", "observed_at", "received_at",
        )
        db.execute(
            """
            INSERT INTO costmap_latest
                (robot_id, layer, message_id, frame_id, resolution, width, height,
                 origin_x, origin_y, origin_yaw, content_hash, image_path,
                 observed_at, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(robot_id, layer) DO UPDATE SET
                message_id=excluded.message_id, frame_id=excluded.frame_id,
                resolution=excluded.resolution, width=excluded.width,
                height=excluded.height, origin_x=excluded.origin_x,
                origin_y=excluded.origin_y, origin_yaw=excluded.origin_yaw,
                content_hash=excluded.content_hash, image_path=excluded.image_path,
                observed_at=excluded.observed_at, received_at=excluded.received_at
            """,
            tuple(record[column] for column in columns),
        )
        db.commit()
        return "accepted", record, previous_image
    except Exception:
        # [교체 실패] 기존 최신 행을 보존해 화면과 파일 참조가 어긋나지 않게 한다.
        db.rollback()
        raise
