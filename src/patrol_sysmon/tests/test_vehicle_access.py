"""차량 입출차 내역 API·대시보드·중복 저장을 확인한다."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from app import create_app
from app.database import get_db
from app.services import auth_service


class VehicleAccessTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name) / "instance"
        self.config = {
            "TESTING": True,
            "DATABASE": str(root / "sysmon.sqlite3"),
            "EVIDENCE_DIR": str(root / "evidence"),
            "SECRET_KEY": "vehicle-tests-only-key",
            "ROBOT_API_KEY": "vehicle-device-test-key",
        }
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        with self.app.app_context():
            self.user_id = auth_service.create_user("viewer", "Test-pass-123", "VIEWER")

    def payload(self, **changes):
        payload = {
            "access_id": "access-001", "message_id": "access-message-001",
            "camera_id": "webcam1", "direction": "ENTRY",
            "detected_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        }
        payload.update(changes)
        return payload

    def send(self, payload=None, token="vehicle-device-test-key"):
        headers = {"X-Robot-Token": token} if token is not None else {}
        return self.client.post(
            "/api/vehicle-access", json=payload or self.payload(), headers=headers,
        )

    def login(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def test_entry_is_saved_listed_and_shown_on_dashboard(self):
        self.assertEqual(self.send().status_code, 201)
        with self.app.app_context():
            row = get_db().execute("SELECT * FROM vehicle_access_logs").fetchone()
            self.assertEqual((row["camera_id"], row["direction"]), ("webcam1", "ENTRY"))
            self.assertEqual(set(row.keys()), {
                "access_id", "message_id", "camera_id", "direction", "detected_at", "received_at",
            })
        self.assertEqual(self.client.get("/api/vehicle-access").location, "/login")
        self.login()
        item = self.client.get("/api/vehicle-access").get_json()["accesses"][0]
        self.assertEqual((item["direction_label"], item["camera_name"]),
                         ("입차", "고정 웹캠 1"))
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn("차량 입출차 로그", page)
        self.assertIn("고정 웹캠 1", page)
        self.assertNotIn("차량번호", page)
        self.assertNotIn("인식률", page)
        self.assertNotIn("차량 이미지", page)

    def test_exit_is_allowed(self):
        response = self.send(self.payload(
            access_id="access-002", message_id="access-message-002",
            camera_id="webcam2", direction="EXIT",
        ))
        self.assertEqual(response.status_code, 201)
        self.login()
        item = self.client.get("/api/vehicle-access").get_json()["accesses"][0]
        self.assertEqual((item["direction_label"], item["camera_name"]),
                         ("출차", "고정 웹캠 2"))

    def test_token_validation_duplicate_and_conflict(self):
        self.assertEqual(self.send(token=None).status_code, 401)
        payload = self.payload()
        self.assertEqual(self.send(payload).status_code, 201)
        self.assertEqual(self.send(payload).status_code, 200)
        self.assertEqual(self.send({**payload, "direction": "EXIT"}).status_code, 409)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM vehicle_access_logs").fetchone()[0], 1)

    def test_invalid_topic_fields_leave_no_record(self):
        invalid = [
            self.payload(camera_id="amr1"), self.payload(direction="PARKED"),
            self.payload(detected_at="2026-09-06 12:00:00"), {},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(
                    "/api/vehicle-access", json=payload,
                    headers={"X-Robot-Token": "vehicle-device-test-key"},
                ).status_code, 400)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM vehicle_access_logs").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
