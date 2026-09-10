"""Nav2 OccupancyGrid 형태의 지도 검증·PNG 변환·웹 좌표 계산."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import json
import math
import os
import re
import struct
import tempfile
import zlib

from flask import current_app

from ..models import map as map_model
from . import robot_service


MESSAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class MapValidationError(ValueError):
    """지도 입력이 내부 OccupancyGrid 규약과 다를 때 사용한다."""


def _finite_number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MapValidationError(f"{field} 값은 유한한 숫자여야 합니다.")
    return float(value)


def _utc_timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise MapValidationError("observed_at은 시간대가 포함된 ISO 8601 시각이어야 합니다.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MapValidationError("observed_at에 시간대가 필요합니다.")
    return parsed.astimezone(timezone.utc)


def validate_map(payload, now=None):
    """ROS adapter와 임시 HTTP 입력이 함께 사용할 지도 형식으로 정규화한다."""
    if not isinstance(payload, dict):
        raise MapValidationError("JSON 객체 형식의 지도가 필요합니다.")
    message_id = payload.get("message_id")
    if not isinstance(message_id, str) or not MESSAGE_ID_PATTERN.fullmatch(message_id.strip()):
        raise MapValidationError("message_id 형식이 올바르지 않습니다.")
    frame_id = payload.get("frame_id")
    if frame_id != current_app.config["MAP_FRAME_ID"]:
        raise MapValidationError(f'frame_id는 {current_app.config["MAP_FRAME_ID"]}이어야 합니다.')
    width = payload.get("width")
    height = payload.get("height")
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        raise MapValidationError("width는 1 이상의 정수여야 합니다.")
    if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
        raise MapValidationError("height는 1 이상의 정수여야 합니다.")
    if width * height > current_app.config["MAP_MAX_CELLS"]:
        raise MapValidationError("지도 격자 수가 서버 제한을 초과했습니다.")
    resolution = _finite_number(payload.get("resolution"), "resolution")
    if not 0.001 <= resolution <= 10:
        raise MapValidationError("resolution은 0.001에서 10 사이여야 합니다.")
    origin = payload.get("origin")
    if not isinstance(origin, dict):
        raise MapValidationError("origin 객체가 필요합니다.")
    origin_x = _finite_number(origin.get("x"), "origin.x")
    origin_y = _finite_number(origin.get("y"), "origin.y")
    origin_yaw = _finite_number(origin.get("yaw", 0), "origin.yaw")
    occupancy = payload.get("data")
    if not isinstance(occupancy, list) or len(occupancy) != width * height:
        raise MapValidationError("data 길이는 width × height와 같아야 합니다.")
    if any(isinstance(value, bool) or not isinstance(value, int) or not -1 <= value <= 100
           for value in occupancy):
        raise MapValidationError("data 값은 -1에서 100 사이의 정수여야 합니다.")
    observed = _utc_timestamp(payload.get("observed_at"))
    current = now or datetime.now(timezone.utc)
    if observed > current + timedelta(minutes=5):
        raise MapValidationError("observed_at이 서버 시각보다 5분 이상 미래입니다.")
    return {
        "message_id": message_id.strip(), "frame_id": frame_id,
        "resolution": resolution, "width": width, "height": height,
        "origin_x": origin_x, "origin_y": origin_y, "origin_yaw": origin_yaw,
        "data": occupancy,
        "observed_at": observed.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }


def _png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


def occupancy_to_png(occupancy, width, height):
    """OccupancyGrid의 아래쪽 원점을 PNG 위쪽 원점으로 뒤집어 RGBA 이미지로 만든다."""
    rows = bytearray()
    for output_y in range(height):
        source_start = (height - 1 - output_y) * width
        rows.append(0)
        for value in occupancy[source_start:source_start + width]:
            if value < 0:
                # [미탐색 칸] 색을 칠하면 지도 가장자리가 여백처럼 보이므로 투명하게 둔다.
                color = (0, 0, 0, 0)
            else:
                shade = round(235 - (value / 100) * 205)
                color = (shade, shade, shade, 255)
            rows.extend(color)
    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return signature + _png_chunk(b"IHDR", header) + _png_chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + _png_chunk(b"IEND", b"")


def downsample_grid(occupancy, width, height, max_side):
    """화면용 PNG가 너무 커지지 않게 격자를 일정 간격으로 솎는다.

    좌표 변환에는 원본 해상도·크기를 그대로 사용하고 이미지 픽셀 수만 줄인다.
    화면은 원본 크기의 viewBox에 이미지를 늘려 그리므로 마커 위치는 달라지지 않는다.
    """
    step = 1
    while -(-width // step) > max_side or -(-height // step) > max_side:
        step += 1
    if step == 1:
        return occupancy, width, height
    rows = []
    for y in range(0, height, step):
        start = y * width
        # 슬라이스로 한 줄씩 솎아 큰 격자에서도 처리 시간을 짧게 유지한다.
        rows.extend(occupancy[start:start + width:step])
    return rows, -(-width // step), -(-height // step)


def receive_map(payload, now=None):
    """검증한 지도 이미지를 파일에 기록하고 메타데이터를 DB에 저장한다."""
    current = now or datetime.now(timezone.utc)
    grid = validate_map(payload, current)
    hash_source = json.dumps(grid, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    content_hash = sha256(hash_source).hexdigest()
    image_name = f"map-{content_hash[:24]}.png"
    map_dir = Path(current_app.config["MAP_DIR"])
    image_path = map_dir / image_name
    created = False
    if not image_path.exists():
        image_data, image_width, image_height = downsample_grid(
            grid["data"], grid["width"], grid["height"],
            current_app.config["MAP_MAX_IMAGE_SIDE"],
        )
        png = occupancy_to_png(image_data, image_width, image_height)
        # [원자적 파일 저장] 브라우저가 생성 중인 PNG를 읽지 않도록 완성 후 이름을 바꾼다.
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=map_dir, suffix=".tmp", delete=False) as stream:
                temporary_path = Path(stream.name)
                stream.write(png)
            os.replace(temporary_path, image_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        created = True
    received_at = current.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    record = {key: value for key, value in grid.items() if key != "data"}
    record.update(content_hash=content_hash, image_path=image_name, received_at=received_at)
    try:
        return map_model.store_map(record)
    except Exception:
        # [DB 실패 정리] 이번 요청이 새로 만든 파일만 제거하며 기존 지도를 건드리지 않는다.
        if created:
            image_path.unlink(missing_ok=True)
        raise


def _screen_point(x, y, map_row):
    """map 좌표를 원점 회전까지 반영한 이미지 격자 좌표로 바꾼다."""
    dx = x - map_row["origin_x"]
    dy = y - map_row["origin_y"]
    cosine = math.cos(map_row["origin_yaw"])
    sine = math.sin(map_row["origin_yaw"])
    grid_x = (cosine * dx + sine * dy) / map_row["resolution"]
    grid_y = (-sine * dx + cosine * dy) / map_row["resolution"]
    return grid_x, map_row["height"] - grid_y


def _inside_map(point, map_row):
    return 0 <= point[0] <= map_row["width"] and 0 <= point[1] <= map_row["height"]


def robot_overlay(map_data, now=None):
    """격자 메타데이터 기준으로 로봇 마커·최근 경로·좌표 경고를 이미지 격자 좌표로 만든다."""
    robots = robot_service.dashboard_robots(now)
    markers = []
    paths = []
    coordinate_warnings = []
    for robot in robots:
        if not robot["has_status"]:
            continue
        if robot["frame_id"] != map_data["frame_id"]:
            coordinate_warnings.append(
                f'{robot["id"]} 좌표계 {robot["frame_id"]}는 지도 좌표계 {map_data["frame_id"]}와 다릅니다.'
            )
            continue
        # [위치 유효성] 현재 위치가 무효면 마지막 유효 위치를 다른 표시로 그린다.
        pose_valid = robot["pose_valid"]
        x = robot["x"] if pose_valid else robot["last_valid_x"]
        y = robot["y"] if pose_valid else robot["last_valid_y"]
        if x is None or y is None:
            coordinate_warnings.append(f'{robot["id"]} 위치를 확인할 수 없습니다.')
            continue
        point = _screen_point(x, y, map_data)
        marker = {
            "id": robot["id"], "name": robot["name"],
            "x": round(point[0], 3), "y": round(point[1], 3),
            "inside_map": _inside_map(point, map_data),
            "connection_status": robot["connection_status"],
            "pose_valid": pose_valid,
            "pose_label": robot["id"] if pose_valid else f'{robot["id"]} 마지막 유효',
        }
        if not pose_valid:
            coordinate_warnings.append(
                f'{robot["id"]} 현재 위치가 무효입니다. 마지막 유효 위치를 표시합니다.'
            )
        markers.append(marker)
        history = map_model.recent_positions(robot["id"], map_data["frame_id"])
        points = []
        for row in history:
            history_point = _screen_point(row["x"], row["y"], map_data)
            if _inside_map(history_point, map_data):
                points.append({"x": round(history_point[0], 3), "y": round(history_point[1], 3)})
        paths.append({"robot_id": robot["id"], "points": points})
    return markers, paths, coordinate_warnings


def dashboard_map(now=None):
    """현재 지도와 로봇 위치·최근 경로를 SVG가 그릴 JSON 형태로 만든다."""
    map_row = map_model.current_map()
    if map_row is None:
        return {"available": False, "state_label": "지도 수신 대기", "robots": [], "paths": [],
                "coordinate_warnings": []}
    map_data = dict(map_row)
    markers, paths, coordinate_warnings = robot_overlay(map_data, now)
    return {
        "available": True, "state_label": "NAV 지도 수신",
        "message_id": map_data["message_id"], "frame_id": map_data["frame_id"],
        "resolution": map_data["resolution"], "width": map_data["width"],
        "height": map_data["height"], "origin": {
            "x": map_data["origin_x"], "y": map_data["origin_y"], "yaw": map_data["origin_yaw"],
        },
        "content_hash": map_data["content_hash"], "observed_at": map_data["observed_at"],
        "robots": markers, "paths": paths, "coordinate_warnings": coordinate_warnings,
    }
