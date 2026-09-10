"""v2 Patrol Action 피드백·상태와 배터리를 로봇 상태·방문·결과로 옮기는 추적기를 확인한다."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import tempfile
import unittest

from app import create_app
from app.database import get_db
from app.ros.patrol_action import PatrolActionTracker, stable_uuid
from app.services import patrol_service, robot_service


GOAL = "0b5f1f4c-3c52-4c0e-9f0e-8d7c5b1a2e3f"
UUID_V4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def feedback(task_state, waypoint="", x=1.0, y=2.0, pose_valid=True, robot_id="AMR1", goal=GOAL):
    return {
        "robot_id": robot_id, "goal_id": goal, "task_state": task_state,
        "waypoint_id": waypoint, "token_valid": True, "pose_valid": pose_valid,
        "x": x if pose_valid else None, "y": y if pose_valid else None,
    }


def goal_status(status, finished, goal=GOAL, accepted_at="2026-09-10T01:00:00.000Z"):
    return {"robot_id": "AMR1", "goals": [
        {"goal_id": goal, "status": status, "finished": finished, "accepted_at": accepted_at},
    ]}


class PatrolActionTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tracker = PatrolActionTracker()
        self.now = datetime(2026, 9, 10, 1, 0, 5, tzinfo=timezone.utc)

    def kinds(self, outputs):
        return [kind for kind, _ in outputs]

    def test_stable_uuid_is_repeatable_v4_shape(self):
        first = stable_uuid("visit", "AMR1", GOAL, "wp1", "0")
        self.assertEqual(first, stable_uuid("visit", "AMR1", GOAL, "wp1", "0"))
        self.assertNotEqual(first, stable_uuid("visit", "AMR1", GOAL, "wp1", "1"))
        self.assertRegex(first, UUID_V4)

    def test_feedback_updates_mission_and_pose_and_battery_is_merged(self):
        self.tracker.on_battery({"robot_id": "AMR1", "battery": 82.5}, self.now)
        outputs = self.tracker.on_feedback(feedback("PATROLLING"), self.now)
        self.assertEqual(self.kinds(outputs), ["status"])
        status = outputs[0][1]
        self.assertEqual(
            (status["battery"], status["mission_status"], status["x"], status["y"],
             status["pose_valid"], status["connection_status"]),
            (82.5, "PATROLLING", 1.0, 2.0, True, "ONLINE"),
        )
        # 위치를 모르는 피드백은 마지막으로 알던 위치를 지우지 않는다.
        later = self.tracker.on_feedback(feedback("BLOCKED", pose_valid=False), self.now)[0][1]
        self.assertEqual((later["mission_status"], later["x"], later["y"]), ("BLOCKED", 1.0, 2.0))

    def test_battery_only_updates_are_throttled_unless_value_changes(self):
        first = self.tracker.on_battery({"robot_id": "AMR1", "battery": 80.0}, self.now)
        same = self.tracker.on_battery(
            {"robot_id": "AMR1", "battery": 80.0}, self.now + timedelta(seconds=0.5)
        )
        changed = self.tracker.on_battery(
            {"robot_id": "AMR1", "battery": 79.0}, self.now + timedelta(seconds=0.6)
        )
        later = self.tracker.on_battery(
            {"robot_id": "AMR1", "battery": 79.0}, self.now + timedelta(seconds=2)
        )
        self.assertEqual([len(first), len(same), len(changed), len(later)], [1, 0, 1, 1])
        # 배터리를 아직 못 받았으면 비워 둔다.
        status = self.tracker.on_feedback(feedback("PATROLLING", robot_id="AMR2"), self.now)[0][1]
        self.assertIsNone(status["battery"])

    def test_waypoint_reached_records_one_visit_per_arrival(self):
        outputs = []
        for state, waypoint in (
            ("PATROLLING", ""), ("WAYPOINT_REACHED", "wp1"), ("WAYPOINT_REACHED", "wp1"),
            ("WAYPOINT_REACHED", "wp2"), ("PATROLLING", "wp2"), ("WAYPOINT_REACHED", "wp1"),
            ("WAYPOINT_REACHED", ""),
        ):
            outputs.extend(self.tracker.on_feedback(feedback(state, waypoint), self.now))
        visits = [payload for kind, payload in outputs if kind == "visit"]
        # 같은 관측점 반복 피드백은 한 번, 다시 돌아와 도착하면 새 방문, 관측점 ID가 없으면 기록하지 않는다.
        self.assertEqual([visit["waypoint_id"] for visit in visits], ["wp1", "wp2", "wp1"])
        self.assertEqual({visit["patrol_id"] for visit in visits}, {GOAL})
        self.assertEqual(len({visit["visit_id"] for visit in visits}), 3)
        # 재시작 뒤 같은 목표·관측점·회차면 같은 ID가 나와 저장 서비스가 중복으로 처리할 수 있다.
        restarted = PatrolActionTracker().on_feedback(feedback("WAYPOINT_REACHED", "wp1"), self.now)
        self.assertEqual(restarted[1][1]["visit_id"], visits[0]["visit_id"])

    def test_finished_goal_reports_once_and_sets_latest_mission(self):
        self.tracker.on_feedback(feedback("DOCKING"), self.now)
        self.assertEqual(self.tracker.on_goal_status(goal_status("EXECUTING", False), self.now), [])
        outputs = self.tracker.on_goal_status(goal_status("SUCCEEDED", True), self.now)
        self.assertEqual(self.kinds(outputs), ["report", "status"])
        report = outputs[0][1]
        self.assertEqual(
            (report["patrol_id"], report["result"], report["started_at"]),
            (GOAL, "SUCCEEDED", "2026-09-10T01:00:00.000Z"),
        )
        self.assertEqual(outputs[1][1]["mission_status"], "COMPLETED")
        # 상태 토픽은 끝난 목표를 계속 싣는다. 이미 기록한 결과는 다시 만들지 않는다.
        self.assertEqual(self.tracker.on_goal_status(goal_status("SUCCEEDED", True), self.now), [])

    def test_old_finished_goal_does_not_override_newer_mission(self):
        newer = "5d6b2c1a-9e8f-4a7b-8c6d-1e2f3a4b5c6d"
        payload = {"robot_id": "AMR1", "goals": [
            {"goal_id": GOAL, "status": "FAILED", "finished": True,
             "accepted_at": "2026-09-10T00:50:00.000Z"},
            {"goal_id": newer, "status": "EXECUTING", "finished": False,
             "accepted_at": "2026-09-10T01:00:00.000Z"},
        ]}
        outputs = self.tracker.on_goal_status(payload, self.now)
        # 옛 목표의 결과는 기록하지만 현재 임무 상태는 바꾸지 않는다.
        self.assertEqual(self.kinds(outputs), ["report"])
        self.assertEqual(outputs[0][1]["result"], "FAILED")


class PatrolActionStorageTests(unittest.TestCase):
    """추적기 출력이 기존 저장 서비스 검증을 그대로 통과하는지 확인한다."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name) / "instance"
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(root / "sysmon.sqlite3"),
            "EVIDENCE_DIR": str(root / "evidence"),
            "SECRET_KEY": "patrol-action-tests-only-key",
            "ROBOT_STATUS_HISTORY_MIN_INTERVAL_SECONDS": 0,
        })

    def test_outputs_are_accepted_by_storage_services(self):
        tracker = PatrolActionTracker()
        now = datetime.now(timezone.utc)
        handlers = {
            "status": robot_service.receive_status,
            "visit": patrol_service.receive_visit,
            "report": patrol_service.receive_action_result,
        }
        outputs = []
        outputs += tracker.on_feedback(feedback("PATROLLING"), now)
        outputs += tracker.on_feedback(feedback("WAYPOINT_REACHED", "wp1"), now + timedelta(seconds=1))
        outputs += tracker.on_feedback(feedback("WAYPOINT_REACHED", "wp2"), now + timedelta(seconds=2))
        outputs += tracker.on_goal_status(
            goal_status("SUCCEEDED", True, accepted_at=(now - timedelta(minutes=1)).isoformat()),
            now + timedelta(seconds=3),
        )
        with self.app.app_context():
            outcomes = [handlers[kind](payload)[0] for kind, payload in outputs]
            latest = get_db().execute(
                "SELECT battery, mission_status FROM robot_latest_status WHERE robot_id = 'AMR1'"
            ).fetchone()
            run = get_db().execute(
                "SELECT result, completed_visit_count FROM patrol_runs WHERE patrol_id = ?", (GOAL,)
            ).fetchone()
            robots = robot_service.dashboard_robots(now + timedelta(seconds=3))
        self.assertEqual(set(outcomes), {"accepted"})
        self.assertEqual((latest["battery"], latest["mission_status"]), (None, "COMPLETED"))
        self.assertEqual((run["result"], run["completed_visit_count"]), ("SUCCEEDED", 2))
        amr1 = next(robot for robot in robots if robot["id"] == "AMR1")
        self.assertEqual((amr1["battery"], amr1["mission_label"]), (None, "완료"))


if __name__ == "__main__":
    unittest.main()
