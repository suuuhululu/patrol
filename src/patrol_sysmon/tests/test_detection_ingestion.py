"""18단계 검증: DetectionEvent와 chunk 증적의 독립 도착·결합을 확인한다."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import base64
import tempfile
import unittest

from app import create_app
from app.database import get_db
from app.models.detection import DetectionMessageConflictError, EvidenceRejectedError
from app.services import auth_service, detection_service


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
IDS = {
    "event": "10000000-0000-4000-8000-000000000001",
    "evidence": "20000000-0000-4000-8000-000000000002",
    "event_message": "30000000-0000-4000-8000-000000000003",
    "chunk0": "40000000-0000-4000-8000-000000000004",
    "chunk1": "50000000-0000-4000-8000-000000000005",
}


class DetectionIngestionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "instance/sysmon.sqlite3"),
            "EVIDENCE_DIR": str(Path(self.folder.name) / "instance/evidence"),
            "SECRET_KEY": "detection-tests-only-key",
        })
        self.now = datetime.now(timezone.utc)

    def event(self, **changes):
        payload = {
            "message_id": IDS["event_message"], "event_id": IDS["event"],
            "robot_id": "AMR1", "event_type": "LEAK", "confidence": 0.91,
            "risk_level": "MEDIUM", "x": 1.2, "y": 3.4, "frame_id": "map",
            "location_valid": True,
            "detected_at": (self.now - timedelta(seconds=1)).isoformat(),
            "evidence_id": IDS["evidence"],
        }
        payload.update(changes)
        return payload

    def chunk(self, index, **changes):
        split = len(PNG) // 2
        parts = (PNG[:split], PNG[split:])
        payload = {
            "message_id": IDS[f"chunk{index}"], "evidence_id": IDS["evidence"],
            "event_id": IDS["event"], "robot_id": "AMR1",
            "captured_at": (self.now - timedelta(seconds=1)).isoformat(),
            "media_type": "image/png", "sha256": sha256(PNG).hexdigest(),
            "total_size": len(PNG), "chunk_index": index, "chunk_count": 2,
            "data": parts[index],
        }
        payload.update(changes)
        return payload

    def test_evidence_can_arrive_first_out_of_order_and_attach_when_event_arrives(self):
        with self.app.app_context():
            outcome, result = detection_service.receive_evidence_chunk(self.chunk(1), self.now)
            self.assertEqual(outcome, "incomplete")
            self.assertEqual(result["missing_chunks"], [0])
            outcome, result = detection_service.receive_evidence_chunk(self.chunk(0), self.now)
            self.assertEqual(outcome, "stored")
            self.assertEqual(result["missing_chunks"], [])
            self.assertIsNone(get_db().execute("SELECT event_id FROM event_evidence").fetchone())

            outcome, stored = detection_service.receive_detection(self.event(), self.now)
            self.assertEqual(outcome, "accepted")
            self.assertEqual(stored["event_type"], "LEAK")
            link = get_db().execute("SELECT * FROM event_evidence").fetchone()
            self.assertEqual((link["event_id"], link["evidence_id"]), (IDS["event"], IDS["evidence"]))
            image = Path(self.app.config["EVIDENCE_DIR"]) / link["image_path"]
            self.assertEqual(image.read_bytes(), PNG)
            self.assertTrue(all(
                row[0] is None for row in get_db().execute(
                    "SELECT data FROM evidence_chunks ORDER BY chunk_index"
                )
            ))

    def test_event_without_location_or_evidence_is_saved_without_fake_coordinates(self):
        payload = self.event(
            evidence_id="", location_valid=False, x=float("nan"), y=float("nan"),
            event_type="OBSTACLE", risk_level="LOW",
        )
        with self.app.app_context():
            outcome, stored = detection_service.receive_detection(payload, self.now)
            self.assertEqual(outcome, "accepted")
            self.assertEqual((stored["x"], stored["y"], stored["location_valid"]), (None, None, 0))
            self.assertIsNone(stored["evidence_id"])

    def test_out_of_scope_event_types_are_rejected_and_not_stored(self):
        """제품 범위는 화재·누수·장애물이다. 계약 enum의 나머지 둘은 저장하지 않는다."""
        with self.app.app_context():
            for event_type in ("LIGHTING", "FACILITY_DAMAGE"):
                with self.assertRaises(detection_service.DetectionValidationError):
                    detection_service.receive_detection(
                        self.event(event_type=event_type), self.now
                    )
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0], 0
            )

    def test_detection_duplicate_conflict_and_supplemental_message(self):
        with self.app.app_context():
            self.assertEqual(detection_service.receive_detection(self.event(), self.now)[0], "accepted")
            self.assertEqual(detection_service.receive_detection(self.event(), self.now)[0], "duplicate")
            with self.assertRaises(DetectionMessageConflictError):
                detection_service.receive_detection(self.event(confidence=0.2), self.now)
            supplement = self.event(
                message_id="60000000-0000-4000-8000-000000000006",
                confidence=0.95,
            )
            outcome, stored = detection_service.receive_detection(supplement, self.now)
            self.assertEqual(outcome, "updated")
            self.assertEqual(stored["confidence"], 0.95)
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM detection_event_messages").fetchone()[0], 2)

    def test_invalid_final_hash_marks_evidence_rejected_and_drops_chunk_bytes(self):
        bad_hash = "0" * 64
        with self.app.app_context():
            self.assertEqual(
                detection_service.receive_evidence_chunk(self.chunk(0, sha256=bad_hash), self.now)[0],
                "incomplete",
            )
            with self.assertRaises(detection_service.DetectionValidationError):
                detection_service.receive_evidence_chunk(self.chunk(1, sha256=bad_hash), self.now)
            status = get_db().execute(
                "SELECT status FROM evidence_ingestions WHERE evidence_id=?", (IDS["evidence"],)
            ).fetchone()[0]
            self.assertEqual(status, "REJECTED")
            self.assertTrue(all(
                row[0] is None for row in get_db().execute("SELECT data FROM evidence_chunks")
            ))
            with self.assertRaises(EvidenceRejectedError):
                detection_service.receive_evidence_chunk(self.chunk(0, sha256=bad_hash), self.now)

    def test_incomplete_evidence_becomes_delayed_then_missing_by_age(self):
        """증적 조립이 끝나지 않으면 경과 시간으로 지연·누락을 구분해 보여준다."""
        from datetime import timedelta

        from app.services import event_service

        with self.app.app_context():
            detection_service.receive_detection(self.event(), self.now)
            detection_service.receive_evidence_chunk(self.chunk(0), self.now)
            row = dict(get_db().execute(
                """
                SELECT e.*, evidence.image_path, ingestion.status AS evidence_status,
                       ingestion.updated_at AS evidence_updated_at
                  FROM events AS e
                  LEFT JOIN event_evidence AS evidence ON evidence.event_id = e.event_id
                  LEFT JOIN evidence_ingestions AS ingestion ON ingestion.event_id = e.event_id
                """
            ).fetchone())
            self.assertEqual(row["evidence_status"], "INCOMPLETE")
            self.assertEqual(event_service.evidence_state(row, self.now), "INCOMPLETE")
            self.assertEqual(
                event_service.evidence_state(row, self.now + timedelta(seconds=40)), "DELAYED"
            )
            self.assertEqual(
                event_service.evidence_state(row, self.now + timedelta(minutes=10)), "MISSING"
            )
            # 나머지 조각이 도착하면 저장 완료로 바뀐다.
            detection_service.receive_evidence_chunk(self.chunk(1), self.now)
            done = dict(get_db().execute(
                "SELECT e.*, ingestion.status AS evidence_status,"
                " ingestion.updated_at AS evidence_updated_at"
                " FROM events AS e LEFT JOIN evidence_ingestions AS ingestion"
                " ON ingestion.event_id = e.event_id"
            ).fetchone())
            self.assertEqual(
                event_service.evidence_state(done, self.now + timedelta(minutes=10)), "STORED"
            )

    def test_completed_event_is_visible_through_existing_protected_event_api(self):
        with self.app.app_context():
            detection_service.receive_detection(self.event(), self.now)
            detection_service.receive_evidence_chunk(self.chunk(0), self.now)
            detection_service.receive_evidence_chunk(self.chunk(1), self.now)
            user_id = auth_service.create_user("detection-viewer", "Test-pass-123", "VIEWER")
        client = self.app.test_client()
        self.assertEqual(client.get("/api/events").status_code, 302)
        with client.session_transaction() as session:
            session["user_id"] = user_id
        events = client.get("/api/events").get_json()["events"]
        self.assertEqual(events[0]["event_label"], "누수")
        self.assertTrue(events[0]["has_evidence"])
        evidence = client.get(events[0]["evidence_url"])
        self.assertEqual((evidence.status_code, evidence.mimetype), (200, "image/png"))
        evidence.close()


if __name__ == "__main__":
    unittest.main()
