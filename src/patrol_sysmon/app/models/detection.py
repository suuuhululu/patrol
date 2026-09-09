"""ROS DetectionEvent와 EvidenceChunk의 SQLite 저장·재전송 판정."""

from ..database import get_db


EVIDENCE_META_COLUMNS = (
    "evidence_id", "event_id", "robot_id", "captured_at", "media_type",
    "sha256", "total_size", "chunk_count",
)


class DetectionMessageConflictError(Exception):
    """같은 메시지·사건·증적 식별자가 서로 다른 내용을 가리키는 경우."""


class EvidenceRejectedError(Exception):
    """이미 무결성 검증에 실패해 거부 처리된 evidence_id가 다시 들어온 경우."""


def _attach_evidence(db, event_id, evidence_id):
    """이벤트와 완료 증적의 계약 ID가 맞을 때 한 장의 증적 경로를 연결한다."""
    if not evidence_id:
        return False
    evidence = db.execute(
        "SELECT * FROM evidence_ingestions WHERE evidence_id = ? AND status = 'STORED'",
        (evidence_id,),
    ).fetchone()
    if evidence is None:
        return False
    event = db.execute(
        "SELECT robot_id, evidence_id FROM events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    if event is None:
        # [독립 도착] 완료 증적을 보존하고 DetectionEvent가 나중에 연결하게 한다.
        return False
    if (
        event["evidence_id"] != evidence_id
        or event["robot_id"] != evidence["robot_id"]
        or evidence["event_id"] != event_id
    ):
        raise DetectionMessageConflictError("이벤트와 증적 식별 관계가 일치하지 않습니다.")
    linked = db.execute(
        "SELECT evidence_id, image_path FROM event_evidence WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    if linked is not None:
        if linked["evidence_id"] == evidence_id and linked["image_path"] == evidence["image_path"]:
            return False
        raise DetectionMessageConflictError("사건에 다른 증적이 이미 연결되어 있습니다.")
    db.execute(
        """
        INSERT INTO event_evidence (event_id, evidence_id, image_path, captured_at)
        VALUES (?, ?, ?, ?)
        """,
        (event_id, evidence_id, evidence["image_path"], evidence["captured_at"]),
    )
    return True


def store_detection_event(record, content_hash):
    """DetectionEvent 재전송을 판정하고 사건 최신값·증적 연결을 원자적으로 저장한다."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        receipt = db.execute(
            "SELECT event_id, content_hash FROM detection_event_messages WHERE message_id = ?",
            (record["message_id"],),
        ).fetchone()
        if receipt is not None:
            if receipt["event_id"] != record["event_id"] or receipt["content_hash"] != content_hash:
                raise DetectionMessageConflictError("DetectionEvent message_id가 충돌합니다.")
            stored = db.execute(
                "SELECT * FROM events WHERE event_id = ?", (record["event_id"],)
            ).fetchone()
            db.commit()
            return "duplicate", dict(stored)

        message_owner = db.execute(
            "SELECT event_id FROM events WHERE message_id = ?", (record["message_id"],)
        ).fetchone()
        if message_owner is not None and message_owner["event_id"] != record["event_id"]:
            raise DetectionMessageConflictError("DetectionEvent message_id가 다른 사건에 사용됐습니다.")

        existing = db.execute(
            "SELECT * FROM events WHERE event_id = ?", (record["event_id"],)
        ).fetchone()
        if existing is not None:
            if existing["robot_id"] != record["robot_id"]:
                raise DetectionMessageConflictError("같은 event_id의 robot_id가 다릅니다.")
            previous_evidence = existing["evidence_id"]
            incoming_evidence = record["evidence_id"]
            if previous_evidence and incoming_evidence and previous_evidence != incoming_evidence:
                raise DetectionMessageConflictError("같은 사건의 evidence_id가 변경됐습니다.")
            evidence_id = previous_evidence or incoming_evidence
            db.execute(
                """
                UPDATE events
                   SET message_id = ?, event_type = ?, occurred_at = ?, x = ?, y = ?,
                       frame_id = ?, confidence = ?, location_valid = ?, evidence_id = ?,
                       risk_level = ?, received_at = ?
                 WHERE event_id = ?
                """,
                (
                    record["message_id"], record["event_type"], record["occurred_at"],
                    record["x"], record["y"], record["frame_id"], record["confidence"],
                    record["location_valid"], evidence_id, record["risk_level"],
                    record["received_at"], record["event_id"],
                ),
            )
            outcome = "updated"
        else:
            db.execute(
                "INSERT OR IGNORE INTO robots (robot_id, name) VALUES (?, ?)",
                (record["robot_id"], record["robot_name"]),
            )
            db.execute(
                """
                INSERT INTO events
                    (event_id, message_id, robot_id, event_type, occurred_at,
                     x, y, frame_id, confidence, location_valid, evidence_id,
                     risk_level, status, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'NEW', ?)
                """,
                tuple(record[column] for column in (
                    "event_id", "message_id", "robot_id", "event_type", "occurred_at",
                    "x", "y", "frame_id", "confidence", "location_valid", "evidence_id",
                    "risk_level", "received_at",
                )),
            )
            outcome = "accepted"
        db.execute(
            """
            INSERT INTO detection_event_messages (message_id, event_id, content_hash, received_at)
            VALUES (?, ?, ?, ?)
            """,
            (record["message_id"], record["event_id"], content_hash, record["received_at"]),
        )
        _attach_evidence(db, record["event_id"], record["evidence_id"] or (
            existing["evidence_id"] if existing is not None else None
        ))
        stored = db.execute(
            "SELECT * FROM events WHERE event_id = ?", (record["event_id"],)
        ).fetchone()
        db.commit()
        return outcome, dict(stored)
    except Exception:
        db.rollback()
        raise


def store_evidence_chunk(metadata, content_hash, data):
    """chunk 한 개를 저장하고 현재 누락 index 또는 완성용 조각을 반환한다."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        assembly = db.execute(
            "SELECT * FROM evidence_ingestions WHERE evidence_id = ?",
            (metadata["evidence_id"],),
        ).fetchone()
        if assembly is not None:
            if any(assembly[column] != metadata[column] for column in EVIDENCE_META_COLUMNS):
                raise DetectionMessageConflictError("같은 evidence_id의 메타데이터가 다릅니다.")
            if assembly["status"] == "REJECTED":
                raise EvidenceRejectedError("이미 거부된 evidence_id입니다.")
        else:
            event = db.execute(
                "SELECT robot_id, evidence_id FROM events WHERE event_id = ?",
                (metadata["event_id"],),
            ).fetchone()
            if event is not None and (
                event["robot_id"] != metadata["robot_id"]
                or event["evidence_id"] != metadata["evidence_id"]
            ):
                raise DetectionMessageConflictError("사건이 기대하는 증적과 다릅니다.")
            db.execute(
                """
                INSERT INTO evidence_ingestions
                    (evidence_id, event_id, robot_id, captured_at, media_type,
                     sha256, total_size, chunk_count, status, received_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'INCOMPLETE', ?, ?)
                """,
                tuple(metadata[column] for column in EVIDENCE_META_COLUMNS)
                + (metadata["received_at"], metadata["received_at"]),
            )

        existing_message = db.execute(
            "SELECT * FROM evidence_chunks WHERE message_id = ?",
            (metadata["message_id"],),
        ).fetchone()
        if existing_message is not None:
            if (
                existing_message["evidence_id"] != metadata["evidence_id"]
                or existing_message["chunk_index"] != metadata["chunk_index"]
                or existing_message["content_hash"] != content_hash
            ):
                raise DetectionMessageConflictError("EvidenceChunk message_id가 충돌합니다.")
            missing = _missing_chunks(db, metadata["evidence_id"], metadata["chunk_count"])
            db.commit()
            return "duplicate", missing, None

        same_index = db.execute(
            "SELECT * FROM evidence_chunks WHERE evidence_id = ? AND chunk_index = ?",
            (metadata["evidence_id"], metadata["chunk_index"]),
        ).fetchone()
        if same_index is not None:
            if same_index["content_hash"] != content_hash:
                raise DetectionMessageConflictError("같은 chunk_index의 내용이 다릅니다.")
            missing = _missing_chunks(db, metadata["evidence_id"], metadata["chunk_count"])
            db.commit()
            return "duplicate", missing, None

        if assembly is not None and assembly["status"] == "STORED":
            raise DetectionMessageConflictError("완료된 증적에 알 수 없는 chunk가 도착했습니다.")
        db.execute(
            """
            INSERT INTO evidence_chunks
                (evidence_id, chunk_index, message_id, content_hash, data, received_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                metadata["evidence_id"], metadata["chunk_index"], metadata["message_id"],
                content_hash, data, metadata["received_at"],
            ),
        )
        db.execute(
            "UPDATE evidence_ingestions SET updated_at = ? WHERE evidence_id = ?",
            (metadata["received_at"], metadata["evidence_id"]),
        )
        missing = _missing_chunks(db, metadata["evidence_id"], metadata["chunk_count"])
        chunks = None
        if not missing:
            chunks = db.execute(
                "SELECT chunk_index, data FROM evidence_chunks WHERE evidence_id = ? ORDER BY chunk_index",
                (metadata["evidence_id"],),
            ).fetchall()
        db.commit()
        return ("complete_ready" if chunks is not None else "incomplete"), missing, chunks
    except Exception:
        db.rollback()
        raise


def _missing_chunks(db, evidence_id, chunk_count):
    present = {
        row[0] for row in db.execute(
            "SELECT chunk_index FROM evidence_chunks WHERE evidence_id = ?", (evidence_id,)
        )
    }
    return [index for index in range(chunk_count) if index not in present]


def find_report(event_id):
    """ReportDetection 중복 판정용으로 같은 event_id의 사건과 내용 해시를 읽는다."""
    return get_db().execute(
        "SELECT event_id, robot_id, occurred_at, x, y, content_hash FROM events WHERE event_id = ?",
        (event_id,),
    ).fetchone()


def store_report(record, image_name):
    """서비스로 받은 사건을 events 1행과 event_evidence 1행으로 한 transaction에 저장한다.

    message_id·종류·위험도가 없는 사건이다. message_id에는 event_id를 넣고 event_type은
    UNKNOWN, risk_level은 NULL로 둔다. 같은 event_id 판정은 서비스 계층이 먼저 했지만
    동시 호출을 대비해 transaction 안에서 한 번 더 확인한다.
    """
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT event_id, robot_id, occurred_at, x, y, content_hash FROM events WHERE event_id = ?",
            (record["event_id"],),
        ).fetchone()
        if existing is not None:
            if existing["content_hash"] != record["content_hash"]:
                raise DetectionMessageConflictError("같은 event_id에 다른 내용이 이미 저장돼 있습니다.")
            db.commit()
            return "duplicate", dict(existing)
        db.execute(
            "INSERT OR IGNORE INTO robots (robot_id, name) VALUES (?, ?)",
            (record["robot_id"], record["robot_name"]),
        )
        db.execute(
            """
            INSERT INTO events
                (event_id, message_id, robot_id, event_type, occurred_at, x, y, frame_id,
                 confidence, location_valid, evidence_id, risk_level, status, received_at,
                 content_hash)
            VALUES (?, ?, ?, 'UNKNOWN', ?, ?, ?, ?, NULL, 1, NULL, NULL, 'NEW', ?, ?)
            """,
            (
                record["event_id"], record["event_id"], record["robot_id"], record["occurred_at"],
                record["x"], record["y"], record["frame_id"], record["received_at"],
                record["content_hash"],
            ),
        )
        db.execute(
            """
            INSERT INTO event_evidence (event_id, evidence_id, image_path, captured_at)
            VALUES (?, NULL, ?, ?)
            """,
            (record["event_id"], image_name, record["occurred_at"]),
        )
        stored = db.execute(
            "SELECT * FROM events WHERE event_id = ?", (record["event_id"],)
        ).fetchone()
        db.commit()
        return "accepted", {**dict(stored), "image_path": image_name}
    except Exception:
        db.rollback()
        raise


def finalize_evidence(evidence_id, image_path):
    """완성 파일 경로를 확정하고 chunk BLOB을 비운 뒤 가능한 사건에 연결한다."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        assembly = db.execute(
            "SELECT * FROM evidence_ingestions WHERE evidence_id = ?", (evidence_id,)
        ).fetchone()
        if assembly is None or assembly["status"] != "INCOMPLETE":
            raise DetectionMessageConflictError("완료할 증적 상태가 올바르지 않습니다.")
        db.execute(
            "UPDATE evidence_ingestions SET status='STORED', image_path=? WHERE evidence_id=?",
            (image_path, evidence_id),
        )
        # 완료 파일이 있으므로 DB에는 재전송 판정용 hash·message_id만 남긴다.
        db.execute("UPDATE evidence_chunks SET data=NULL WHERE evidence_id=?", (evidence_id,))
        _attach_evidence(db, assembly["event_id"], evidence_id)
        db.commit()
    except Exception:
        db.rollback()
        raise


def reject_evidence(evidence_id):
    """전체 무결성 실패를 영속 표시하고 임시 chunk 바이트를 제거한다."""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "UPDATE evidence_ingestions SET status='REJECTED', image_path=NULL WHERE evidence_id=?",
            (evidence_id,),
        )
        db.execute("UPDATE evidence_chunks SET data=NULL WHERE evidence_id=?", (evidence_id,))
        db.commit()
    except Exception:
        db.rollback()
        raise
