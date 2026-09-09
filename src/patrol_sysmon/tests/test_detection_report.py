"""ReportDetection 서비스 검증: 필드 5개 요청의 검증·저장·중복·거부와 events 마이그레이션."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import base64
import sqlite3
import tempfile
import unittest

from app import create_app
from app.database import get_db, init_db
from app.models.detection import DetectionMessageConflictError
from app.ros.payloads import report_detection_payload
from app.ros.errors import RosMessageMappingError
from app.services import auth_service, detection_service, event_service


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
EVENT_ID = "10000000-0000-4000-8000-000000000001"
OTHER_ID = "20000000-0000-4000-8000-000000000002"


class DetectionReportTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.config = {
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "instance/sysmon.sqlite3"),
            "EVIDENCE_DIR": str(Path(self.folder.name) / "instance/evidence"),
            "SECRET_KEY": "report-tests-only-key",
        }
        self.app = create_app(self.config)
        self.now = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)

    def payload(self, **changes):
        data = {
            "robot_id": "AMR2", "event_id": EVENT_ID,
            "detected_at": (self.now - timedelta(seconds=1)).isoformat(),
            "x": 2.0, "y": 3.0, "image": PNG,
        }
        data.update(changes)
        return data

    def test_valid_report_saves_one_row_and_one_file(self):
        with self.app.app_context():
            outcome, stored = detection_service.receive_report(self.payload(), self.now)
            self.assertEqual(outcome, "accepted")
            image = Path(self.config["EVIDENCE_DIR"]) / stored["image_path"]
            self.assertEqual(image.read_bytes(), PNG)
            db = get_db()
            row = db.execute("SELECT * FROM events WHERE event_id=?", (EVENT_ID,)).fetchone()
            self.assertEqual((row["robot_id"], row["x"], row["y"], row["frame_id"]), ("AMR2", 2.0, 3.0, "map"))
            self.assertEqual(row["event_type"], "UNKNOWN")
            self.assertIsNone(row["risk_level"])
            self.assertEqual(row["message_id"], EVENT_ID)
            self.assertTrue(row["content_hash"])
            # 사진 조각·조립 표는 쓰지 않는다.
            self.assertEqual(db.execute("SELECT COUNT(*) FROM evidence_chunks").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM evidence_ingestions").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM detection_event_messages").fetchone()[0], 0)

    def test_dashboard_shows_report_without_type_and_risk(self):
        with self.app.app_context():
            detection_service.receive_report(self.payload(), self.now)
            events = event_service.recent_events(50)
            self.assertEqual(len(events), 1)
            view = events[0]
            self.assertEqual(view["event_label"], "미분류")
            self.assertEqual(view["risk_label"], "—")
            self.assertIsNone(view["risk_level"])
            self.assertTrue(view["has_evidence"])
            self.assertEqual(view["evidence_state"], "STORED")
            self.assertEqual(view["location_label"], "map (2.00, 3.00)")
            detail = event_service.event_detail(EVENT_ID)
            self.assertTrue(detail["has_evidence"])

    def test_same_request_again_is_duplicate_without_second_row(self):
        with self.app.app_context():
            detection_service.receive_report(self.payload(), self.now)
            outcome, _ = detection_service.receive_report(self.payload(), self.now + timedelta(seconds=3))
            self.assertEqual(outcome, "duplicate")
            db = get_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM event_evidence").fetchone()[0], 1)
            self.assertEqual(len(list(Path(self.config["EVIDENCE_DIR"]).iterdir())), 1)

    def test_same_event_id_with_different_content_is_rejected(self):
        with self.app.app_context():
            detection_service.receive_report(self.payload(), self.now)
            with self.assertRaises(DetectionMessageConflictError):
                detection_service.receive_report(self.payload(x=9.0), self.now)
            self.assertEqual(get_db().execute("SELECT x FROM events").fetchone()[0], 2.0)

    def test_invalid_fields_are_rejected_without_rows_or_files(self):
        cases = {
            "robot_id": self.payload(robot_id="AMR9"),
            "event_id 형식": self.payload(event_id="det-robot1-1-0001"),
            "5분 미래": self.payload(detected_at=(self.now + timedelta(minutes=6)).isoformat()),
            "좌표 NaN": self.payload(x=float("nan")),
            "빈 이미지": self.payload(image=b""),
            "이미지 형식": self.payload(image=b"not-an-image"),
        }
        with self.app.app_context():
            for label, payload in cases.items():
                with self.subTest(label):
                    with self.assertRaises(detection_service.DetectionValidationError):
                        detection_service.receive_report(payload, self.now)
            self.app.config["REPORT_IMAGE_MAX_BYTES"] = len(PNG) - 1
            with self.assertRaisesRegex(detection_service.DetectionValidationError, "KiB"):
                detection_service.receive_report(self.payload(event_id=OTHER_ID), self.now)
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
            self.assertEqual(list(Path(self.config["EVIDENCE_DIR"]).iterdir()), [])

    def test_ros_request_maps_to_payload(self):
        request = SimpleNamespace(
            robot_id="robot6", event_id=EVENT_ID,
            detected_at=SimpleNamespace(sec=1700000000, nanosec=250000000),
            position=SimpleNamespace(x=2.0, y=3.0, z=0.0), image=list(PNG),
        )
        payload = report_detection_payload(request)
        self.assertEqual(payload["robot_id"], "AMR2")
        self.assertEqual(payload["detected_at"], "2023-11-14T22:13:20.250Z")
        self.assertEqual((payload["x"], payload["y"]), (2.0, 3.0))
        self.assertEqual(payload["image"], PNG)
        with self.assertRaises(RosMessageMappingError):
            report_detection_payload(SimpleNamespace(**{**vars(request), "robot_id": "robot9"}))

    def test_existing_db_with_not_null_risk_is_rebuilt_keeping_rows(self):
        """위험도가 NOT NULL이던 기존 DB를 재구성해도 사건·증거·변경 이력이 그대로 남는다."""
        database = Path(self.folder.name) / "legacy/sysmon.sqlite3"
        database.parent.mkdir(parents=True)
        legacy = sqlite3.connect(database)
        legacy.executescript(
            """
            CREATE TABLE robots (robot_id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT '');
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, role TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT '');
            CREATE TABLE events (
                event_id TEXT PRIMARY KEY NOT NULL, message_id TEXT NOT NULL UNIQUE,
                robot_id TEXT NOT NULL REFERENCES robots(robot_id), event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL, x REAL, y REAL, frame_id TEXT, confidence REAL,
                location_valid INTEGER NOT NULL DEFAULT 1, evidence_id TEXT,
                risk_level TEXT NOT NULL CHECK (risk_level IN ('HIGH', 'MEDIUM', 'LOW')),
                status TEXT NOT NULL DEFAULT 'NEW', received_at TEXT NOT NULL DEFAULT '');
            CREATE TABLE event_evidence (id INTEGER PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE REFERENCES events(event_id), evidence_id TEXT,
                image_path TEXT NOT NULL, captured_at TEXT, created_at TEXT NOT NULL DEFAULT '');
            CREATE TABLE event_changes (id INTEGER PRIMARY KEY,
                event_id TEXT NOT NULL REFERENCES events(event_id),
                user_id INTEGER NOT NULL REFERENCES users(id), previous_status TEXT NOT NULL,
                new_status TEXT NOT NULL, memo TEXT NOT NULL DEFAULT '', changed_at TEXT NOT NULL DEFAULT '');
            INSERT INTO robots VALUES ('AMR1', '로봇 1', '');
            INSERT INTO users (id, username, password_hash, role) VALUES (1, 'op', 'x', 'OPERATOR');
            INSERT INTO events (event_id, message_id, robot_id, event_type, occurred_at, x, y, frame_id,
                risk_level, status, received_at)
                VALUES ('old-1', 'msg-1', 'AMR1', 'FIRE', '2026-09-01T00:00:00.000Z', 1, 1, 'map',
                        'HIGH', 'REVIEWING', '2026-09-01T00:00:01.000Z');
            INSERT INTO event_evidence (event_id, image_path) VALUES ('old-1', 'evidence-old.png');
            INSERT INTO event_changes (event_id, user_id, previous_status, new_status)
                VALUES ('old-1', 1, 'NEW', 'REVIEWING');
            """
        )
        legacy.commit()
        legacy.close()
        app = create_app({**self.config, "DATABASE": str(database),
                          "EVIDENCE_DIR": str(database.parent / "evidence")})
        with app.app_context():
            db = get_db()
            info = {row[1]: row for row in db.execute("PRAGMA table_info(events)")}
            self.assertEqual(info["risk_level"][3], 0)          # NOT NULL 해제
            self.assertIn("content_hash", info)
            old = db.execute("SELECT * FROM events WHERE event_id='old-1'").fetchone()
            self.assertEqual((old["risk_level"], old["status"], old["event_type"]), ("HIGH", "REVIEWING", "FIRE"))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM event_evidence").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM event_changes").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            # 재구성한 표에 서비스 사건이 들어가고, 두 번째 시작에서는 다시 재구성하지 않는다.
            detection_service.receive_report(self.payload(robot_id="AMR1"), self.now)
            init_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 2)
            indexes = {row[1] for row in db.execute("PRAGMA index_list(events)")}
            self.assertTrue({"idx_events_occurred", "idx_events_robot_time"} <= indexes)


if __name__ == "__main__":
    unittest.main()
