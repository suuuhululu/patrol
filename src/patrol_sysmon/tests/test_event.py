"""이상 이벤트의 인증·종류·검증·원자적 저장을 확인한다."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from app import create_app
from app.database import get_db
from app.services import auth_service
from app.services.map_service import occupancy_to_png


class EventTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.config = {
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "instance/sysmon.sqlite3"),
            "EVIDENCE_DIR": str(Path(self.folder.name) / "instance/evidence"),
            "SECRET_KEY": "event-tests-only-key",
            "ROBOT_API_KEY": "event-device-test-key",
            "EVENT_IMAGE_MAX_BYTES": 1024,
        }
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.png = occupancy_to_png([0, 100, -1, 0], 2, 2)
        with self.app.app_context():
            self.user_id = auth_service.create_user("viewer", "Test-pass-123", "VIEWER")
            self.operator_id = auth_service.create_user("operator", "Test-pass-456", "OPERATOR")

    def metadata(self, event_id="fire-event-001", message_id="fire-message-001", **changes):
        happened = datetime.now(timezone.utc) - timedelta(seconds=2)
        payload = {
            "event_id": event_id,
            "message_id": message_id,
            "robot_id": "AMR1",
            "event_type": "FIRE",
            "occurred_at": happened.isoformat(),
            "captured_at": (happened + timedelta(milliseconds=100)).isoformat(),
            "x": 12.5,
            "y": 8.25,
            "frame_id": "map",
            "risk_level": "HIGH",
        }
        payload.update(changes)
        return payload

    def send_event(self, metadata=None, image=None, token="event-device-test-key"):
        headers = {"X-Robot-Token": token} if token is not None else {}
        data = {"metadata": json.dumps(metadata or self.metadata())}
        data["image"] = (BytesIO(self.png if image is None else image), "evidence.bin")
        return self.client.post("/api/events", data=data, headers=headers,
                                content_type="multipart/form-data")

    def login_session(self, user_id=None, csrf_token=None):
        with self.client.session_transaction() as session:
            session["user_id"] = user_id or self.user_id
            if csrf_token:
                session["csrf_token"] = csrf_token

    def test_event_api_requires_token_and_multipart(self):
        self.assertEqual(self.send_event(token=None).status_code, 401)
        self.assertEqual(self.send_event(token="wrong").status_code, 401)
        self.assertEqual(
            self.client.post("/api/events", json=self.metadata(),
                             headers={"X-Robot-Token": "event-device-test-key"}).status_code,
            415,
        )
        disabled = create_app({
            **self.config,
            "DATABASE": str(Path(self.folder.name) / "disabled/db.sqlite3"),
            "EVIDENCE_DIR": str(Path(self.folder.name) / "disabled/evidence"),
            "ROBOT_API_KEY": None,
        }).test_client()
        self.assertEqual(disabled.post("/api/events").status_code, 503)

    def test_valid_fire_event_saves_metadata_and_one_evidence_file(self):
        response = self.send_event()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["result"], "accepted")
        evidence_files = list(Path(self.config["EVIDENCE_DIR"]).glob("event-*.png"))
        self.assertEqual(len(evidence_files), 1)
        self.assertEqual(evidence_files[0].read_bytes(), self.png)
        with self.app.app_context():
            db = get_db()
            event = db.execute("SELECT * FROM events").fetchone()
            evidence = db.execute("SELECT * FROM event_evidence").fetchone()
            self.assertEqual((event["robot_id"], event["event_type"], event["risk_level"], event["status"]),
                             ("AMR1", "FIRE", "HIGH", "NEW"))
            self.assertEqual((event["x"], event["y"], event["frame_id"]), (12.5, 8.25, "map"))
            self.assertEqual(evidence["event_id"], event["event_id"])
            self.assertEqual(evidence["image_path"], evidence_files[0].name)
            self.assertEqual(db.execute("SELECT name FROM robots WHERE robot_id='AMR1'").fetchone()[0], "로봇 1")

    def test_leak_and_obstacle_events_use_common_event_flow(self):
        leak = self.metadata(
            event_id="leak-event-001", message_id="leak-message-001",
            event_type="LEAK", risk_level="MEDIUM",
        )
        obstacle = self.metadata(
            event_id="obstacle-event-001", message_id="obstacle-message-001",
            event_type="OBSTACLE", risk_level="LOW",
        )
        self.assertEqual(self.send_event(leak).status_code, 201)
        self.assertEqual(self.send_event(obstacle).status_code, 201)
        self.login_session()
        labels = {item["event_label"] for item in self.client.get("/api/events").get_json()["events"]}
        self.assertEqual(labels, {"누수", "장애물"})

    def test_exact_retry_is_duplicate_but_changed_event_conflicts(self):
        metadata = self.metadata()
        self.assertEqual(self.send_event(metadata).status_code, 201)
        duplicate = self.send_event(metadata)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.get_json()["result"], "duplicate")
        self.assertEqual(self.send_event({**metadata, "risk_level": "LOW"}).status_code, 409)
        same_message = self.metadata(event_id="fire-event-002", message_id=metadata["message_id"])
        self.assertEqual(self.send_event(same_message).status_code, 409)
        self.assertEqual(len(list(Path(self.config["EVIDENCE_DIR"]).iterdir())), 1)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)

    def test_invalid_metadata_does_not_leave_rows_or_files(self):
        invalid = [
            self.metadata(event_type="SMOKE"),
            self.metadata(robot_id="AMR3"),
            self.metadata(risk_level="CRITICAL"),
            self.metadata(x=True),
            self.metadata(frame_id="잘못된 좌표계"),
            self.metadata(occurred_at="2026-09-06 12:00:00"),
            self.metadata(captured_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()),
        ]
        for metadata in invalid:
            with self.subTest(metadata=metadata):
                self.assertEqual(self.send_event(metadata).status_code, 400)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
        self.assertEqual(list(Path(self.config["EVIDENCE_DIR"]).iterdir()), [])

    def test_invalid_missing_and_large_images_are_rejected(self):
        metadata_text = json.dumps(self.metadata())
        missing = self.client.post(
            "/api/events", data={"metadata": metadata_text},
            headers={"X-Robot-Token": "event-device-test-key"},
            content_type="multipart/form-data",
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(self.send_event(image=b"not-an-image").status_code, 400)
        large = b"\x89PNG\r\n\x1a\n" + b"x" * 1100
        self.assertEqual(self.send_event(image=large).status_code, 400)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
        self.assertEqual(list(Path(self.config["EVIDENCE_DIR"]).iterdir()), [])

    def test_evidence_image_requires_login_and_blocks_paths_outside_folder(self):
        self.send_event()
        event_url = "/api/events/fire-event-001/evidence"
        self.assertEqual(self.client.get(event_url).location, "/login")
        self.login_session()
        image = self.client.get(event_url)
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.mimetype, "image/png")
        self.assertEqual(image.data, self.png)
        image.close()
        outside = Path(self.folder.name) / "outside.png"
        outside.write_bytes(self.png)
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE event_evidence SET image_path='../outside.png'")
            db.commit()
        self.assertEqual(self.client.get(event_url).status_code, 404)

    def test_invalid_metadata_json_is_rejected(self):
        response = self.client.post(
            "/api/events",
            data={"metadata": "{broken", "image": (BytesIO(self.png), "evidence.png")},
            headers={"X-Robot-Token": "event-device-test-key"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_metadata")

    def test_event_list_detail_and_dashboard_use_saved_values(self):
        self.send_event()
        self.assertEqual(self.client.get("/api/events").location, "/login")
        self.assertEqual(self.client.get("/api/events/fire-event-001").location, "/login")
        self.login_session()
        listing = self.client.get("/api/events").get_json()
        self.assertEqual(listing["count"], 1)
        event = listing["events"][0]
        self.assertEqual(
            (event["event_label"], event["robot_id"], event["risk_label"], event["status_label"]),
            ("화재", "AMR1", "상", "신규"),
        )
        self.assertEqual(event["location_label"], "map (12.50, 8.25)")
        self.assertTrue(event["evidence_url"].endswith("/api/events/fire-event-001/evidence"))
        detail = self.client.get("/api/events/fire-event-001").get_json()["event"]
        self.assertEqual(detail["changes"], [])
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("fire-event-001", page.get_data(as_text=True))
        self.assertIn("상세 보기", page.get_data(as_text=True))
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE events SET x=NULL, y=NULL, frame_id=NULL")
            db.commit()
        self.assertEqual(self.client.get("/api/events").get_json()["events"][0]["location_label"],
                         "좌표 없음")

    def test_operator_records_sequential_status_changes_without_robot_command(self):
        self.send_event()
        csrf = "event-status-csrf"
        self.login_session(csrf_token=csrf)
        forbidden = self.client.post(
            "/api/events/fire-event-001/status",
            json={"status": "REVIEWING", "memo": "확인"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(forbidden.status_code, 403)

        self.login_session(self.operator_id, csrf)
        skipped = self.client.post(
            "/api/events/fire-event-001/status",
            json={"status": "WORK_REQUESTED"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(skipped.status_code, 409)
        for status, memo in [
            ("REVIEWING", "현장 영상 확인"),
            ("WORK_REQUESTED", "외부 안전 담당자에게 전달"),
            ("RESOLVED", "현장 조치 확인"),
        ]:
            response = self.client.post(
                "/api/events/fire-event-001/status",
                json={"status": status, "memo": memo},
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["status"], status)
        detail = self.client.get("/api/events/fire-event-001").get_json()["event"]
        self.assertEqual(detail["status"], "RESOLVED")
        self.assertEqual([change["new_status"] for change in detail["changes"]],
                         ["REVIEWING", "WORK_REQUESTED", "RESOLVED"])
        self.assertEqual(detail["changes"][1]["username"], "operator")
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM event_changes").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM commands").fetchone()[0], 0)

    def test_status_update_validates_csrf_request_memo_and_event(self):
        self.send_event()
        csrf = "event-status-csrf"
        self.login_session(self.operator_id, csrf)
        self.assertEqual(
            self.client.post("/api/events/fire-event-001/status",
                             json={"status": "REVIEWING"}).status_code,
            400,
        )
        headers = {"X-CSRF-Token": csrf}
        self.assertEqual(
            self.client.post("/api/events/fire-event-001/status", data="text",
                             headers=headers, content_type="text/plain").status_code,
            400,
        )
        self.assertEqual(
            self.client.post("/api/events/fire-event-001/status",
                             json={"status": "REVIEWING", "memo": "x" * 501},
                             headers=headers).status_code,
            400,
        )
        self.assertEqual(
            self.client.post("/api/events/missing/status",
                             json={"status": "REVIEWING"}, headers=headers).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
