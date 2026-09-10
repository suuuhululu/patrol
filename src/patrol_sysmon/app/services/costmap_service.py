"""Nav2 costmap 검증·최신 파일 교체·대시보드 표시 처리."""

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import tempfile

from flask import current_app

from ..models import costmap as costmap_model
from .map_service import downsample_grid, occupancy_to_png, robot_overlay, validate_map


COSTMAP_SOURCES = (
    ("AMR1", "global"), ("AMR1", "local"),
    ("AMR2", "global"), ("AMR2", "local"),
)
# [NAV 지도 바탕] global costmap은 정적 지도 층을 포함하므로 NAV 지도 바탕으로 쓴다.
# local costmap은 로봇 주변만 따라다니는 격자라 바탕으로 쓰지 않는다.
NAV_LAYER = "global"
NAV_ROBOTS = ("AMR1", "AMR2")


class CostmapValidationError(ValueError):
    """costmap의 로봇 또는 계층 식별자가 허용 범위를 벗어난 경우."""


def validate_source(robot_id, layer):
    normalized_robot = robot_id.upper() if isinstance(robot_id, str) else ""
    normalized_layer = layer.lower() if isinstance(layer, str) else ""
    if (normalized_robot, normalized_layer) not in COSTMAP_SOURCES:
        raise CostmapValidationError("costmap source는 AMR1·AMR2의 global·local 중 하나여야 합니다.")
    return normalized_robot, normalized_layer


def receive_costmap(robot_id, layer, payload, now=None):
    """검증한 동적 격자를 로봇·계층별 최신 PNG와 DB 한 행으로 교체한다."""
    source = validate_source(robot_id, layer)
    current = now or datetime.now(timezone.utc)
    grid = validate_map(payload, current)
    hash_input = {"robot_id": source[0], "layer": source[1], **grid}
    content_hash = sha256(
        json.dumps(hash_input, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    image_name = f"costmap-{source[0].lower()}-{source[1]}-{content_hash[:24]}.png"
    directory = Path(current_app.config["COSTMAP_DIR"])
    image_path = directory / image_name
    created = False
    if not image_path.exists():
        temporary_path = None
        try:
            image_data, image_width, image_height = downsample_grid(
                grid["data"], grid["width"], grid["height"],
                current_app.config["MAP_MAX_IMAGE_SIDE"],
            )
            png = occupancy_to_png(image_data, image_width, image_height)
            with tempfile.NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as stream:
                temporary_path = Path(stream.name)
                stream.write(png)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, image_path)
            created = True
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    received_at = current.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    record = {key: value for key, value in grid.items() if key != "data"}
    record.update(
        robot_id=source[0], layer=source[1], content_hash=content_hash,
        image_path=image_name, received_at=received_at,
    )
    try:
        outcome, stored, previous_image = costmap_model.store_costmap(record)
    except Exception:
        if created:
            image_path.unlink(missing_ok=True)
        raise
    # [최신 한 장 정책] DB 교체가 확정된 뒤에만 더 이상 참조하지 않는 이전 PNG를 지운다.
    if previous_image and previous_image != image_name:
        (directory / previous_image).unlink(missing_ok=True)
    return outcome, stored


def dashboard_costmaps():
    """아직 수신하지 않은 source도 포함해 화면용 네 슬롯을 고정 순서로 반환한다."""
    rows = {
        (row["robot_id"], row["layer"]): dict(row)
        for row in costmap_model.all_latest_costmaps()
    }
    result = []
    for robot_id, layer in COSTMAP_SOURCES:
        row = rows.get((robot_id, layer))
        result.append({
            "robot_id": robot_id,
            "layer": layer,
            "label": f"{robot_id} {layer}",
            "available": row is not None,
            "state_label": "수신됨" if row else "수신 대기",
            "message_id": row["message_id"] if row else None,
            "frame_id": row["frame_id"] if row else None,
            "resolution": row["resolution"] if row else None,
            "width": row["width"] if row else None,
            "height": row["height"] if row else None,
            "origin": ({"x": row["origin_x"], "y": row["origin_y"], "yaw": row["origin_yaw"]} if row else None),
            "content_hash": row["content_hash"] if row else None,
            "observed_at": row["observed_at"] if row else None,
        })
    return result


def dashboard_nav_map(robot_id=None, now=None):
    """선택한 로봇의 global costmap을 바탕으로 로봇 위치·최근 경로를 SVG용 JSON으로 만든다.

    robot_id가 없으면 가장 최근에 받은 로봇을 고른다. 선택한 로봇이 아직 없으면
    다른 로봇으로 몰래 바꾸지 않고 수신 대기로 알린다.
    """
    rows = {}
    for candidate in NAV_ROBOTS:
        row = costmap_model.latest_costmap(candidate, NAV_LAYER)
        if row is not None:
            rows[candidate] = dict(row)
    sources = [{"robot_id": candidate, "available": candidate in rows} for candidate in NAV_ROBOTS]
    if robot_id is None:
        selected = max(rows, key=lambda key: rows[key]["received_at"]) if rows else None
    else:
        selected = validate_source(robot_id, NAV_LAYER)[0]
    grid = rows.get(selected)
    if grid is None:
        label = f"{selected} 수신 대기" if selected else "수신 대기"
        return {"available": False, "state_label": label, "source_robot": selected,
                "sources": sources, "robots": [], "paths": [], "coordinate_warnings": []}
    markers, paths, coordinate_warnings = robot_overlay(grid, now)
    return {
        "available": True, "state_label": "수신 중",
        "source_robot": selected, "sources": sources,
        "message_id": grid["message_id"], "frame_id": grid["frame_id"],
        "resolution": grid["resolution"], "width": grid["width"], "height": grid["height"],
        "origin": {"x": grid["origin_x"], "y": grid["origin_y"], "yaw": grid["origin_yaw"]},
        "content_hash": grid["content_hash"], "observed_at": grid["observed_at"],
        "robots": markers, "paths": paths, "coordinate_warnings": coordinate_warnings,
    }
