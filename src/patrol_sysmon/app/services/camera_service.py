"""ROS 영상 토픽 연결 전 최신 카메라 프레임의 검증·교체·표시 처리."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import fcntl
import json
import os
import re
import struct
import tempfile
from zoneinfo import ZoneInfo

from flask import current_app


CAMERAS = {
    "amr1": {"name": "로봇 1 카메라", "source": "AMR1", "kind": "이동형"},
    "amr2": {"name": "로봇 2 카메라", "source": "AMR2", "kind": "이동형"},
    "webcam1": {"name": "고정 웹캠 1", "source": "CAM 01", "kind": "고정형"},
    "webcam2": {"name": "고정 웹캠 2", "source": "CAM 02", "kind": "고정형"},
}
FRAME_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
KST = ZoneInfo("Asia/Seoul")


class CameraValidationError(ValueError):
    """카메라 ID·프레임·시각이 임시 영상 규약과 다를 때 사용한다."""


class CameraFrameConflictError(RuntimeError):
    """같은 frame_id에 다른 영상이 들어왔을 때 사용한다."""


class StaleCameraFrameError(RuntimeError):
    """현재 프레임보다 오래된 영상이 도착했을 때 사용한다."""


def _camera_id(value):
    camera_id = value.lower() if isinstance(value, str) else ""
    if camera_id not in CAMERAS:
        raise CameraValidationError("camera_id는 amr1, amr2, webcam1, webcam2 중 하나여야 합니다.")
    return camera_id


def _utc_timestamp(value, now):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise CameraValidationError("X-Captured-At은 시간대가 포함된 ISO 8601 시각이어야 합니다.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CameraValidationError("X-Captured-At에 시간대가 필요합니다.")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > now + timedelta(minutes=5):
        raise CameraValidationError("촬영 시각이 서버 시각보다 5분 이상 미래입니다.")
    return parsed


def _detect_image(image_bytes):
    """선언된 Content-Type 대신 실제 바이트를 검사해 PNG/JPEG만 허용한다."""
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") and len(image_bytes) >= 24:
        width, height = struct.unpack(">II", image_bytes[16:24])
        if width and height:
            return "image/png", width, height
    if image_bytes.startswith(b"\xff\xd8\xff") and image_bytes.endswith(b"\xff\xd9"):
        return "image/jpeg", None, None
    raise CameraValidationError("영상 프레임은 유효한 PNG 또는 JPEG 파일이어야 합니다.")


def validate_frame(camera_id, frame_id, captured_at, image_stream, now=None):
    """HTTP adapter와 향후 ROS adapter가 공통으로 사용할 최신 프레임 형식으로 정규화한다."""
    current = now or datetime.now(timezone.utc)
    normalized_camera = _camera_id(camera_id)
    if not isinstance(frame_id, str) or not FRAME_ID_PATTERN.fullmatch(frame_id.strip()):
        raise CameraValidationError("X-Frame-Id 형식이 올바르지 않습니다.")
    captured = _utc_timestamp(captured_at, current)
    if image_stream is None:
        raise CameraValidationError("영상 프레임이 필요합니다.")
    maximum = current_app.config["VIDEO_FRAME_MAX_BYTES"]
    image_bytes = image_stream.read(maximum + 1)
    if not image_bytes:
        raise CameraValidationError("영상 프레임이 비어 있습니다.")
    if len(image_bytes) > maximum:
        raise CameraValidationError(f"영상 프레임은 {maximum // 1024}KB 이하여야 합니다.")
    mimetype, width, height = _detect_image(image_bytes)
    return {
        "camera_id": normalized_camera,
        "frame_id": frame_id.strip(),
        "captured_at": captured.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "received_at": current.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "content_hash": sha256(image_bytes).hexdigest(),
        "mimetype": mimetype,
        "width": width,
        "height": height,
        "image_bytes": image_bytes,
    }


def _paths(camera_id):
    directory = Path(current_app.config["VIDEO_DIR"])
    return directory / f"{camera_id}.frame", directory / f"{camera_id}.json", directory / f"{camera_id}.lock"


def _read_metadata(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _atomic_write(path, content, binary=False):
    """브라우저가 쓰는 중간 파일을 읽지 않도록 같은 폴더에서 완성 후 교체한다."""
    temporary_path = None
    mode = "wb" if binary else "w"
    kwargs = {} if binary else {"encoding": "utf-8"}
    try:
        with tempfile.NamedTemporaryFile(mode=mode, dir=path.parent, suffix=".tmp", delete=False, **kwargs) as stream:
            temporary_path = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def receive_frame(camera_id, frame_id, captured_at, image_stream, now=None):
    """카메라별 최신 프레임 한 장만 교체하고 과거 영상은 축적하지 않는다."""
    frame = validate_frame(camera_id, frame_id, captured_at, image_stream, now)
    image_path, metadata_path, lock_path = _paths(frame["camera_id"])
    # [동시 프레임] 프로세스가 여러 개여도 카메라별 순서 검사와 교체가 섞이지 않게 잠근다.
    with lock_path.open("a+b") as lock_stream:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        existing = _read_metadata(metadata_path)
        if existing and existing.get("frame_id") == frame["frame_id"]:
            if existing.get("content_hash") == frame["content_hash"] and existing.get("captured_at") == frame["captured_at"]:
                return "duplicate", existing
            raise CameraFrameConflictError
        if existing and frame["captured_at"] <= existing.get("captured_at", ""):
            raise StaleCameraFrameError(existing.get("captured_at"))
        _atomic_write(image_path, frame["image_bytes"], binary=True)
        metadata = {key: value for key, value in frame.items() if key != "image_bytes"}
        _atomic_write(
            metadata_path,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        return "accepted", metadata


def frame_metadata(camera_id):
    """유효한 최신 파일과 메타데이터가 모두 있을 때만 프레임을 제공한다."""
    normalized = _camera_id(camera_id)
    image_path, metadata_path, _ = _paths(normalized)
    metadata = _read_metadata(metadata_path)
    if not metadata or metadata.get("camera_id") != normalized or not image_path.is_file():
        return None
    return metadata


def frame_path(camera_id):
    normalized = _camera_id(camera_id)
    image_path, _, _ = _paths(normalized)
    return image_path


def _parse_utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def dashboard_cameras(now=None):
    """네 카메라의 최신 프레임 URL 구성에 필요한 상태를 고정된 순서로 반환한다."""
    current = now or datetime.now(timezone.utc)
    timeout = timedelta(seconds=current_app.config["CAMERA_OFFLINE_AFTER_SECONDS"])
    result = []
    for camera_id, definition in CAMERAS.items():
        metadata = frame_metadata(camera_id)
        available = metadata is not None
        live = False
        received_label = "수신 영상 없음"
        if available:
            try:
                received = _parse_utc(metadata["received_at"])
                live = current - received <= timeout
                received_label = "방금 수신" if live else received.astimezone(KST).strftime("마지막 수신 %m-%d %H:%M:%S")
            except (KeyError, TypeError, ValueError):
                available = False
                metadata = None
        state = "LIVE" if live else ("연결 끊김" if available else "수신 대기")
        result.append({
            "id": camera_id, **definition,
            "available": available, "live": live, "state_label": state,
            "received_label": received_label,
            "frame_id": metadata.get("frame_id") if metadata else None,
            "captured_at": metadata.get("captured_at") if metadata else None,
            "version": metadata.get("content_hash", "")[:16] if metadata else None,
        })
    return result
