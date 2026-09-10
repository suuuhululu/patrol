"""ROS DetectionEvent 저장과 EvidenceChunk 재조립·무결성 검증."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import math
import os
import re
import tempfile
import uuid

from flask import current_app

from ..models import detection as detection_model
from ..models.detection import DetectionMessageConflictError
from . import event_service
from .robot_service import ROBOT_NAMES


UUID_V4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
# [제품 범위] event_service와 같은 세 종류만 저장한다.
# LIGHTING·FACILITY_DAMAGE는 계약 enum이지만 이번 범위 밖이라 REJECTED로 회신한다.
EVENT_TYPES = {"FIRE", "LEAK", "OBSTACLE"}
RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}
MEDIA_TYPES = {"image/jpeg": ".jpg", "image/png": ".png"}
MAX_CHUNK_BYTES = 64 * 1024


class DetectionValidationError(ValueError):
    """ROS DetectionEvent 또는 EvidenceChunk가 계약 형식과 다를 때 사용한다."""


def _uuid_v4(value, field, allow_empty=False):
    if allow_empty and value == "":
        return ""
    if not isinstance(value, str) or not UUID_V4_PATTERN.fullmatch(value):
        raise DetectionValidationError(f"{field}는 소문자 UUID v4여야 합니다.")
    try:
        parsed = uuid.UUID(value, version=4)
    except ValueError as exc:
        raise DetectionValidationError(f"{field}는 소문자 UUID v4여야 합니다.") from exc
    if str(parsed) != value:
        raise DetectionValidationError(f"{field}는 소문자 UUID v4여야 합니다.")
    return value


def _timestamp(value, field, now):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise DetectionValidationError(f"{field}은 시간대가 포함된 ISO 8601 시각이어야 합니다.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DetectionValidationError(f"{field}에 시간대가 필요합니다.")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > now + timedelta(minutes=5):
        raise DetectionValidationError(f"{field}이 서버 시각보다 5분 이상 미래입니다.")
    return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _finite(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise DetectionValidationError(f"{field} 값은 유한한 숫자여야 합니다.")
    return float(value)


def validate_detection(payload, now=None):
    """adapter가 변환한 DetectionEvent를 저장 가능한 내부 사건으로 정규화한다."""
    if not isinstance(payload, dict):
        raise DetectionValidationError("DetectionEvent 객체가 필요합니다.")
    current = now or datetime.now(timezone.utc)
    robot_id = payload.get("robot_id")
    if robot_id not in ROBOT_NAMES:
        raise DetectionValidationError("robot_id는 AMR1 또는 AMR2여야 합니다.")
    event_type = payload.get("event_type")
    if event_type not in EVENT_TYPES:
        raise DetectionValidationError(
            "EVENT_UNKNOWN과 범위 밖 event_type(LIGHTING·FACILITY_DAMAGE)은 저장하지 않습니다."
        )
    risk_level = payload.get("risk_level")
    if risk_level not in RISK_LEVELS:
        raise DetectionValidationError("RISK_UNKNOWN 또는 지원하지 않는 risk_level은 저장할 수 없습니다.")
    if payload.get("frame_id") != "map":
        raise DetectionValidationError("DetectionEvent header.frame_id는 map이어야 합니다.")
    location_valid = payload.get("location_valid")
    if not isinstance(location_valid, bool):
        raise DetectionValidationError("location_valid는 bool이어야 합니다.")
    x = y = None
    if location_valid:
        x = _finite(payload.get("x"), "pose.position.x")
        y = _finite(payload.get("y"), "pose.position.y")
    confidence = _finite(payload.get("confidence"), "confidence")
    if not 0.0 <= confidence <= 1.0:
        raise DetectionValidationError("confidence는 0.0에서 1.0 사이여야 합니다.")
    received_at = current.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return {
        "message_id": _uuid_v4(payload.get("message_id"), "message_id"),
        "event_id": _uuid_v4(payload.get("event_id"), "event_id"),
        "robot_id": robot_id,
        "robot_name": ROBOT_NAMES[robot_id],
        "event_type": event_type,
        "confidence": confidence,
        "risk_level": risk_level,
        "x": x,
        "y": y,
        "frame_id": "map",
        "location_valid": int(location_valid),
        "occurred_at": _timestamp(payload.get("detected_at"), "detected_at", current),
        "evidence_id": _uuid_v4(
            payload.get("evidence_id"), "evidence_id", allow_empty=True
        ) or None,
        "received_at": received_at,
    }


def receive_detection(payload, now=None):
    event = validate_detection(payload, now)
    hash_source = {key: value for key, value in event.items() if key not in {"received_at", "robot_name"}}
    content_hash = sha256(
        json.dumps(hash_source, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return detection_model.store_detection_event(event, content_hash)


def validate_report(payload, now=None):
    """ReportDetection 요청 5개 필드를 검증해 저장용 record와 이미지를 돌려준다."""
    if not isinstance(payload, dict):
        raise DetectionValidationError("ReportDetection 요청 객체가 필요합니다.")
    current = now or datetime.now(timezone.utc)
    robot_id = payload.get("robot_id")
    if robot_id not in ROBOT_NAMES:
        raise DetectionValidationError("robot_id는 AMR1 또는 AMR2여야 합니다.")
    image = payload.get("image")
    if not isinstance(image, (bytes, bytearray)) or not image:
        raise DetectionValidationError("image가 비어 있습니다.")
    image = bytes(image)
    maximum = current_app.config["REPORT_IMAGE_MAX_BYTES"]
    if len(image) > maximum:
        raise DetectionValidationError(f"image는 {maximum // 1024}KiB 이하여야 합니다.")
    try:
        extension = event_service._detect_image(image)
    except event_service.EvidenceValidationError as exc:
        raise DetectionValidationError("image는 실제 PNG 또는 JPEG여야 합니다.") from exc
    image_hash = sha256(image).hexdigest()
    event_type = payload.get("event_type")
    if event_type not in EVENT_TYPES:
        raise DetectionValidationError("event_type은 FIRE, LEAK, OBSTACLE 중 하나여야 합니다.")
    record = {
        "event_id": _uuid_v4(payload.get("event_id"), "event_id"),
        "robot_id": robot_id,
        "robot_name": ROBOT_NAMES[robot_id],
        "event_type": event_type,
        "occurred_at": _timestamp(payload.get("detected_at"), "detected_at", current),
        "x": _finite(payload.get("x"), "position.x"),
        "y": _finite(payload.get("y"), "position.y"),
        "frame_id": "map",
        "image_sha256": image_hash,
        "extension": extension,
        "received_at": current.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }
    # [중복 판정 열쇠] message_id 없이 event_id + 내용 해시로 재시도와 잘못된 재사용을 가른다.
    hash_source = {key: record[key] for key in (
        "event_id", "robot_id", "event_type", "occurred_at", "x", "y", "image_sha256")}
    record["content_hash"] = sha256(
        json.dumps(hash_source, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return record, image


def receive_report(payload, now=None):
    """서비스 요청 한 건을 사진 파일 1장 + events 1행으로 저장한다.

    반환 outcome: "accepted"(저장) 또는 "duplicate"(같은 event_id·같은 내용). 값 오류는
    DetectionValidationError, 같은 event_id에 다른 내용은 DetectionMessageConflictError.
    """
    record, image = validate_report(payload, now)
    existing = detection_model.find_report(record["event_id"])
    if existing is not None:
        if existing["content_hash"] == record["content_hash"]:
            return "duplicate", dict(existing)
        raise DetectionMessageConflictError("같은 event_id에 다른 내용이 이미 저장돼 있습니다.")
    # [사건 억제] 감지 노드는 대상이 보이는 동안 몇 초마다 새 event_id로 다시 보고할 수 있다.
    # 같은 로봇·같은 종류 사건이 억제 시간 안에 이미 있으면 저장하지 않고 DUPLICATE로 답한다.
    window = current_app.config.get("REPORT_SUPPRESS_SECONDS") or 0
    if window > 0:
        recent = detection_model.find_recent_report(
            record["robot_id"], record["event_type"], record["occurred_at"], window
        )
        if recent is not None:
            return "duplicate", {
                **dict(recent),
                "suppressed_by": recent["event_id"],
                "detail": f'{window}초 안에 같은 로봇의 같은 종류 사건 {recent["event_id"]}이 이미 저장돼 있어 억제했습니다.',
            }
    image_name = f'evidence-{record["event_id"]}-{record["image_sha256"][:24]}{record["extension"]}'
    directory = Path(current_app.config["EVIDENCE_DIR"])
    image_path = directory / image_name
    created = False
    if not image_path.exists():
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as stream:
                temporary_path = Path(stream.name)
                stream.write(image)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, image_path)
            created = True
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
    try:
        return detection_model.store_report(record, image_name)
    except Exception:
        if created:
            image_path.unlink(missing_ok=True)
        raise


def validate_evidence_chunk(payload, now=None):
    """EvidenceChunk 메타데이터·크기·index를 전체 파일 조립 전에 검증한다."""
    if not isinstance(payload, dict):
        raise DetectionValidationError("EvidenceChunk 객체가 필요합니다.")
    current = now or datetime.now(timezone.utc)
    robot_id = payload.get("robot_id")
    if robot_id not in ROBOT_NAMES:
        raise DetectionValidationError("robot_id는 AMR1 또는 AMR2여야 합니다.")
    media_type = payload.get("media_type")
    if media_type not in MEDIA_TYPES:
        raise DetectionValidationError("media_type은 image/jpeg 또는 image/png여야 합니다.")
    digest = payload.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise DetectionValidationError("sha256은 소문자 64자리 16진수여야 합니다.")
    total_size = payload.get("total_size")
    maximum = current_app.config["EVENT_IMAGE_MAX_BYTES"]
    if isinstance(total_size, bool) or not isinstance(total_size, int) or not 0 < total_size <= maximum:
        raise DetectionValidationError(f"total_size는 1에서 {maximum}바이트 사이여야 합니다.")
    chunk_count = payload.get("chunk_count")
    chunk_index = payload.get("chunk_index")
    if (
        isinstance(chunk_count, bool) or not isinstance(chunk_count, int)
        or not 0 < chunk_count <= total_size
    ):
        raise DetectionValidationError("chunk_count는 1 이상이고 total_size 이하여야 합니다.")
    if (
        isinstance(chunk_index, bool) or not isinstance(chunk_index, int)
        or not 0 <= chunk_index < chunk_count
    ):
        raise DetectionValidationError("chunk_index는 0부터 chunk_count-1 사이여야 합니다.")
    data = payload.get("data")
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_CHUNK_BYTES:
        raise DetectionValidationError("chunk data는 1바이트 이상 64KiB 이하여야 합니다.")
    metadata = {
        "message_id": _uuid_v4(payload.get("message_id"), "message_id"),
        "evidence_id": _uuid_v4(payload.get("evidence_id"), "evidence_id"),
        "event_id": _uuid_v4(payload.get("event_id"), "event_id"),
        "robot_id": robot_id,
        "captured_at": _timestamp(payload.get("captured_at"), "captured_at", current),
        "media_type": media_type,
        "sha256": digest,
        "total_size": total_size,
        "chunk_index": chunk_index,
        "chunk_count": chunk_count,
        "received_at": current.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }
    return metadata, data


def receive_evidence_chunk(payload, now=None):
    """chunk를 누적하고 완성 시 크기·hash·형식을 검사해 증적 한 장으로 확정한다."""
    metadata, data = validate_evidence_chunk(payload, now)
    chunk_hash = sha256(data).hexdigest()
    outcome, missing, chunks = detection_model.store_evidence_chunk(
        metadata, chunk_hash, data
    )
    if outcome != "complete_ready":
        return outcome, {**metadata, "missing_chunks": missing}

    assembled = b"".join(bytes(row["data"]) for row in chunks)
    try:
        if len(assembled) != metadata["total_size"]:
            raise DetectionValidationError("재조립한 증적 크기가 total_size와 다릅니다.")
        if sha256(assembled).hexdigest() != metadata["sha256"]:
            raise DetectionValidationError("재조립한 증적 SHA-256이 선언값과 다릅니다.")
        _, extension, _ = event_service.validate_evidence(BytesIO(assembled))
        if MEDIA_TYPES[metadata["media_type"]] != extension:
            raise DetectionValidationError("media_type과 실제 이미지 형식이 다릅니다.")
    except (DetectionValidationError, event_service.EvidenceValidationError):
        detection_model.reject_evidence(metadata["evidence_id"])
        raise

    image_name = f'evidence-{metadata["evidence_id"]}-{metadata["sha256"][:24]}{extension}'
    directory = Path(current_app.config["EVIDENCE_DIR"])
    image_path = directory / image_name
    created = False
    if not image_path.exists():
        temporary_path = None
        try:
            # [원자적 완성] 모든 chunk 검증 뒤 같은 파일시스템에서 최종 이름으로 교체한다.
            with tempfile.NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as stream:
                temporary_path = Path(stream.name)
                stream.write(assembled)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, image_path)
            created = True
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
    try:
        detection_model.finalize_evidence(metadata["evidence_id"], image_name)
    except Exception:
        if created:
            image_path.unlink(missing_ok=True)
        raise
    return "stored", {**metadata, "missing_chunks": [], "image_path": image_name}
