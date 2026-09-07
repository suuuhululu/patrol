"""Deterministic E-stop guard tests; no robot or ROS graph required."""

import importlib.util
from pathlib import Path
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / 'src/patrol_amr/'
          'patrol_amr/estop_guard.py')
SPEC = importlib.util.spec_from_file_location('estop_guard', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
V = MODULE.EStopVerdict
C = MODULE.EStopCause


def guard():
    return MODULE.EStopGuard()


def observe(
    g,
    active=True,
    cause=C.OPERATOR,
    physical=False,
    source='test',
    sequence=1,
    activated_at=0.0,
    release_started=0.0,
):
    return g.observe(
        active, cause, physical, source, sequence, activated_at, release_started
    )


class TimeConversionTests(unittest.TestCase):
    def test_time_to_seconds(self):
        self.assertEqual(MODULE.time_to_seconds(1, 0), 1.0)
        self.assertAlmostEqual(MODULE.time_to_seconds(0, 250_000_000), 0.25)

    def test_time_to_seconds_rejects_non_int(self):
        for sec, nanosec in ((1.0, 0), (0, 1.5), (True, 0), (0, False)):
            with self.subTest(sec=sec, nanosec=nanosec):
                with self.assertRaises(ValueError):
                    MODULE.time_to_seconds(sec, nanosec)


class DefaultStateTests(unittest.TestCase):
    def test_defaults_to_stopped_before_any_message(self):
        g = guard()
        self.assertTrue(g.stopped)
        self.assertIs(g.cause, C.UNKNOWN)
        self.assertFalse(g.physical)
        self.assertEqual(g.source, '')
        self.assertIsNone(g.last_sequence)
        self.assertIsNone(g.activated_at_seconds)
        self.assertIsNone(g.release_condition_started_at_seconds)


class ReflectionTests(unittest.TestCase):
    def test_active_true_is_reflected_immediately(self):
        g = guard()
        self.assertIs(
            observe(g, active=True, cause=C.OBSTACLE, sequence=1), V.ACCEPTED
        )
        self.assertTrue(g.stopped)
        self.assertIs(g.cause, C.OBSTACLE)

    def test_active_false_is_reflected_immediately(self):
        g = guard()
        observe(g, active=True, sequence=1)
        self.assertIs(observe(g, active=False, sequence=2), V.ACCEPTED)
        self.assertFalse(g.stopped)

    def test_physical_and_source_are_reflected(self):
        g = guard()
        observe(g, physical=True, source='estop_button_1', sequence=1)
        self.assertTrue(g.physical)
        self.assertEqual(g.source, 'estop_button_1')

    def test_timestamps_are_reflected_as_given(self):
        g = guard()
        observe(g, activated_at=12.5, release_started=0.0, sequence=1)
        self.assertEqual(g.activated_at_seconds, 12.5)
        self.assertEqual(g.release_condition_started_at_seconds, 0.0)

    def test_unrecognized_cause_still_updates_active(self):
        g = guard()
        # 향후 확장된 cause 값도 active 반영을 막지 않는다 (안전 방향).
        verdict = g.observe(True, 99, False, 'future_node', 1, 0.0, 0.0)
        self.assertIs(verdict, V.ACCEPTED)
        self.assertTrue(g.stopped)
        self.assertEqual(g.cause, 99)


class SequenceTests(unittest.TestCase):
    def test_first_observation_is_accepted_regardless_of_sequence_value(self):
        g = guard()
        self.assertIs(observe(g, sequence=500), V.ACCEPTED)
        self.assertEqual(g.last_sequence, 500)

    def test_stale_or_duplicate_sequence_is_discarded(self):
        g = guard()
        observe(g, active=True, sequence=10)
        for sequence in (0, 5, 10):
            with self.subTest(sequence=sequence):
                self.assertIs(
                    observe(g, active=False, sequence=sequence), V.STALE_SEQUENCE
                )
        # 폐기된 메시지는 상태를 바꾸지 않는다: active=False 시도가 무시됐다.
        self.assertTrue(g.stopped)
        self.assertEqual(g.last_sequence, 10)

    def test_newer_sequence_is_accepted(self):
        g = guard()
        observe(g, active=True, sequence=10)
        self.assertIs(observe(g, active=False, sequence=11), V.ACCEPTED)
        self.assertFalse(g.stopped)

    def test_uint32_max_sequence_is_accepted(self):
        g = guard()
        self.assertIs(observe(g, sequence=MODULE.SEQUENCE_MAX), V.ACCEPTED)


class TransitionDetectionTests(unittest.TestCase):
    """observe() 는 로그 이름을 반환하지 않는다; 호출자가 stopped 를 비교한다."""

    def test_activation_transition_is_observable_via_stopped(self):
        g = guard()
        # 기본값이 이미 정지이므로, 먼저 명시적으로 해제해 두고 시작한다.
        observe(g, active=False, sequence=1)
        before = g.stopped
        observe(g, active=True, cause=C.PHYSICAL_BUTTON, sequence=2)
        after = g.stopped
        self.assertFalse(before)
        self.assertTrue(after)

    def test_release_transition_is_observable_via_stopped(self):
        g = guard()
        observe(g, active=True, sequence=1)
        before = g.stopped
        observe(g, active=False, sequence=2)
        after = g.stopped
        self.assertTrue(before)
        self.assertFalse(after)

    def test_repeated_active_true_is_not_a_new_transition(self):
        g = guard()
        observe(g, active=True, sequence=1)
        before = g.stopped
        observe(g, active=True, sequence=2)
        after = g.stopped
        self.assertTrue(before)
        self.assertTrue(after)


class CallerErrorTests(unittest.TestCase):
    def test_invalid_argument_types_raise(self):
        g = guard()
        bad = [
            dict(active=1),
            dict(cause=1.0),
            dict(cause=True),
            dict(cause=-1),
            dict(cause=MODULE.CAUSE_MAX + 1),
            dict(physical='true'),
            dict(source=123),
            dict(sequence=1.5),
            dict(sequence=True),
            dict(sequence=-1),
            dict(sequence=MODULE.SEQUENCE_MAX + 1),
            dict(activated_at=float('nan')),
            dict(activated_at=None),
            dict(release_started=float('inf')),
        ]
        for overrides in bad:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    observe(g, **overrides)

    def test_rejected_observation_does_not_advance_sequence(self):
        g = guard()
        observe(g, sequence=5)
        with self.assertRaises(ValueError):
            observe(g, cause=-1, sequence=6)
        self.assertEqual(g.last_sequence, 5)


if __name__ == '__main__':
    unittest.main()
