"""Deterministic RobotStatus state tests; no ROS graph required."""

import importlib.util
from pathlib import Path
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / 'src/patrol_amr/'
          'patrol_amr/robot_status_state.py')
SPEC = importlib.util.spec_from_file_location('robot_status_state', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

O = MODULE.OperationalState
M = MODULE.MissionState
D = MODULE.DockingState
B = MODULE.BatteryState


class DefaultStateTests(unittest.TestCase):
    def test_fail_unknown_defaults_do_not_claim_ready_or_valid_pose(self):
        state = MODULE.RobotStatusState('robot1')
        snapshot = state.snapshot(0.0)
        self.assertIs(snapshot.operational_state, O.OP_UNKNOWN)
        self.assertIs(snapshot.mission_state, M.MISSION_NONE)
        self.assertIs(snapshot.docking_state, D.DOCK_UNKNOWN)
        self.assertIs(snapshot.battery_state, B.UNKNOWN)
        self.assertIsNone(snapshot.safety_state)
        self.assertFalse(snapshot.pose_valid)
        self.assertIsNone(snapshot.pose)
        self.assertIsNone(snapshot.last_valid_pose)
        self.assertIsNone(snapshot.last_valid_pose_age)
        self.assertEqual(snapshot.revision, 0)

    def test_robot_id_is_restricted_to_configured_robots(self):
        for robot_id in ('robot2', '', 'ROBOT1', None):
            with self.subTest(robot_id=robot_id):
                with self.assertRaises(ValueError):
                    MODULE.RobotStatusState(robot_id)


class StateAxisTests(unittest.TestCase):
    def test_axes_change_independently(self):
        state = MODULE.RobotStatusState('robot6')
        self.assertTrue(state.update_states(mission_state=M.MISSION_PATROLLING))
        snapshot = state.snapshot(1.0)
        self.assertIs(snapshot.mission_state, M.MISSION_PATROLLING)
        self.assertIs(snapshot.operational_state, O.OP_UNKNOWN)
        self.assertIs(snapshot.docking_state, D.DOCK_UNKNOWN)
        self.assertIs(snapshot.battery_state, B.UNKNOWN)

    def test_one_call_changes_multiple_axes_once(self):
        state = MODULE.RobotStatusState('robot1')
        changed = state.update_states(
            operational_state=O.OP_CHARGING,
            mission_state=M.MISSION_DOCKING,
            docking_state=D.DOCK_DOCKED,
            battery_state=B.CHARGING,
        )
        self.assertTrue(changed)
        self.assertEqual(state.revision, 1)
        snapshot = state.snapshot(1.0)
        self.assertIs(snapshot.operational_state, O.OP_CHARGING)
        self.assertIs(snapshot.mission_state, M.MISSION_DOCKING)
        self.assertIs(snapshot.docking_state, D.DOCK_DOCKED)
        self.assertIs(snapshot.battery_state, B.CHARGING)

    def test_same_values_are_not_a_change(self):
        state = MODULE.RobotStatusState('robot1')
        self.assertFalse(state.update_states())
        self.assertFalse(state.update_states(mission_state=M.MISSION_NONE))
        self.assertEqual(state.revision, 0)

    def test_numeric_contract_values_are_accepted(self):
        state = MODULE.RobotStatusState('robot1')
        state.update_states(
            operational_state=3,
            mission_state=3,
            docking_state=3,
            battery_state=3,
        )
        snapshot = state.snapshot(0.0)
        self.assertIs(snapshot.operational_state, O.OP_MOVING)
        self.assertIs(snapshot.mission_state, M.MISSION_MOVING_TO_SAFE_ZONE)
        self.assertIs(snapshot.docking_state, D.DOCK_DOCKING)
        self.assertIs(snapshot.battery_state, B.NORMAL)

    def test_invalid_axis_does_not_partially_apply_valid_axis(self):
        state = MODULE.RobotStatusState('robot1')
        with self.assertRaises(ValueError):
            state.update_states(
                operational_state=O.OP_READY,
                mission_state=255,
            )
        snapshot = state.snapshot(0.0)
        self.assertIs(snapshot.operational_state, O.OP_UNKNOWN)
        self.assertIs(snapshot.mission_state, M.MISSION_NONE)
        self.assertEqual(snapshot.revision, 0)

    def test_safety_is_opaque_uint8_until_enum_is_agreed(self):
        state = MODULE.RobotStatusState('robot1')
        self.assertTrue(state.update_states(safety_state=200))
        self.assertEqual(state.snapshot(0.0).safety_state, 200)
        for value in (-1, 256, True, 1.0, None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    state.update_states(safety_state=value)

    def test_invalid_enum_values_are_rejected(self):
        calls = (
            {'operational_state': 7},
            {'mission_state': 11},
            {'docking_state': 6},
            {'battery_state': 7},
            {'battery_state': True},
        )
        for keyword in calls:
            with self.subTest(keyword=keyword):
                state = MODULE.RobotStatusState('robot1')
                with self.assertRaises(ValueError):
                    state.update_states(**keyword)


class PoseTests(unittest.TestCase):
    def test_valid_pose_becomes_current_and_last_valid(self):
        state = MODULE.RobotStatusState('robot1')
        pose = {'x': 1.0, 'covariance': [0.1]}
        self.assertTrue(state.observe_pose(pose, True, 10.0, 'map'))
        snapshot = state.snapshot(12.5)
        self.assertTrue(snapshot.pose_valid)
        self.assertEqual(snapshot.pose.value, pose)
        self.assertEqual(snapshot.last_valid_pose.value, pose)
        self.assertEqual(snapshot.last_valid_pose_age, 2.5)

    def test_invalid_pose_does_not_erase_last_valid_pose(self):
        state = MODULE.RobotStatusState('robot1')
        state.observe_pose('good-pose', True, 10.0, 'map')
        state.observe_pose(None, False)
        snapshot = state.snapshot(14.0)
        self.assertFalse(snapshot.pose_valid)
        self.assertIsNone(snapshot.pose)
        self.assertEqual(snapshot.last_valid_pose.value, 'good-pose')
        self.assertEqual(snapshot.last_valid_pose.measured_at, 10.0)
        self.assertEqual(snapshot.last_valid_pose_age, 4.0)

    def test_invalid_payload_can_be_reported_but_not_used_as_last_valid(self):
        state = MODULE.RobotStatusState('robot1')
        state.observe_pose('good', True, 5.0, 'map')
        state.observe_pose('bad-diagnostic-value', False, 7.0, 'map')
        snapshot = state.snapshot(9.0)
        self.assertFalse(snapshot.pose_valid)
        self.assertEqual(snapshot.pose.value, 'bad-diagnostic-value')
        self.assertEqual(snapshot.last_valid_pose.value, 'good')
        self.assertEqual(snapshot.last_valid_pose_age, 4.0)

    def test_repeated_pose_is_not_a_change(self):
        state = MODULE.RobotStatusState('robot1')
        self.assertTrue(state.observe_pose('pose', True, 2.0, 'map'))
        self.assertFalse(state.observe_pose('pose', True, 2.0, 'map'))
        self.assertEqual(state.revision, 1)

    def test_snapshot_and_input_are_copied(self):
        state = MODULE.RobotStatusState('robot1')
        pose = {'covariance': [1.0]}
        state.observe_pose(pose, True, 2.0, 'map')
        pose['covariance'][0] = 99.0
        first = state.snapshot(3.0)
        self.assertEqual(first.pose.value['covariance'], [1.0])
        first.pose.value['covariance'][0] = 88.0
        second = state.snapshot(3.0)
        self.assertEqual(second.pose.value['covariance'], [1.0])

    def test_invalid_pose_arguments_are_rejected(self):
        state = MODULE.RobotStatusState('robot1')
        cases = (
            ('pose', True, 1.0, 'odom'),
            (None, True, 1.0, 'map'),
            (None, False, 1.0, None),
            ('pose', True, float('nan'), 'map'),
            ('pose', 1, 1.0, 'map'),
        )
        for args in cases:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    state.observe_pose(*args)
        self.assertEqual(state.revision, 0)

    def test_snapshot_cannot_precede_last_valid_pose(self):
        state = MODULE.RobotStatusState('robot1')
        state.observe_pose('pose', True, 10.0, 'map')
        with self.assertRaises(ValueError):
            state.snapshot(9.999)

    def test_snapshot_time_must_be_finite_real_number(self):
        state = MODULE.RobotStatusState('robot1')
        for value in (True, None, float('nan'), float('inf')):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    state.snapshot(value)


if __name__ == '__main__':
    unittest.main()
