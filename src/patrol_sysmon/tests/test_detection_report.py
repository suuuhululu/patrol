"""ReportDetection 서비스 검증: 요청 필드의 검증·저장·중복·거부와 events 마이그레이션."""

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
            self.assertTrue(row["content_hash"])
            evidence = db.execute("SELECT * FROM event_evidence WHERE event_id=?", (EVENT_ID,)).fetchone()
            self.assertEqual(evidence["image_path"], stored["image_path"])
            self.assertTrue(stored["image_path"].startswith(f"evidence-{EVENT_ID}-"))
            # 사진 시각 필드가 따로 없으므로 감지 시각을 그대로 쓴다.
            self.assertEqual(evidence["captured_at"], row["occurred_at"])

    def test_dashboard_shows_report_type_location_and_evidence(self):
        with self.app.app_context():
            detection_service.receive_report(self.payload(), self.now)
            events = event_service.recent_events(50)
            self.assertEqual(len(events), 1)
            view = events[0]
            self.assertEqual(view["event_label"], "누수")
            self.assertTrue(view["has_evidence"])
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
            # 다른 종류는 억제하지 않는다.
            outcome, _ = detection_service.receive_report(
                self.payload(event_id=OTHER_ID, event_type="FIRE", detected_at=later.isoformat()), later
            )
            self.assertEqual(outcome, "accepted")
            # 창이 지나면 같은 종류도 새 사건이다.
            after = self.now + timedelta(seconds=61)
            outcome, _ = detection_service.receive_report(
                self.payload(event_id="30000000-0000-4000-8000-000000000003",
                             detected_at=after.isoformat()), after
            )
            self.assertEqual(outcome, "accepted")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 3)
            # 0이면 끈다.
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

    def test_existing_db_with_topic_columns_is_rebuilt_keeping_rows(self):
        """DetectionEvent 토픽 시절 열·표가 남은 기존 DB를 재구성해도 사건·사진·처리 이력이 그대로 남는다."""
        database = Path(self.folder.name) / "legacy/sysmon.sqlite3"
        database.parent.mkdir(parents=True)
        legacy = sqlite3.connect(database)
        legacy.executescript(
            f"""
            CREATE TABLE robots (robot_id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT '');
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, role TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT '');
            CREATE TABLE events (
                event_id TEXT PRIMARY KEY NOT NULL, message_id TEXT NOT NULL UNIQUE,
                robot_id TEXT NOT NULL REFERENCES robots(robot_id),
                event_type TEXT NOT NULL DEFAULT 'UNKNOWN', occurred_at TEXT NOT NULL,
                x REAL, y REAL, frame_id TEXT, confidence REAL,
                location_valid INTEGER NOT NULL DEFAULT 1, evidence_id TEXT,
                risk_level TEXT CHECK (risk_level IS NULL OR risk_level IN ('HIGH', 'MEDIUM', 'LOW')),
                status TEXT NOT NULL DEFAULT 'NEW', received_at TEXT NOT NULL DEFAULT '',
                content_hash TEXT);
            CREATE TABLE event_evidence (id INTEGER PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE REFERENCES events(event_id), evidence_id TEXT,
                image_path TEXT NOT NULL, captured_at TEXT, created_at TEXT NOT NULL DEFAULT '');
            CREATE TABLE event_changes (id INTEGER PRIMARY KEY,
                event_id TEXT NOT NULL REFERENCES events(event_id),
                user_id INTEGER NOT NULL REFERENCES users(id), previous_status TEXT NOT NULL,
                new_status TEXT NOT NULL, memo TEXT NOT NULL DEFAULT '', changed_at TEXT NOT NULL DEFAULT '');
            CREATE TABLE detection_event_messages (message_id TEXT PRIMARY KEY NOT NULL,
                event_id TEXT NOT NULL REFERENCES events(event_id), content_hash TEXT NOT NULL,
                received_at TEXT NOT NULL);
            CREATE TABLE evidence_ingestions (evidence_id TEXT PRIMARY KEY NOT NULL,
                event_id TEXT NOT NULL, robot_id TEXT NOT NULL, captured_at TEXT NOT NULL,
                media_type TEXT NOT NULL, sha256 TEXT NOT NULL, total_size INTEGER NOT NULL,
                chunk_count INTEGER NOT NULL, status TEXT NOT NULL, image_path TEXT,
                received_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE evidence_chunks (
                evidence_id TEXT NOT NULL REFERENCES evidence_ingestions(evidence_id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL, message_id TEXT NOT NULL UNIQUE,
                content_hash TEXT NOT NULL, data BLOB, received_at TEXT NOT NULL,
                PRIMARY KEY (evidence_id, chunk_index));
            CREATE UNIQUE INDEX idx_events_evidence_id ON events(evidence_id) WHERE evidence_id IS NOT NULL;
            CREATE UNIQUE INDEX idx_event_evidence_evidence_id
                ON event_evidence(evidence_id) WHERE evidence_id IS NOT NULL;
            CREATE INDEX idx_detection_messages_event ON detection_event_messages(event_id);
            CREATE INDEX idx_evidence_ingestions_event ON evidence_ingestions(event_id);
            INSERT INTO robots VALUES ('AMR1', '로봇 1', ''), ('AMR2', '로봇 2', '');
            INSERT INTO users (id, username, password_hash, role) VALUES (1, 'op', 'x', 'OPERATOR');
            INSERT INTO events (event_id, message_id, robot_id, event_type, occurred_at, x, y, frame_id,
                risk_level, status, received_at)
                VALUES ('old-1', 'msg-1', 'AMR1', 'FIRE', '2026-09-01T00:00:00.000Z', 1, 1, 'map',
                        'HIGH', 'REVIEWING', '2026-09-01T00:00:01.000Z');
            INSERT INTO events (event_id, message_id, robot_id, event_type, occurred_at, x, y, frame_id,
                confidence, location_valid, evidence_id, risk_level, status, received_at, content_hash)
                VALUES ('{OTHER_ID}', '{OTHER_ID}', 'AMR2', 'LEAK', '2026-09-02T00:00:00.000Z',
                        NULL, NULL, 'map', 0.9, 0, '{EVENT_ID}', 'LOW', 'NEW',
                        '2026-09-02T00:00:01.000Z', 'hash-2');
            INSERT INTO event_evidence (id, event_id, evidence_id, image_path, captured_at, created_at)
                VALUES (7, 'old-1', NULL, 'event-old.png', '2026-09-01T00:00:00.100Z', 'created-1'),
                       (8, '{OTHER_ID}', '{EVENT_ID}', 'evidence-old.png', '2026-09-02T00:00:00.000Z',
                        'created-2');
            INSERT INTO event_changes (event_id, user_id, previous_status, new_status, memo)
                VALUES ('old-1', 1, 'NEW', 'REVIEWING', '확인');
            INSERT INTO detection_event_messages VALUES ('{OTHER_ID}', '{OTHER_ID}', 'hash', 'at');
            INSERT INTO evidence_ingestions VALUES ('{EVENT_ID}', '{OTHER_ID}', 'AMR2', 'at',
                'image/png', 'sha', 1, 1, 'STORED', 'evidence-old.png', 'at', 'at');
            INSERT INTO evidence_chunks VALUES ('{EVENT_ID}', 0, 'chunk-message', 'hash', NULL, 'at');
            """
        )
        legacy.commit()
        legacy.close()
        app = create_app({**self.config, "DATABASE": str(database),
                          "EVIDENCE_DIR": str(database.parent / "evidence")})
        with app.app_context():
            db = get_db()
            columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
            self.assertEqual(columns, {
                "event_id", "robot_id", "event_type", "occurred_at", "x", "y", "frame_id",
                "status", "received_at", "content_hash",
            })
            columns = {row[1] for row in db.execute("PRAGMA table_info(event_evidence)")}
            self.assertEqual(columns, {"id", "event_id", "image_path", "captured_at", "created_at"})
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertFalse(
                {"detection_event_messages", "evidence_ingestions", "evidence_chunks"} & tables
            )
            # 사건·사진·처리 이력 행은 값 그대로 남는다.
            events = [tuple(row) for row in db.execute(
                "SELECT event_id, robot_id, event_type, occurred_at, x, y, frame_id, status, "
                "received_at, content_hash FROM events ORDER BY occurred_at"
            )]
            self.assertEqual(events, [
                ("old-1", "AMR1", "FIRE", "2026-09-01T00:00:00.000Z", 1.0, 1.0, "map",
                 "REVIEWING", "2026-09-01T00:00:01.000Z", None),
                (OTHER_ID, "AMR2", "LEAK", "2026-09-02T00:00:00.000Z", None, None, "map",
                 "NEW", "2026-09-02T00:00:01.000Z", "hash-2"),
            ])
            evidence = [tuple(row) for row in db.execute(
                "SELECT id, event_id, image_path, captured_at, created_at FROM event_evidence ORDER BY id"
            )]
            self.assertEqual(evidence, [
                (7, "old-1", "event-old.png", "2026-09-01T00:00:00.100Z", "created-1"),
                (8, OTHER_ID, "evidence-old.png", "2026-09-02T00:00:00.000Z", "created-2"),
            ])
            change = db.execute(
                "SELECT event_id, user_id, previous_status, new_status, memo FROM event_changes"
            ).fetchall()
            self.assertEqual([tuple(row) for row in change], [("old-1", 1, "NEW", "REVIEWING", "확인")])
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            # 임시 표 이름이 참조로 남거나 옛 증적 식별자 인덱스가 남지 않는다.
            leftovers = [
                row[0] for row in db.execute("SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL")
                if any(word in row[1] for word in ("events_new", "_legacy", "evidence_id"))
            ]
            self.assertEqual(leftovers, [])
            self.assertIn(
                "REFERENCES events(event_id)",
                db.execute("SELECT sql FROM sqlite_master WHERE name='event_changes'").fetchone()[0],
            )
            # 재구성한 표에 서비스 사건이 들어가고, 두 번째 시작에서는 다시 재구성하지 않는다.
            detection_service.receive_report(self.payload(robot_id="AMR1"), self.now)
            init_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM event_evidence").fetchone()[0], 3)
            indexes = {row[1] for row in db.execute("PRAGMA index_list(events)")}
            self.assertTrue({"idx_events_occurred", "idx_events_robot_time"} <= indexes)

if __name__ == "__main__":
    unittest.main()
