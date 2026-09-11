"""Verify temporary projections without changing measured safety fields."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/patrol_amr_safety'))
from patrol_amr_safety import provisional_status_policy as policy
from patrol_amr_safety import robot_status_state as rss


class ProvisionalPolicyTests(unittest.TestCase):
    def setUp(self):
        self.state = rss.RobotStatusState('robot1')
        self.mission = SimpleNamespace(outcome='')

    def project(self, now=0, has_mission=True):
        return policy.project_axes(self.state.snapshot(now), self.mission,
                                   has_mission=has_mission)

    def test_boot_without_source_has_explicit_unknown_scan(self):
        result = self.project(has_mission=False)
        self.assertEqual(result.operational_state, rss.OperationalState.OP_INITIALIZING)
        self.assertEqual(result.docking_state, rss.DockingState.DOCK_UNKNOWN)
        self.assertEqual(result.scan_state, 'UNKNOWN')

    def test_moving_and_stationary_patrol_projection(self):
        self.state.update_states(mission_state=rss.MissionState.MISSION_PATROLLING,
                                 safety_state=rss.SafetyState.SAFETY_NORMAL)
        self.state.observe_odometry(0.2, 0, 0)
        moving = self.project()
        self.assertEqual(moving.operational_state, rss.OperationalState.OP_MOVING)
        self.assertEqual(moving.scan_state, 'MOVING_TO_WAYPOINT')
        self.state.observe_odometry(0, 0, 0.1)
        self.state.observe_odometry(0, 0, 0.6)
        self.state.observe_odometry(0, 0, 0.7)
        stopped = self.project(0.7)
        self.assertEqual(stopped.operational_state, rss.OperationalState.OP_READY)
        self.assertEqual(stopped.scan_state, 'SCANNING')
        self.assertEqual(self.project(1.201).scan_state, 'UNKNOWN')

    def test_docking_completion_and_failure_do_not_oscillate(self):
        self.state.update_states(mission_state=rss.MissionState.MISSION_DOCKING)
        self.assertEqual(self.project().docking_state, rss.DockingState.DOCK_DOCKING)
        self.state.update_states(docking_state=rss.DockingState.DOCK_DOCKING,
                                 mission_state=rss.MissionState.MISSION_COMPLETED)
        self.mission.outcome = 'SUCCEEDED'
        self.assertEqual(self.project().docking_state, rss.DockingState.DOCK_DOCKED)
        self.state.update_states(mission_state=rss.MissionState.MISSION_FAILED,
                                 battery_state=rss.BatteryState.CHARGING)
        first = self.project()
        self.assertEqual(first.docking_state, rss.DockingState.DOCK_FAILED)
        self.state.update_states(docking_state=first.docking_state)
        self.assertEqual(self.project().docking_state, rss.DockingState.DOCK_FAILED)

    def test_safety_precedence_and_no_input_mutation(self):
        self.state.update_states(safety_state=rss.SafetyState.SAFETY_ESTOPPED,
                                 battery_state=rss.BatteryState.CHARGING)
        before = self.state.snapshot(0)
        projected = self.project()
        self.assertEqual(projected.operational_state, rss.OperationalState.OP_STOPPED_SAFETY)
        self.assertEqual(self.state.revision, before.revision)
        self.assertEqual(self.state.snapshot(0).safety_state, before.safety_state)

    def test_all_known_mission_states_have_a_projection(self):
        for mission in rss.MissionState:
            with self.subTest(mission=mission):
                self.state.update_states(mission_state=mission)
                axes = self.project()
                self.assertIsInstance(axes.operational_state, rss.OperationalState)
                self.assertIsInstance(axes.docking_state, rss.DockingState)
                self.assertTrue(axes.scan_state)


if __name__ == '__main__':
    unittest.main()
