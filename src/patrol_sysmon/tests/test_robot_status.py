"""5단계 검증: 로봇 상태 인증·검증·중복·순서·저장·표시를 확인한다."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from app import create_app
from app.database import get_db
from app.services import auth_service, robot_service


class RobotStatusTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.config = {
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "instance/db.sqlite3"),
            "EVIDENCE_DIR": str(Path(self.folder.name) / "instance/evidence"),
            "SECRET_KEY": "robot-tests-only-key",
            "ROBOT_API_KEY": "robot-device-test-key",
            "ROBOT_OFFLINE_AFTER_SECONDS": 15,
            "ROBOT_STATUS_HISTORY_MIN_INTERVAL_SECONDS": 1.0,
            "ROBOT_STATUS_HISTORY_RETENTION_DAYS": 7,
        }
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        with self.app.app_context():
            self.user_id = auth_service.create_user("viewer", "Test-pass-123", "VIEWER")

    def login_session(self, client=None):
        client = client or self.client
        with client.session_transaction() as session:
            session["user_id"] = self.user_id

    def payload(self, message_id="amr1-status-0001", robot_id="AMR1", seconds_ago=1, **changes):
        data = {
            "message_id": message_id,
            "robot_id": robot_id,
            "battery": 82.5,
            "x": 12.4,
            "y": 8.7,
            "frame_id": "map",
            "mission_status": "PATROLLING",
            "connection_status": "ONLINE",
            "observed_at": (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat(),
        }
        data.update(changes)
        return data

    def send(self, payload, token="robot-device-test-key"):
        headers = {"X-Robot-Token": token} if token is not None else {}
        return self.client.post("/api/robots/status", json=payload, headers=headers)

    def test_device_token_is_required_and_unconfigured_api_is_closed(self):
        self.assertEqual(self.send(self.payload(), token=None).status_code, 401)
        self.assertEqual(self.send(self.payload(), token="wrong").status_code, 401)
        disabled = create_app({**self.config, "DATABASE": str(Path(self.folder.name) / "disabled.sqlite3"),
                               "ROBOT_API_KEY": None}).test_client()
        self.assertEqual(disabled.post("/api/robots/status", json=self.payload()).status_code, 503)

    def test_valid_status_saves_latest_and_history(self):
        response = self.send(self.payload())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["result"], "accepted")
        with self.app.app_context():
            db = get_db()
            latest = db.execute("SELECT * FROM robot_latest_status WHERE robot_id='AMR1'").fetchone()
            self.assertEqual(latest["battery"], 82.5)
            self.assertEqual(latest["mission_status"], "PATROLLING")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM robot_status_history").fetchone()[0], 1)

    def test_newer_status_updates_latest_and_keeps_both_history_rows(self):
        old = self.payload(seconds_ago=4)
        new = self.payload(message_id="amr1-status-0002", seconds_ago=1, battery=39,
                           mission_status="RETURNING")
        self.assertEqual(self.send(old).status_code, 201)
        self.assertEqual(self.send(new).status_code, 201)
        with self.app.app_context():
            db = get_db()
            latest = db.execute("SELECT * FROM robot_latest_status WHERE robot_id='AMR1'").fetchone()
            self.assertEqual(latest["message_id"], "amr1-status-0002")
            self.assertEqual(latest["battery"], 39)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM robot_status_history").fetchone()[0], 2)

    def test_exact_retry_is_idempotent_but_changed_payload_conflicts(self):
        payload = self.payload()
        self.assertEqual(self.send(payload).status_code, 201)
        duplicate = self.send(payload)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.get_json()["result"], "duplicate")
        self.assertEqual(self.send({**payload, "battery": 10}).status_code, 409)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM robot_status_history").fetchone()[0], 1)

    def test_older_message_cannot_overwrite_latest(self):
        first = self.payload(seconds_ago=1)
        stale = self.payload(message_id="amr1-status-old", seconds_ago=5, battery=5)
        self.assertEqual(self.send(first).status_code, 201)
        response = self.send(stale)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "stale_status")
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT battery FROM robot_latest_status").fetchone()[0], 82.5)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM robot_status_history").fetchone()[0], 1)

    def test_invalid_fields_are_rejected_without_partial_rows(self):
        invalid_payloads = [
            self.payload(robot_id="AMR3"),
            self.payload(battery=101),
            self.payload(battery=True),
            self.payload(x=float("nan")),
            self.payload(frame_id="map space"),
            self.payload(mission_status="FLYING"),
            self.payload(connection_status="CONNECTED"),
            self.payload(observed_at="2026-09-06 10:00:00"),
            self.payload(observed_at=(datetime.now(timezone.utc) + timedelta(minutes=6)).isoformat()),
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.assertEqual(self.send(payload).status_code, 400)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM robots").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM robot_status_history").fetchone()[0], 0)

    def test_dashboard_api_requires_login_and_page_uses_saved_values(self):
        self.assertEqual(self.client.get("/api/robots/status").location, "/login")
        self.assertEqual(self.send(self.payload()).status_code, 201)
        self.login_session()
        response = self.client.get("/api/robots/status")
        self.assertEqual(response.status_code, 200)
        robots = {item["id"]: item for item in response.get_json()["robots"]}
        self.assertEqual(robots["AMR1"]["connection_status"], "ONLINE")
        self.assertEqual(robots["AMR1"]["location_label"], "map (12.40, 8.70)")
        self.assertFalse(robots["AMR2"]["has_status"])
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn("82", page)
        self.assertIn("순찰 중", page)
        self.assertIn("map (12.40, 8.70)", page)

    def test_invalid_pose_keeps_status_and_shows_last_valid_position(self):
        """위치를 잃어도 배터리·임무는 계속 받고 화면은 마지막 유효 위치를 구분해 보여준다."""
        with self.app.app_context():
            robot_service.receive_status(self.payload(
                message_id="pose-valid-1", x=12.0, y=8.0, seconds_ago=20,
            ))
            robot_service.receive_status(self.payload(
                message_id="pose-invalid-1", pose_valid=False, x=None, y=None,
                seconds_ago=5,
                last_valid_pose_at=(
                    datetime.now(timezone.utc) - timedelta(seconds=20)
                ).isoformat(),
            ))
            row = get_db().execute(
                "SELECT battery, x, y, pose_valid FROM robot_latest_status WHERE robot_id='AMR1'"
            ).fetchone()
            cards = robot_service.dashboard_robots()
        self.assertEqual((row["x"], row["y"], row["pose_valid"]), (None, None, 0))
        self.assertIsNotNone(row["battery"])
        card = next(item for item in cards if item["id"] == "AMR1")
        self.assertFalse(card["pose_valid"])
        self.assertEqual((card["last_valid_x"], card["last_valid_y"]), (12.0, 8.0))
        self.assertIn("마지막 유효", card["location_label"])
        self.assertEqual(card["mission_label"], "순찰 중")

    def test_connection_becomes_offline_when_updates_stop(self):
        now = datetime.now(timezone.utc)
        with self.app.app_context():
            robot_service.receive_status(self.payload(seconds_ago=1), now=now)
            current = robot_service.dashboard_robots(now=now)[0]
            expired = robot_service.dashboard_robots(now=now + timedelta(seconds=16))[0]
        self.assertEqual(current["connection_status"], "ONLINE")
        self.assertEqual(expired["connection_status"], "OFFLINE")

    def test_rapid_updates_refresh_latest_but_sample_history(self):
        """2 Hz 수신은 최신 표만 갱신하고 이력은 1초 간격으로만 남는다."""
        base = datetime(2026, 9, 9, 10, 0, 0, tzinfo=timezone.utc)
        with self.app.app_context():
            for index, offset in enumerate((0.0, 0.5, 0.9, 1.0, 1.4, 2.2)):
                observed = (base + timedelta(seconds=offset)).isoformat()
                outcome, stored = robot_service.receive_status(
                    self.payload(message_id=f"amr1-fast-{index}", battery=90 - index,
                                 observed_at=observed),
                    now=base + timedelta(seconds=offset + 0.1),
                )
                self.assertEqual(outcome, "accepted")
                self.assertEqual(stored["history_recorded"], offset in (0.0, 1.0, 2.2))
            db = get_db()
            self.assertEqual(db.execute("SELECT battery FROM robot_latest_status").fetchone()[0], 85)
            rows = db.execute(
                "SELECT message_id FROM robot_status_history ORDER BY observed_at"
            ).fetchall()
            self.assertEqual([row[0] for row in rows], ["amr1-fast-0", "amr1-fast-3", "amr1-fast-5"])

    def test_history_older_than_retention_is_pruned_once_per_minute(self):
        """보존 기간이 지난 이력은 저장 경로에서 지우되 1분에 한 번만 DELETE를 돌린다."""
        now = datetime(2026, 9, 9, 10, 0, 0, tzinfo=timezone.utc)
        with self.app.app_context():
            eight_days_ago = now - timedelta(days=8)
            # 8일 전 시점에 저장된 이력. 그때는 보존 기간 안이라 지워지지 않는다.
            _, first = robot_service.receive_status(
                self.payload(message_id="old", observed_at=eight_days_ago.isoformat()), now=eight_days_ago
            )
            self.assertEqual(first["history_pruned"], 0)
            # 1분 넘게 지난 뒤의 저장은 정리를 돌려 8일 전 행을 지운다.
            _, second = robot_service.receive_status(
                self.payload(message_id="kept", observed_at=(now - timedelta(days=6)).isoformat()),
                now=now - timedelta(seconds=30),
            )
            self.assertEqual(second["history_pruned"], 1)
            # 마지막 정리 뒤 1분 안의 저장은 DELETE를 건너뛴다.
            _, third = robot_service.receive_status(
                self.payload(message_id="fresh", observed_at=now.isoformat()), now=now
            )
            self.assertEqual(third["history_pruned"], 0)
            rows = get_db().execute(
                "SELECT message_id FROM robot_status_history ORDER BY observed_at"
            ).fetchall()
            self.assertEqual([row[0] for row in rows], ["kept", "fresh"])

    def test_simultaneous_retry_creates_one_history_row(self):
        payload = self.payload()

        def send_from_new_client(_):
            client = self.app.test_client()
            return client.post("/api/robots/status", json=payload,
                               headers={"X-Robot-Token": "robot-device-test-key"}).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(send_from_new_client, range(2)))
        self.assertCountEqual(codes, [200, 201])
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM robot_status_history").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
