"""20단계 순찰 방문·보고와 Keepout·E-stop 저장·표시를 검증한다."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
import uuid

from app import create_app
from app.database import get_db
from app.models.patrol import PatrolConflictError
from app.services import auth_service, patrol_service, safety_service


class PatrolSafetyTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name) / "instance"
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(root / "sysmon.sqlite3"),
            "EVIDENCE_DIR": str(root / "evidence"),
            "SECRET_KEY": "patrol-tests-only-key",
            "ESTOP_STALE_AFTER_SECONDS": 10,
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            self.user_id = auth_service.create_user(
                "patrol-viewer", "Test-pass-123", "VIEWER"
            )
            db = get_db()
            db.executemany(
                "INSERT OR IGNORE INTO robots(robot_id, name) VALUES (?, ?)",
                (("AMR1", "로봇 1"), ("AMR2", "로봇 2")),
            )
            db.commit()
        self.now = datetime(2026, 9, 7, 6, 0, 0, tzinfo=timezone.utc)

    def visit(self, **changes):
        payload = {
            "visit_id": str(uuid.uuid4()), "message_id": str(uuid.uuid4()),
            "robot_id": "AMR1", "patrol_id": "patrol-0001",
            "mission_id": "", "command_id": "", "waypoint_id": "P3",
            "x": 3.5, "y": 4.5, "frame_id": "map", "result": "SUCCEEDED",
            "reason_code": 0, "reason": "",
            "arrived_at": (self.now - timedelta(seconds=30)).isoformat(),
            "completed_at": (self.now - timedelta(seconds=20)).isoformat(),
        }
        payload.update(changes)
        return payload

    def report(self, **changes):
        payload = {
            "patrol_id": "patrol-0001", "report_id": str(uuid.uuid4()),
            "message_id": str(uuid.uuid4()), "robot_id": "AMR1",
            "mission_id": "", "command_id": "", "result": "SUCCEEDED",
            "reason_code": 0, "reason": "",
            "started_at": (self.now - timedelta(minutes=5)).isoformat(),
            "ended_at": (self.now - timedelta(seconds=10)).isoformat(),
            "planned_visit_count": 2, "completed_visit_count": 2,
        }
        payload.update(changes)
        return payload

    def keepout(self, **changes):
        payload = {
            "robot_id": "AMR1", "message_id": str(uuid.uuid4()),
            "transaction_id": str(uuid.uuid4()), "state": "APPLIED",
            "global_enabled": True, "local_enabled": True,
            "reason_code": 0, "detail": "",
            "observed_at": (self.now - timedelta(seconds=5)).isoformat(),
        }
        payload.update(changes)
        return payload

    def estop(self, **changes):
        # 계약 EStop(interfaces.md 3.1절): 대상·활성·대표 원인·순번만 있다.
        payload = {
            "target_robot_id": "robot1", "active": True, "reason": 4, "sequence": 1,
            "observed_at": (self.now - timedelta(seconds=3)).isoformat(),
        }
        payload.update(changes)
        return payload

    def login(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def test_visit_and_report_are_stored_with_contract_labels(self):
        with self.app.app_context():
            self.assertEqual(patrol_service.receive_visit(self.visit(), self.now)[0], "accepted")
            self.assertEqual(patrol_service.receive_report(self.report(), self.now)[0], "accepted")
            view = patrol_service.dashboard_patrol()
        self.assertEqual(view["visits"][0]["waypoint_id"], "P3")
        self.assertEqual(view["visits"][0]["result_label"], "완료")
        self.assertEqual(view["reports"][0]["result_label"], "완료")
        self.assertEqual(view["reports"][0]["completed_visit_count"], 2)
        # 보고가 도착한 순찰은 UNREPORTED 목록에서 빠진다.
        self.assertEqual(view["unreported"], [])

    def test_patrol_without_report_is_marked_unreported(self):
        """계약상 관제는 없는 결과를 대필하지 않고 보고 누락만 표시한다."""
        with self.app.app_context():
            patrol_service.receive_visit(self.visit(patrol_id="patrol-0002"), self.now)
            view = patrol_service.dashboard_patrol()
        self.assertEqual(len(view["unreported"]), 1)
        self.assertEqual(view["unreported"][0]["patrol_id"], "patrol-0002")
        self.assertEqual(view["unreported"][0]["result_label"], "보고 없음")

    def test_duplicate_and_conflicting_visit_are_distinguished(self):
        payload = self.visit()
        with self.app.app_context():
            patrol_service.receive_visit(payload, self.now)
            self.assertEqual(patrol_service.receive_visit(payload, self.now)[0], "duplicate")
            with self.assertRaises(PatrolConflictError):
                patrol_service.receive_visit(
                    dict(payload, waypoint_id="P7"), self.now
                )
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM patrol_visits").fetchone()[0], 1
            )

    def test_contract_violations_are_rejected(self):
        cases = (
            self.visit(result="DONE"),
            self.visit(waypoint_id=""),
            self.visit(visit_id="not-a-uuid"),
            self.visit(frame_id="odom"),
            self.visit(arrived_at="2026-09-07T06:00:00"),
        )
        with self.app.app_context():
            for payload in cases:
                with self.assertRaises(patrol_service.PatrolValidationError):
                    patrol_service.receive_visit(payload, self.now)
            # 실패·취소 보고에는 원인 코드와 설명이 필수다.
            with self.assertRaises(patrol_service.PatrolValidationError):
                patrol_service.receive_report(
                    self.report(result="FAILED", reason_code=0, reason=""), self.now
                )
            with self.assertRaises(patrol_service.PatrolValidationError):
                patrol_service.receive_report(
                    self.report(planned_visit_count=1, completed_visit_count=2), self.now
                )
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM patrol_runs").fetchone()[0], 0
            )

    def test_keepout_keeps_latest_row_and_marks_rollback_failure(self):
        with self.app.app_context():
            safety_service.receive_keepout(self.keepout(), self.now)
            safety_service.receive_keepout(
                self.keepout(
                    state="ROLLBACK_FAILED", reason_code=12, detail="parameter 적용 실패",
                    observed_at=self.now.isoformat(),
                ),
                self.now,
            )
            rows = get_db().execute("SELECT COUNT(*) FROM keepout_latest").fetchone()[0]
            view = safety_service.dashboard_safety(self.now)
        self.assertEqual(rows, 1)
        self.assertEqual(view["keepouts"][0]["state_label"], "되돌리기 실패")
        self.assertTrue(view["keepouts"][0]["warning"])
        self.assertEqual(view["keepout_warning_count"], 1)

    def test_keepout_can_arrive_before_first_robot_status(self):
        """DDS 메시지 도착 순서와 무관하게 첫 Keepout 상태를 저장한다."""
        with self.app.app_context():
            db = get_db()
            db.execute("DELETE FROM robots WHERE robot_id = 'AMR1'")
            db.commit()
            self.assertEqual(
                safety_service.receive_keepout(self.keepout(), self.now)[0],
                "accepted",
            )
            robot = db.execute(
                "SELECT name FROM robots WHERE robot_id = 'AMR1'"
            ).fetchone()
            keepout = db.execute(
                "SELECT state FROM keepout_latest WHERE robot_id = 'AMR1'"
            ).fetchone()
        self.assertEqual(robot["name"], "로봇 1")
        self.assertEqual(keepout["state"], "APPLIED")

    def test_estop_records_only_state_changes_and_keeps_last_value(self):
        first = self.estop()
        with self.app.app_context():
            self.assertEqual(safety_service.receive_estop(first, self.now)[0], "changed")
            # 같은 상태의 반복 수신은 최신 행만 갱신한다.
            self.assertEqual(
                safety_service.receive_estop(dict(first, sequence=2), self.now)[0],
                "refreshed",
            )
            view_active = safety_service.dashboard_safety(self.now)
            self.assertEqual(
                safety_service.receive_estop(
                    dict(
                        first, active=False, reason=0, sequence=3,
                        observed_at=self.now.isoformat(),
                    ),
                    self.now,
                )[0],
                "changed",
            )
            history = get_db().execute("SELECT COUNT(*) FROM estop_history").fetchone()[0]
            view = safety_service.dashboard_safety(self.now)
        self.assertEqual(history, 2)
        self.assertTrue(view_active["estop"]["active"])
        self.assertEqual(view_active["estop"]["state_label"], "비상정지 활성 (로봇 1)")
        self.assertEqual(view_active["estop"]["reason"], "장애물 안전 차단")
        self.assertFalse(view["estop"]["active"])
        self.assertEqual(view["estop"]["state_label"], "정상")
        self.assertFalse(view["estop"]["stale"])
        self.assertEqual(view["estop"]["reason"], "")

    def test_estop_targets_are_kept_separately_and_all_covers_both_robots(self):
        with self.app.app_context():
            safety_service.receive_estop(self.estop(active=False, reason=0), self.now)
            safety_service.receive_estop(
                self.estop(target_robot_id="all", reason=1, sequence=7), self.now
            )
            rows = get_db().execute("SELECT COUNT(*) FROM estop_latest").fetchone()[0]
            view = safety_service.dashboard_safety(self.now)
        self.assertEqual(rows, 2)
        self.assertTrue(view["estop"]["active"])
        self.assertEqual(view["estop"]["state_label"], "비상정지 활성 (전체)")
        self.assertEqual(view["estop"]["reason"], "운영자 정지 요청")
        by_target = {item["target_robot_id"]: item for item in view["estop"]["targets"]}
        self.assertFalse(by_target["robot1"]["active"])
        self.assertTrue(by_target["all"]["active"])
        # robot6은 받은 적이 없으므로 해제로 표시하지 않는다.
        self.assertFalse(by_target["robot6"]["available"])

    def test_estop_contract_violations_are_rejected(self):
        with self.app.app_context():
            for payload in (
                self.estop(target_robot_id="AMR1"),
                self.estop(reason=9),
                self.estop(active="yes"),
                self.estop(sequence=-1),
            ):
                with self.assertRaises(safety_service.SafetyValidationError):
                    safety_service.receive_estop(payload, self.now)

    def test_missing_estop_is_not_shown_as_cleared(self):
        with self.app.app_context():
            view = safety_service.dashboard_safety(self.now)
        self.assertFalse(view["estop"]["available"])
        self.assertIsNone(view["estop"]["active"])
        self.assertEqual(view["estop"]["state_label"], "E-stop 수신 대기")

    def test_apis_require_login_and_expose_monitor_only_data(self):
        self.assertEqual(self.client.get("/api/patrol/status").status_code, 302)
        self.assertEqual(self.client.get("/api/safety/status").status_code, 302)
        with self.app.app_context():
            patrol_service.receive_visit(self.visit(), self.now)
            safety_service.receive_estop(self.estop(), self.now)
        self.login()
        patrol = self.client.get("/api/patrol/status").get_json()
        safety = self.client.get("/api/safety/status").get_json()
        self.assertEqual(patrol["visits"][0]["waypoint_id"], "P3")
        self.assertTrue(safety["estop"]["active"])
        # 조회 전용 API이므로 변경 경로가 없다. CSRF 검사가 먼저 걸려 400, 없으면 405다.
        self.assertIn(self.client.post("/api/patrol/status").status_code, (400, 405))


if __name__ == "__main__":
    unittest.main()
