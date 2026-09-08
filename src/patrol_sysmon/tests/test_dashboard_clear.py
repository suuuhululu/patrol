"""최근 목록 표시 초기화가 DB 이력을 유지하고 사용자별로 적용되는지 확인한다."""

from pathlib import Path
import tempfile
import unittest

from app import create_app
from app.database import get_db
from app.services import auth_service


class DashboardClearTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name) / "instance"
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(root / "sysmon.sqlite3"),
            "EVIDENCE_DIR": str(root / "evidence"),
            "SECRET_KEY": "dashboard-clear-tests-only-key",
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            self.user1 = auth_service.create_user("viewer1", "Test-pass-123", "VIEWER")
            self.user2 = auth_service.create_user("viewer2", "Test-pass-456", "VIEWER")
            db = get_db()
            db.execute("INSERT INTO robots(robot_id,name) VALUES ('AMR1','로봇 1')")
            db.execute(
                """INSERT INTO events
                   (event_id,message_id,robot_id,event_type,occurred_at,risk_level,status,received_at)
                   VALUES ('event-old','event-message-old','AMR1','FIRE',
                           '2026-09-06T01:00:00.000Z','HIGH','NEW','2026-09-06T01:00:01.000Z')"""
            )
            db.execute(
                """INSERT INTO vehicle_access_logs
                   (access_id,message_id,camera_id,direction,detected_at,received_at)
                   VALUES ('access-old','access-message-old','webcam1','ENTRY',
                           '2026-09-06T02:00:00.000Z','2026-09-06T02:00:01.000Z')"""
            )
            db.commit()

    def login(self, user_id, csrf="clear-csrf"):
        with self.client.session_transaction() as session:
            session["user_id"] = user_id
            session["csrf_token"] = csrf
        return {"X-CSRF-Token": csrf}

    def test_each_log_is_hidden_per_user_without_deleting_history(self):
        headers = self.login(self.user1)
        self.assertEqual(self.client.get("/api/events").get_json()["count"], 1)
        self.assertEqual(self.client.get("/api/vehicle-access").get_json()["count"], 1)
        self.assertEqual(self.client.post("/api/dashboard/clear/events").status_code, 400)
        self.assertEqual(
            self.client.post("/api/dashboard/clear/events", headers=headers).status_code, 200
        )
        self.assertEqual(self.client.get("/api/events").get_json()["count"], 0)
        self.assertEqual(self.client.get("/api/vehicle-access").get_json()["count"], 1)
        # [이력 보존] 대시보드에서 숨긴 뒤에도 통합 이력과 원본 행은 그대로 남는다.
        self.assertEqual(self.client.get("/api/history").get_json()["total"], 2)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM vehicle_access_logs").fetchone()[0], 1)

        self.assertEqual(
            self.client.post("/api/dashboard/clear/vehicle-access", headers=headers).status_code, 200
        )
        self.assertEqual(self.client.get("/api/vehicle-access").get_json()["count"], 0)
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn("표시 초기화", page)
        self.assertIn("통합 이력에 보존", page)

        # [사용자 분리] 다른 사용자는 자신의 기준 시각이 없으므로 같은 기존 기록을 본다.
        self.login(self.user2)
        self.assertEqual(self.client.get("/api/events").get_json()["count"], 1)
        self.assertEqual(self.client.get("/api/vehicle-access").get_json()["count"], 1)

    def test_newly_received_rows_appear_after_clear(self):
        headers = self.login(self.user1)
        self.client.post("/api/dashboard/clear/events", headers=headers)
        self.client.post("/api/dashboard/clear/vehicle-access", headers=headers)
        with self.app.app_context():
            db = get_db()
            db.execute(
                """INSERT INTO events
                   (event_id,message_id,robot_id,event_type,occurred_at,risk_level,status,received_at)
                   VALUES ('event-new','event-message-new','AMR1','LEAK',
                           '9999-01-01T00:00:00.000Z','MEDIUM','NEW','9999-01-01T00:00:00.000Z')"""
            )
            db.execute(
                """INSERT INTO vehicle_access_logs
                   (access_id,message_id,camera_id,direction,detected_at,received_at)
                   VALUES ('access-new','access-message-new','webcam2','EXIT',
                           '9999-01-01T00:00:00.000Z','9999-01-01T00:00:00.000Z')"""
            )
            db.commit()
        self.assertEqual(self.client.get("/api/events").get_json()["events"][0]["event_id"],
                         "event-new")
        self.assertEqual(
            self.client.get("/api/vehicle-access").get_json()["accesses"][0]["access_id"],
            "access-new",
        )


if __name__ == "__main__":
    unittest.main()
