"""Deterministic RobotStatus state tests; no ROS graph required."""

import importlib.util
import math
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


class OdometryAxisTests(unittest.TestCase):
    """14단계. 네 상수 모두 interfaces.md 3절이 확정한 값이다."""

    LIN = MODULE.STOP_LINEAR_LIMIT
    ANG = MODULE.STOP_ANGULAR_LIMIT
    HOLD = MODULE.STOP_HOLD_SECONDS
    AGE = MODULE.ODOMETRY_MAX_AGE_SECONDS

    def state(self):
        return MODULE.RobotStatusState('robot1')

    def hold_still(self, state, start=0.0, until=None, step=0.1):
        """Feed in-limit samples from `start` through `until` inclusive."""
        until = self.HOLD if until is None else until
        t = start
        while t <= until + 1e-9:
            state.observe_odometry(0.0, 0.0, t)
            t = round(t + step, 6)
        return t - step

    def test_contract_values_match_interfaces_md(self):
        self.assertEqual(self.LIN, 0.05)
        self.assertEqual(self.ANG, 0.1)
        self.assertEqual(self.HOLD, 0.5)
        self.assertEqual(self.AGE, 0.5)

    def test_no_odometry_reports_nan_not_zero(self):
        snapshot = self.state().snapshot(0.0)
        self.assertTrue(math.isnan(snapshot.linear_velocity))
        self.assertTrue(math.isnan(snapshot.angular_velocity))
        self.assertFalse(snapshot.motion_stopped)

    def test_measured_velocity_is_reported(self):
        state = self.state()
        state.observe_odometry(0.4, -0.2, 1.0)
        snapshot = state.snapshot(1.1)
        self.assertAlmostEqual(snapshot.linear_velocity, 0.4)
        self.assertAlmostEqual(snapshot.angular_velocity, -0.2)
        self.assertFalse(snapshot.motion_stopped)

    def test_stop_requires_the_full_hold_window(self):
        state = self.state()
        self.hold_still(state, 0.0, self.HOLD - 0.1)
        self.assertFalse(state.snapshot(self.HOLD).motion_stopped)
        state.observe_odometry(0.0, 0.0, self.HOLD)
        self.assertTrue(state.snapshot(self.HOLD).motion_stopped)

    def test_moving_sample_reopens_the_hold_window(self):
        state = self.state()
        self.hold_still(state, 0.0, self.HOLD)
        self.assertTrue(state.snapshot(self.HOLD).motion_stopped)
        state.observe_odometry(0.3, 0.0, self.HOLD + 0.1)
        self.assertFalse(state.snapshot(self.HOLD + 0.1).motion_stopped)
        state.observe_odometry(0.0, 0.0, self.HOLD + 0.2)
        self.assertFalse(state.snapshot(self.HOLD + 0.2).motion_stopped)

    def test_limits_are_inclusive(self):
        state = self.state()
        for t in (0.0, 0.2, 0.4, 0.5):
            state.observe_odometry(self.LIN, self.ANG, t)
        self.assertTrue(state.snapshot(0.5).motion_stopped)

    def test_just_over_either_limit_is_not_stopped(self):
        for linear, angular in (
            (self.LIN + 0.001, 0.0),
            (0.0, self.ANG + 0.001),
            (-self.LIN - 0.001, 0.0),
            (0.0, -self.ANG - 0.001),
        ):
            with self.subTest(linear=linear, angular=angular):
                state = self.state()
                for t in (0.0, 0.2, 0.4, 0.5):
                    state.observe_odometry(linear, angular, t)
                self.assertFalse(state.snapshot(0.5).motion_stopped)

    def test_stale_odometry_is_not_stopped_and_reports_nan(self):
        state = self.state()
        self.hold_still(state, 0.0, self.HOLD)
        self.assertTrue(state.snapshot(self.HOLD).motion_stopped)
        snapshot = state.snapshot(self.HOLD + self.AGE + 0.001)
        self.assertFalse(snapshot.motion_stopped)
        self.assertTrue(math.isnan(snapshot.linear_velocity))
        self.assertTrue(math.isnan(snapshot.angular_velocity))

    def test_age_boundary_is_inclusive(self):
        state = self.state()
        self.hold_still(state, 0.0, self.HOLD)
        self.assertTrue(state.snapshot(self.HOLD + self.AGE).motion_stopped)

    def test_gap_larger_than_max_age_reopens_the_hold_window(self):
        # 관측이 끊긴 구간은 연속 유지로 주장할 수 없다.
        state = self.state()
        state.observe_odometry(0.0, 0.0, 0.0)
        state.observe_odometry(0.0, 0.0, 10.0)
        self.assertFalse(state.snapshot(10.0).motion_stopped)
        self.hold_still(state, 10.1, 10.0 + self.HOLD + 0.1)
        self.assertTrue(state.snapshot(10.0 + self.HOLD + 0.1).motion_stopped)

    def test_backwards_timestamp_is_rejected(self):
        state = self.state()
        state.observe_odometry(0.0, 0.0, 5.0)
        with self.assertRaises(ValueError):
            state.observe_odometry(0.0, 0.0, 4.9)

    def test_non_finite_or_non_numeric_samples_rejected(self):
        state = self.state()
        bad = [
            (float('nan'), 0.0, 0.0),
            (0.0, float('inf'), 0.0),
            (True, 0.0, 0.0),
            (0.0, '0.1', 0.0),
            (0.0, 0.0, float('nan')),
            (0.0, 0.0, None),
        ]
        for linear, angular, measured_at in bad:
            with self.subTest(sample=(linear, angular, measured_at)):
                with self.assertRaises(ValueError):
                    state.observe_odometry(linear, angular, measured_at)

    def test_repeated_identical_sample_reports_no_change(self):
        state = self.state()
        self.assertTrue(state.observe_odometry(0.1, 0.0, 1.0))
        self.assertFalse(state.observe_odometry(0.1, 0.0, 1.0))

    def test_future_stamp_is_treated_as_fresh(self):
        # Q-17 과 같은 판단: 같은 시계이고 허용 역행 폭이 미정이다.
        state = self.state()
        self.hold_still(state, 0.0, self.HOLD)
        self.assertTrue(state.snapshot(self.HOLD - 0.2).motion_stopped)

    def test_commanded_stop_is_not_odometry_stop(self):
        # cmd_vel 이 0 인 것과 실제로 멈춘 것은 다르다. 이 모듈은 odometry
        # 만 본다 -- 관측이 없으면 정지라고 말하지 않는다.
        state = self.state()
        self.assertFalse(state.snapshot(100.0).motion_stopped)


if __name__ == '__main__':
    unittest.main()
