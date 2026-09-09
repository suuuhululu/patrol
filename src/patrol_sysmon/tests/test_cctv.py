"""19단계 CameraState·patrol_allowed 저장과 화면 상태를 검증한다."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
import uuid

from app import create_app
from app.database import get_db
from app.models.cctv import CctvEventConflictError
from app.services import auth_service, cctv_service


class CctvTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name) / "instance"
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(root / "sysmon.sqlite3"),
            "EVIDENCE_DIR": str(root / "evidence"),
            "SECRET_KEY": "cctv-tests-only-key",
            "PATROL_PERMIT_STALE_SECONDS": 1.5,
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            self.user_id = auth_service.create_user(
                "cctv-viewer", "Test-pass-123", "VIEWER"
            )
        self.now = datetime(2026, 9, 7, 5, 0, 0, tzinfo=timezone.utc)

    _sequence = 0

    def contract_event_id(self, camera_id="gate_cam", state="ENTERING"):
        # 비전 팀 확정 형식: cam-<source_session_id>-<state 소문자>-<source_sequence 4자리>
        type(self)._sequence += 1
        return f"cam-{camera_id}-20260907T050000-01-{state.lower()}-{type(self)._sequence:04d}"

    def payload(self, **changes):
        payload = {
            "event_id": self.contract_event_id(
                changes.get("camera_id", "gate_cam"), changes.get("state", "ENTERING")
            ),
            "camera_id": "gate_cam",
            "state": "ENTERING",
            "confidence": 0.93,
            "observed_at": (self.now - timedelta(milliseconds=100)).isoformat(),
        }
        payload.update(changes)
        return payload

    def login(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def test_valid_camera_states_are_stored_and_labeled(self):
        gate = self.payload()
        center = self.payload(camera_id="center_cam", state="PARKED")
        with self.app.app_context():
            self.assertEqual(cctv_service.receive_camera_state(gate, self.now)[0], "accepted")
            self.assertEqual(cctv_service.receive_camera_state(center, self.now)[0], "accepted")
            state = cctv_service.dashboard_cctv(self.now)
            self.assertEqual(
                {item["camera_id"] for item in state["events"]},
                {"gate_cam", "center_cam"},
            )
            self.assertEqual(
                {item["state_label"] for item in state["events"]},
                {"진입 중", "주차 완료"},
            )

    def test_camera_state_is_also_recorded_in_vehicle_access_log(self):
        """게이트 진입·출차만 입출차 로그로 남기고 센터 상태는 CCTV 상태로만 둔다."""
        with self.app.app_context():
            for camera_id, state, direction in (
                ("gate_cam", "ENTERING", "ENTRY"), ("gate_cam", "EXITED", "EXIT"),
            ):
                payload = self.payload(camera_id=camera_id, state=state)
                cctv_service.receive_camera_state(payload, self.now)
                row = get_db().execute(
                    "SELECT camera_id, direction FROM vehicle_access_logs WHERE access_id = ?",
                    (payload["event_id"],),
                ).fetchone()
                self.assertEqual((row["camera_id"], row["direction"]), ("webcam1", direction))
            # 센터 CCTV의 주차 완료·출차 중은 주차장 안 상태라 입출차로 남기지 않는다.
            for state in ("PARKED", "EXITING"):
                cctv_service.receive_camera_state(
                    self.payload(camera_id="center_cam", state=state), self.now
                )
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM vehicle_access_logs").fetchone()[0], 2
            )
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM cctv_state_events").fetchone()[0], 4
            )

    def test_repeated_camera_state_does_not_duplicate_vehicle_access_row(self):
        payload = self.payload()
        with self.app.app_context():
            cctv_service.receive_camera_state(payload, self.now)
            self.assertEqual(
                cctv_service.receive_camera_state(payload, self.now)[0], "duplicate"
            )
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM vehicle_access_logs").fetchone()[0], 1
            )

    def test_center_states_appear_in_access_list_without_new_access_rows(self):
        """센터의 주차 완료·출차 중은 목록에는 나오되 입출차 행으로는 세지 않는다."""
        from app.services import vehicle_access_service

        with self.app.app_context():
            cctv_service.receive_camera_state(
                self.payload(camera_id="gate_cam", state="ENTERING"), self.now
            )
            cctv_service.receive_camera_state(
                self.payload(camera_id="center_cam", state="PARKED"), self.now
            )
            cctv_service.receive_camera_state(
                self.payload(camera_id="center_cam", state="EXITING"), self.now
            )
            items = vehicle_access_service.recent_accesses()
            stored = get_db().execute(
                "SELECT COUNT(*) FROM vehicle_access_logs"
            ).fetchone()[0]
        self.assertEqual(stored, 1)
        self.assertEqual(len(items), 3)
        self.assertEqual(
            {item["direction_label"] for item in items},
            {"입차", "주차 완료", "출차 중"},
        )
        self.assertEqual(
            {item["camera_name"] for item in items}, {"고정 웹캠 1", "센터 CCTV"}
        )

    def test_duplicate_and_conflicting_event_id_are_distinguished(self):
        payload = self.payload()
        with self.app.app_context():
            self.assertEqual(cctv_service.receive_camera_state(payload, self.now)[0], "accepted")
            self.assertEqual(cctv_service.receive_camera_state(payload, self.now)[0], "duplicate")
            with self.assertRaises(CctvEventConflictError):
                cctv_service.receive_camera_state(
                    {**payload, "state": "EXITED"}, self.now
                )
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM cctv_state_events").fetchone()[0], 1
            )

    def test_invalid_camera_state_contract_values_are_rejected(self):
        invalid = (
            self.payload(event_id="not-a-contract-id"),
            self.payload(event_id="cam-gate_cam-2026-01-entering-1"),
            self.payload(camera_id="webcam1"),
            self.payload(state="PARKED"),
            self.payload(confidence=float("nan")),
            self.payload(confidence=1.1),
            self.payload(observed_at="2026-09-07 05:00:00"),
        )
        with self.app.app_context():
            for payload in invalid:
                with self.subTest(payload=payload), self.assertRaises(
                    cctv_service.CctvValidationError
                ):
                    cctv_service.receive_camera_state(payload, self.now)
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM cctv_state_events").fetchone()[0], 0
            )

    def test_permit_refresh_keeps_last_value_and_records_only_changes(self):
        with self.app.app_context():
            self.assertEqual(cctv_service.receive_patrol_allowed(False, self.now), "changed")
            self.assertEqual(
                cctv_service.receive_patrol_allowed(
                    False, self.now + timedelta(seconds=1)
                ),
                "refreshed",
            )
            fresh = cctv_service.dashboard_cctv(self.now + timedelta(seconds=2))
            self.assertFalse(fresh["permit"]["allowed"])
            self.assertFalse(fresh["permit"]["stale"])
            stale = cctv_service.dashboard_cctv(self.now + timedelta(seconds=3))
            self.assertFalse(stale["permit"]["allowed"])
            self.assertTrue(stale["permit"]["stale"])
            self.assertEqual(stale["permit"]["state"], "STALE")
            self.assertEqual(
                cctv_service.receive_patrol_allowed(
                    True, self.now + timedelta(seconds=4)
                ),
                "changed",
            )
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM patrol_permit_history").fetchone()[0], 2
            )
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM patrol_permit_latest").fetchone()[0], 1
            )

    def test_api_requires_login_and_dashboard_shows_monitor_only_boundary(self):
        self.assertEqual(self.client.get("/api/cctv/status").location, "/login")
        with self.app.app_context():
            cctv_service.receive_camera_state(self.payload(), self.now)
            cctv_service.receive_patrol_allowed(False, self.now)
        self.login()
        response = self.client.get("/api/cctv/status")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["permit"]["allowed"])
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn("CCTV 순찰 조건", page)
        self.assertIn("통신 경고 · 마지막 값 유지", page)
        self.assertNotIn("vehicle_entry_block", page)
        self.assertEqual(
            self.client.get("/api/history?type=CCTV_STATE").get_json()["total"], 1
        )
        self.assertEqual(
            self.client.get("/api/history?type=PATROL_PERMIT").get_json()["total"], 1
        )

    def test_permit_rejects_non_bool_without_changing_storage(self):
        with self.app.app_context():
            for value in (0, 1, "true", None):
                with self.subTest(value=value), self.assertRaises(
                    cctv_service.CctvValidationError
                ):
                    cctv_service.receive_patrol_allowed(value, self.now)
            self.assertIsNone(cctv_service.dashboard_cctv(self.now)["permit"]["allowed"])


if __name__ == "__main__":
    unittest.main()
