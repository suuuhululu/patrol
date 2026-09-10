"""2단계 검증: 실제 운영 DB 대신 임시 폴더에서 저장·재시작·제약 조건을 확인한다."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.database import get_db


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.config = {
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "instance/sysmon.sqlite3"),
            "EVIDENCE_DIR": str(Path(self.folder.name) / "instance/evidence"),
        }
        self.app = create_app(self.config)

    def add_event(self, db, event_id="event-1", robot_id="AMR2", status="NEW"):
        db.execute(
            "INSERT INTO events (event_id, robot_id, event_type, occurred_at, status) "
            "VALUES (?, ?, 'FIRE', '2026-09-05T08:00:00Z', ?)",
            (event_id, robot_id, status),
        )

    def test_first_start_creates_empty_tables_and_folders(self):
        self.assertTrue(Path(self.config["DATABASE"]).is_file())
        self.assertTrue(Path(self.config["EVIDENCE_DIR"]).is_dir())
        expected = {"users", "robots", "robot_latest_status", "robot_status_history", "maps", "map_latest", "costmap_latest",
                    "events", "event_evidence", "event_changes", "vehicle_access_logs",
                    "cctv_state_events", "patrol_permit_latest", "patrol_permit_history",
            "keepout_latest", "estop_latest", "estop_history",
                    "dashboard_clear_state",
                    "commands", "patrol_runs", "patrol_visits", "handovers"}
        with self.app.app_context():
            db = get_db()
            actual = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(actual, expected)
            for table in expected:
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            # [사건 저장] ReportDetection 서비스 필드와 관제 처리 상태만 남는다.
            event_columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
            self.assertEqual(event_columns, {
                "event_id", "robot_id", "event_type", "occurred_at", "x", "y", "frame_id",
                "status", "received_at", "content_hash",
            })
            evidence_columns = {row[1] for row in db.execute("PRAGMA table_info(event_evidence)")}
            self.assertEqual(evidence_columns, {"id", "event_id", "image_path", "captured_at", "created_at"})
        self.assertTrue((Path(self.config["DATABASE"]).parent / "maps").is_dir())
        self.assertTrue((Path(self.config["DATABASE"]).parent / "costmaps").is_dir())
        # [3단계 반영] DB 준비 후 기본 페이지는 로그인 사용자에게만 열린다.
        self.assertEqual(self.app.test_client().get("/").status_code, 302)
        self.assertEqual(self.app.test_client().get("/login").status_code, 200)

    def test_restart_preserves_event_and_evidence(self):
        image = Path(self.config["EVIDENCE_DIR"]) / "sample.jpg"
        image.write_bytes(b"test-file-preservation")
        with self.app.app_context():
            db = get_db()
            db.execute("INSERT INTO robots (robot_id, name) VALUES ('AMR2', '로봇 2')")
            self.add_event(db)
            db.execute("INSERT INTO event_evidence (event_id, image_path) VALUES ('event-1', 'sample.jpg')")
            db.commit()
        restarted = create_app(self.config)
        with restarted.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT robot_id, status FROM events").fetchone()[:], ("AMR2", "NEW"))
            self.assertEqual(db.execute("SELECT image_path FROM event_evidence").fetchone()[0], "sample.jpg")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(image.read_bytes(), b"test-file-preservation")

    def test_legacy_vehicle_access_table_keeps_core_topic_history(self):
        legacy_path = Path(self.folder.name) / "legacy/sysmon.sqlite3"
        legacy_path.parent.mkdir(parents=True)
        with sqlite3.connect(legacy_path) as db:
            db.execute(
                """
                CREATE TABLE vehicle_access_logs (
                    access_id TEXT PRIMARY KEY, message_id TEXT UNIQUE, camera_id TEXT,
                    direction TEXT, plate_number TEXT, confidence REAL,
                    detected_at TEXT, image_path TEXT, received_at TEXT
                )
                """
            )
            db.execute(
                """INSERT INTO vehicle_access_logs VALUES
                   ('legacy-1','legacy-message-1','webcam1','ENTRY','12가3456',0.9,
                    '2026-09-06T01:00:00.000Z','old.png','2026-09-06T01:00:01.000Z')"""
            )
        migrated = create_app({**self.config, "DATABASE": str(legacy_path)})
        with migrated.app_context():
            db = get_db()
            columns = {row[1] for row in db.execute("PRAGMA table_info(vehicle_access_logs)")}
            self.assertEqual(columns, {
                "access_id", "message_id", "camera_id", "direction", "detected_at", "received_at",
            })
            row = db.execute("SELECT * FROM vehicle_access_logs").fetchone()
            self.assertEqual((row["access_id"], row["camera_id"], row["direction"]),
                             ("legacy-1", "webcam1", "ENTRY"))

    def test_duplicate_event_invalid_robot_status_and_extra_image_rejected(self):
        with self.app.app_context():
            db = get_db()
            db.execute("INSERT INTO robots (robot_id, name) VALUES ('AMR2', '로봇 2')")
            self.add_event(db)
            db.execute("INSERT INTO event_evidence (event_id, image_path) VALUES ('event-1', 'first.jpg')")
            db.commit()
            for event_id, robot_id, status in [
                ("event-1", "AMR2", "NEW"),
                ("event-3", "missing", "NEW"),
                ("event-4", "AMR2", "INVALID"),
            ]:
                with self.subTest(event_id=event_id, robot_id=robot_id, status=status), \
                        self.assertRaises(sqlite3.IntegrityError):
                    with db:
                        self.add_event(db, event_id, robot_id, status)
            with self.assertRaises(sqlite3.IntegrityError):
                with db:
                    db.execute("INSERT INTO event_evidence (event_id, image_path) VALUES ('event-1', 'second.jpg')")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)

    def test_connections_are_scoped_closed_and_uncommitted_changes_rolled_back(self):
        with self.app.app_context():
            first = get_db()
            self.assertIs(first, get_db())
            first.execute("INSERT INTO robots (robot_id, name) VALUES ('AMR1', '미커밋 로봇')")
        with self.assertRaises(sqlite3.ProgrammingError):
            first.execute("SELECT 1")
        with self.app.app_context():
            second = get_db()
            self.assertIsNot(first, second)
            self.assertEqual(second.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(second.execute("SELECT COUNT(*) FROM robots").fetchone()[0], 0)

    def test_invalid_storage_path_stops_app_start(self):
        blocker = Path(self.folder.name) / "not-a-folder"
        blocker.write_text("file", encoding="utf-8")
        with self.assertLogs(self.app.logger.name, level="ERROR"):
            with self.assertRaises(OSError):
                create_app({**self.config, "DATABASE": str(blocker / "db.sqlite3")})


if __name__ == "__main__":
    unittest.main()
