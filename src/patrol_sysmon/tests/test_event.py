"""이상 이벤트 목록·상세·증거 이미지 조회와 관제 처리 상태 변경을 확인한다.

사건은 ReportDetection 서비스 경로(detection_service.receive_report)로 만든다. HTTP 수신은 없다.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from app import create_app
from app.database import get_db
from app.services import auth_service, detection_service
from app.services.map_service import occupancy_to_png


EVENT_ID = "fa000000-0000-4000-8000-000000000001"


class EventTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.config = {
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "instance/sysmon.sqlite3"),
            "EVIDENCE_DIR": str(Path(self.folder.name) / "instance/evidence"),
            "SECRET_KEY": "event-tests-only-key",
        }
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.png = occupancy_to_png([0, 100, -1, 0], 2, 2)
        with self.app.app_context():
            self.user_id = auth_service.create_user("viewer", "Test-pass-123", "VIEWER")
            self.operator_id = auth_service.create_user("operator", "Test-pass-456", "OPERATOR")

    def report(self, **changes):
        """서비스 요청과 같은 payload로 사건 한 건을 저장한다."""
        payload = {
            "robot_id": "AMR1", "event_id": EVENT_ID, "event_type": "FIRE",
            "detected_at": (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat(),
            "x": 12.5, "y": 8.25, "image": self.png,
        }
        payload.update(changes)
        with self.app.app_context():
            return detection_service.receive_report(payload)

    def login_session(self, user_id=None, csrf_token=None):
        with self.client.session_transaction() as session:
            session["user_id"] = user_id or self.user_id
            if csrf_token:
                session["csrf_token"] = csrf_token

    def test_http_event_ingestion_is_gone(self):
        """사건은 서비스로만 받는다. 옛 HTTP 입구는 없다."""
        response = self.client.post("/api/events", data=b"x")
        # CSRF 검사(400) 또는 메서드 없음(405) 둘 중 하나로 막힌다. 저장은 되지 않는다.
        self.assertIn(response.status_code, (400, 405))
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)

    def test_event_list_detail_and_dashboard_use_saved_values(self):
        self.report()
        self.assertEqual(self.client.get("/api/events").location, "/login")
        self.assertEqual(self.client.get(f"/api/events/{EVENT_ID}").location, "/login")
        self.login_session()
        listing = self.client.get("/api/events").get_json()
        self.assertEqual(listing["count"], 1)
        event = listing["events"][0]
        self.assertEqual(
            (event["event_label"], event["robot_id"], event["status_label"]),
            ("화재", "AMR1", "신규"),
        )
        self.assertEqual(event["location_label"], "map (12.50, 8.25)")
        self.assertNotIn("risk_level", event)
        self.assertNotIn("message_id", event)
        self.assertTrue(event["evidence_url"].endswith(f"/api/events/{EVENT_ID}/evidence"))
        detail = self.client.get(f"/api/events/{EVENT_ID}").get_json()["event"]
        self.assertEqual(detail["changes"], [])
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn(EVENT_ID, page.get_data(as_text=True))
        self.assertIn("상세 보기", page.get_data(as_text=True))
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE events SET x=NULL, y=NULL, frame_id=NULL")
            db.commit()
        self.assertEqual(self.client.get("/api/events").get_json()["events"][0]["location_label"],
                         "좌표 없음")

    def test_evidence_image_requires_login_and_blocks_paths_outside_folder(self):
        self.report()
        event_url = f"/api/events/{EVENT_ID}/evidence"
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
            db.execute("UPDATE events SET image_path='../outside.png'")
            db.commit()
        self.assertEqual(self.client.get(event_url).status_code, 404)
        self.assertEqual(self.client.get("/api/events/missing/evidence").status_code, 404)

    def test_operator_records_sequential_status_changes_without_robot_command(self):
        self.report()
        csrf = "event-status-csrf"
        self.login_session(csrf_token=csrf)
        forbidden = self.client.post(
            f"/api/events/{EVENT_ID}/status",
            json={"status": "REVIEWING", "memo": "확인"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(forbidden.status_code, 403)

        self.login_session(self.operator_id, csrf)
        skipped = self.client.post(
            f"/api/events/{EVENT_ID}/status",
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
                f"/api/events/{EVENT_ID}/status",
                json={"status": status, "memo": memo},
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["status"], status)
        detail = self.client.get(f"/api/events/{EVENT_ID}").get_json()["event"]
        self.assertEqual(detail["status"], "RESOLVED")
        self.assertEqual([change["new_status"] for change in detail["changes"]],
                         ["REVIEWING", "WORK_REQUESTED", "RESOLVED"])
        self.assertEqual(detail["changes"][1]["username"], "operator")
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM event_changes").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM commands").fetchone()[0], 0)

    def test_status_update_validates_csrf_request_memo_and_event(self):
        self.report()
        csrf = "event-status-csrf"
        self.login_session(self.operator_id, csrf)
        self.assertEqual(
            self.client.post(f"/api/events/{EVENT_ID}/status",
                             json={"status": "REVIEWING"}).status_code,
            400,
        )
        headers = {"X-CSRF-Token": csrf}
        self.assertEqual(
            self.client.post(f"/api/events/{EVENT_ID}/status", data="text",
                             headers=headers, content_type="text/plain").status_code,
            400,
        )
        self.assertEqual(
            self.client.post(f"/api/events/{EVENT_ID}/status",
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
