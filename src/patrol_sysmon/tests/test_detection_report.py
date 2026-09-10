"""ReportDetection 서비스 검증: 요청 6개 필드의 검증·저장·중복·억제·거부와 events 마이그레이션."""

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
from app.services import detection_service, event_service


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
EVENT_ID = "10000000-0000-4000-8000-000000000001"
OTHER_ID = "20000000-0000-4000-8000-000000000002"
EVENT_COLUMNS = {
    "event_id", "robot_id", "event_type", "occurred_at", "x", "y", "frame_id",
    "status", "received_at", "content_hash", "image_path", "captured_at",
}


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
            "x": 2.0, "y": 3.0, "image": PNG, "event_type": "LEAK",
        }
        data.update(changes)
        return data

    def test_events_table_has_only_service_columns(self):
        """서비스가 주는 값·처리 상태·사진 경로만 있고 옛 토픽·HTTP 칸은 없다."""
        with self.app.app_context():
            db = get_db()
            columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
            self.assertEqual(columns, EVENT_COLUMNS)
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertFalse(tables & {
                "event_evidence", "detection_event_messages", "evidence_ingestions", "evidence_chunks",
            })

    def test_valid_report_saves_one_row_and_one_file(self):
        with self.app.app_context():
            outcome, stored = detection_service.receive_report(self.payload(), self.now)
            self.assertEqual(outcome, "accepted")
            image = Path(self.config["EVIDENCE_DIR"]) / stored["image_path"]
            self.assertEqual(image.read_bytes(), PNG)
            db = get_db()
            row = db.execute("SELECT * FROM events WHERE event_id=?", (EVENT_ID,)).fetchone()
            self.assertEqual((row["robot_id"], row["x"], row["y"], row["frame_id"]), ("AMR2", 2.0, 3.0, "map"))
            self.assertEqual(row["event_type"], "LEAK")
            self.assertEqual(row["image_path"], stored["image_path"])
            self.assertEqual(row["captured_at"], row["occurred_at"])
            self.assertTrue(row["content_hash"])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)

    def test_dashboard_shows_report_type_and_photo(self):
        with self.app.app_context():
            detection_service.receive_report(self.payload(), self.now)
            events = event_service.recent_events(50)
            self.assertEqual(len(events), 1)
            view = events[0]
            self.assertEqual(view["event_label"], "누수")
            self.assertTrue(view["has_evidence"])
            self.assertEqual(view["location_label"], "map (2.00, 3.00)")
            self.assertNotIn("risk_level", view)
            self.assertNotIn("message_id", view)
            detail = event_service.event_detail(EVENT_ID)
            self.assertTrue(detail["has_evidence"])

    def test_same_request_again_is_duplicate_without_second_row(self):
        with self.app.app_context():
            detection_service.receive_report(self.payload(), self.now)
            outcome, _ = detection_service.receive_report(self.payload(), self.now + timedelta(seconds=3))
            self.assertEqual(outcome, "duplicate")
            db = get_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
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
            "종류 없음": self.payload(event_type="UNKNOWN"),
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

    def test_repeated_report_of_same_kind_is_suppressed_for_a_window(self):
        """감지 노드가 3초마다 새 event_id로 다시 보고해도 60초 안에는 사진 한 장만 남는다."""
        with self.app.app_context():
            first, _ = detection_service.receive_report(self.payload(), self.now)
            self.assertEqual(first, "accepted")
            later = self.now + timedelta(seconds=3)
            outcome, stored = detection_service.receive_report(
                self.payload(event_id=OTHER_ID, detected_at=later.isoformat(), x=2.1), later
            )
            self.assertEqual(outcome, "duplicate")
            self.assertEqual(stored["suppressed_by"], EVENT_ID)
            self.assertIn("60초", stored["detail"])
            db = get_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
            self.assertEqual(len(list(Path(self.config["EVIDENCE_DIR"]).iterdir())), 1)
            outcome, _ = detection_service.receive_report(
                self.payload(event_id=OTHER_ID, event_type="FIRE", detected_at=later.isoformat()), later
            )
            self.assertEqual(outcome, "accepted")
            after = self.now + timedelta(seconds=61)
            outcome, _ = detection_service.receive_report(
                self.payload(event_id="30000000-0000-4000-8000-000000000003",
                             detected_at=after.isoformat()), after
            )
            self.assertEqual(outcome, "accepted")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 3)
            self.app.config["REPORT_SUPPRESS_SECONDS"] = 0
            outcome, _ = detection_service.receive_report(
                self.payload(event_id="40000000-0000-4000-8000-000000000004",
                             detected_at=(after + timedelta(seconds=2)).isoformat()), after
            )
            self.assertEqual(outcome, "accepted")

    def test_ros_request_maps_to_payload(self):
        request = SimpleNamespace(
            robot_id="robot6", event_id=EVENT_ID,
            detected_at=SimpleNamespace(sec=1700000000, nanosec=250000000),
            position=SimpleNamespace(x=2.0, y=3.0, z=0.0), image=list(PNG), event_type=2,
        )
        payload = report_detection_payload(request)
        self.assertEqual(payload["robot_id"], "AMR2")
        self.assertEqual(payload["detected_at"], "2023-11-14T22:13:20.250Z")
        self.assertEqual((payload["x"], payload["y"]), (2.0, 3.0))
        self.assertEqual(payload["image"], PNG)
        self.assertEqual(payload["event_type"], "LEAK")
        with self.assertRaises(RosMessageMappingError):
            report_detection_payload(SimpleNamespace(**{**vars(request), "event_type": 0}))
        with self.assertRaises(RosMessageMappingError):
            report_detection_payload(SimpleNamespace(**{**vars(request), "robot_id": "robot9"}))

    def test_legacy_db_is_rebuilt_to_slim_events_keeping_rows(self):
        """토픽·HTTP 시절 표(message_id·risk_level·event_evidence 등)를 가진 DB를 재구성해도
        사건·사진 경로·처리 이력이 그대로 남고 옛 표는 사라진다."""
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
            CREATE TABLE detection_event_messages (message_id TEXT PRIMARY KEY NOT NULL,
                event_id TEXT NOT NULL REFERENCES events(event_id), content_hash TEXT NOT NULL,
                received_at TEXT NOT NULL);
            CREATE TABLE evidence_ingestions (evidence_id TEXT PRIMARY KEY NOT NULL, event_id TEXT NOT NULL,
                status TEXT NOT NULL);
            CREATE TABLE evidence_chunks (evidence_id TEXT NOT NULL REFERENCES evidence_ingestions(evidence_id),
                chunk_index INTEGER NOT NULL, message_id TEXT NOT NULL UNIQUE, data BLOB,
                PRIMARY KEY (evidence_id, chunk_index));
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
            INSERT INTO event_evidence (event_id, image_path, captured_at)
                VALUES ('old-1', 'evidence-old.png', '2026-09-01T00:00:00.500Z');
            INSERT INTO detection_event_messages VALUES ('msg-1', 'old-1', 'h', '2026-09-01T00:00:01.000Z');
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
            columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
            self.assertEqual(columns, EVENT_COLUMNS)
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertFalse(tables & {
                "event_evidence", "detection_event_messages", "evidence_ingestions", "evidence_chunks",
            })
            old = db.execute("SELECT * FROM events WHERE event_id='old-1'").fetchone()
            self.assertEqual((old["status"], old["event_type"], old["image_path"], old["captured_at"]),
                             ("REVIEWING", "FIRE", "evidence-old.png", "2026-09-01T00:00:00.500Z"))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM event_changes").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            detection_service.receive_report(self.payload(robot_id="AMR1"), self.now)
            init_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 2)
            indexes = {row[1] for row in db.execute("PRAGMA index_list(events)")}
            self.assertTrue({"idx_events_occurred", "idx_events_robot_time"} <= indexes)


if __name__ == "__main__":
    unittest.main()
