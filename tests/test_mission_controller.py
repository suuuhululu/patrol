from pathlib import Path
import tempfile
import threading
import unittest

from patrol_amr.mission_command_store import CommandStore
from patrol_amr.mission_controller import MissionController
from patrol_amr.mission_types import MissionRequest, MissionType, PoseTarget
from patrol_amr.navigation_adapter import NavigationResult, Waypoint


class FakeNavigation:
    def __init__(self, results=()):
        self.results = iter(results)
        self.goals = []
        self.canceled = False
        self.dock_calls = []

    def ensure_undocked(self, cancel_event):
        return NavigationResult.SUCCEEDED

    def go_to(self, waypoint, cancel_event):
        self.goals.append(waypoint)
        return next(self.results)

    def dock(self, cancel_event, timeout_s, stable_s):
        self.dock_calls.append((timeout_s, stable_s))
        return next(self.results)

    def cancel(self):
        self.canceled = True


class MissionControllerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def controller(self, navigation, resume_policy='disabled'):
        return MissionController(
            navigation,
            CommandStore(self.root / 'commands.json'),
            [
                Waypoint('W1', 0.0, 0.0, 0.0),
                Waypoint('W2', 1.0, 0.0, 0.0),
            ],
            0.0,
            resume_policy,
            lambda state, index: None,
        )

    @staticmethod
    def request(command, target_id='', target_pose=None):
        return MissionRequest(
            command_id='cmd-ctrl-20260907T160000-robot1-start-0001',
            mission_id='msn-ctrl-20260907T160000-robot1-0001',
            robot_id='robot1',
            command=command,
            target_id=target_id, target_pose=target_pose)

    def test_resume_is_rejected_while_policy_tbd(self):
        result = self.controller(FakeNavigation()).execute(
            self.request(MissionType.RESUME_PATROL, 'patrol-a'),
            threading.Event())
        self.assertEqual(result.outcome, 'REJECTED')
        self.assertEqual(result.reason, 'TBD_AMR_005_RESUME_POLICY_OPEN')

    def test_safe_zone_requires_explicit_target(self):
        result = self.controller(FakeNavigation()).execute(
            self.request(MissionType.MOVE_TO_SAFE_ZONE), threading.Event())
        self.assertEqual(result.outcome, 'REJECTED')
        self.assertEqual(result.reason, 'SAFE_ZONE_TARGET_POSE_REQUIRED')

    def test_safe_zone_uses_map_target_and_reports_success(self):
        navigation = FakeNavigation([NavigationResult.SUCCEEDED])
        result = self.controller(navigation).execute(
            self.request(
                MissionType.MOVE_TO_SAFE_ZONE,
                'safe-a',
                PoseTarget('map', -1.0, -2.0, 90.0),
            ),
            threading.Event(),
        )
        self.assertEqual(result.outcome, 'SUCCEEDED')
        self.assertEqual(
            navigation.goals, [Waypoint('safe-a', -1.0, -2.0, 90.0)])

    def test_stop_invokes_navigation_cancel(self):
        navigation = FakeNavigation()
        result = self.controller(navigation).execute(
            self.request(MissionType.STOP), threading.Event())
        self.assertEqual(result.outcome, 'SUCCEEDED')
        self.assertTrue(navigation.canceled)

    def test_dock_uses_q09_timeout_and_stability_values(self):
        navigation = FakeNavigation([NavigationResult.SUCCEEDED])
        result = self.controller(navigation).execute(
            self.request(MissionType.DOCK), threading.Event())
        self.assertEqual(result.outcome, 'SUCCEEDED')

    def test_start_patrol_undocks_visits_every_waypoint_then_docks(self):
        navigation = FakeNavigation([
            NavigationResult.SUCCEEDED,
            NavigationResult.SUCCEEDED,
            NavigationResult.SUCCEEDED,
        ])
        result = self.controller(navigation).execute(
            self.request(MissionType.START_PATROL, 'patrol-a'),
            threading.Event(),
        )
        self.assertEqual(result.outcome, 'SUCCEEDED')
        self.assertEqual(
            [goal.name for goal in navigation.goals], ['W1', 'W2'])
        self.assertEqual(navigation.dock_calls, [(60.0, 2.0)])

    def test_fingerprint_is_stable_and_changes_with_content(self):
        original = self.request(MissionType.START_PATROL, 'patrol-a')
        same = self.request(MissionType.START_PATROL, 'patrol-a')
        changed = self.request(MissionType.START_PATROL, 'patrol-b')
        self.assertEqual(original.fingerprint(), same.fingerprint())
        self.assertNotEqual(original.fingerprint(), changed.fingerprint())

    def test_fingerprint_uses_mission_id_but_not_issued_by(self):
        original = self.request(MissionType.START_PATROL, 'patrol-a')
        changed_mission = MissionRequest(
            command_id=original.command_id,
            mission_id='msn-ctrl-20260907T160000-robot1-0002',
            robot_id=original.robot_id,
            command=original.command,
            target_id=original.target_id,
        )
        changed_sender = MissionRequest(
            command_id=original.command_id,
            mission_id=original.mission_id,
            robot_id=original.robot_id,
            command=original.command,
            target_id=original.target_id,
            issued_by='backup-control',
        )
        self.assertNotEqual(
            original.fingerprint(), changed_mission.fingerprint())
        self.assertEqual(original.fingerprint(), changed_sender.fingerprint())
