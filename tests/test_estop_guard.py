"""Deterministic E-stop guard tests; no ROS graph required."""

import importlib.util
from pathlib import Path
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / 'src/patrol_amr_safety/'
          'patrol_amr_safety/estop_guard.py')
SPEC = importlib.util.spec_from_file_location('estop_guard', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
V = MODULE.EStopVerdict


def guard(robot_id='robot1'):
    return MODULE.EStopGuard(robot_id)


def observe(
    g,
    target_robot_id=None,
    active=True,
    reason=1,
    sequence=1,
):
    return g.observe(target_robot_id or g.robot_id, active, reason, sequence)


class DefaultTests(unittest.TestCase):
    def test_defaults_to_stopped_before_any_message(self):
        g = guard()
        self.assertTrue(g.stopped)
        self.assertIsNone(g.reason)
        self.assertIsNone(g.last_sequence)

    def test_robot_id_must_be_known(self):
        for value in ('robot2', '', None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    guard(value)


class ReflectionTests(unittest.TestCase):
    def test_active_and_release_are_reflected(self):
        g = guard()
        self.assertIs(observe(g, active=True, sequence=1), V.ACCEPTED)
        self.assertTrue(g.stopped)
        self.assertIs(observe(g, active=False, sequence=2), V.ACCEPTED)
        self.assertFalse(g.stopped)

    def test_reason_uses_confirmed_enum_range(self):
        g = guard()
        observe(g, reason=6)
        self.assertEqual(g.reason, 6)

    def test_all_target_applies_to_both_robots(self):
        for robot_id in MODULE.ROBOT_IDS:
            with self.subTest(robot_id=robot_id):
                g = guard(robot_id)
                self.assertIs(
                    observe(g, target_robot_id='all', active=False),
                    V.ACCEPTED,
                )
                self.assertFalse(g.stopped)

class TargetTests(unittest.TestCase):
    def test_other_robot_target_is_not_applied(self):
        g = guard('robot1')
        verdict = observe(g, target_robot_id='robot6', active=False)
        self.assertIs(verdict, V.OTHER_TARGET)
        self.assertTrue(g.stopped)
        self.assertEqual(g.last_sequence, 1)


class SequenceTests(unittest.TestCase):
    def test_stale_or_duplicate_sequence_is_discarded(self):
        g = guard()
        observe(g, active=True, sequence=10)
        for sequence in (1, 9, 10):
            with self.subTest(sequence=sequence):
                self.assertIs(
                    observe(g, active=False, sequence=sequence),
                    V.STALE_SEQUENCE,
                )
        self.assertTrue(g.stopped)

    def test_other_target_still_advances_common_stream_floor(self):
        g = guard('robot1')
        observe(g, target_robot_id='robot6', sequence=5)
        self.assertIs(observe(g, sequence=4), V.STALE_SEQUENCE)

    def test_uint64_max_is_accepted(self):
        g = guard()
        self.assertIs(observe(g, sequence=MODULE.UINT64_MAX), V.ACCEPTED)


class CallerErrorTests(unittest.TestCase):
    def test_invalid_arguments_raise_without_advancing_sequence(self):
        cases = (
            ('', True, 0, 1),
            ('robot1', 1, 0, 1),
            ('robot1', True, -1, 1),
            ('robot1', True, 7, 1),
            ('robot1', True, 0, 0),
            ('robot1', True, 0, True),
        )
        for args in cases:
            with self.subTest(args=args):
                g = guard()
                with self.assertRaises(ValueError):
                    g.observe(*args)
                self.assertIsNone(g.last_sequence)


if __name__ == '__main__':
    unittest.main()
