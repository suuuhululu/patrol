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
    reason=17,
    latched=False,
    sequence=1,
):
    return g.observe(
        target_robot_id or g.robot_id, active, reason, latched, sequence
    )


class DefaultTests(unittest.TestCase):
    def test_defaults_to_stopped_before_any_message(self):
        g = guard()
        self.assertTrue(g.stopped)
        self.assertIsNone(g.reason)
        self.assertFalse(g.latched)
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

    def test_reason_is_opaque_uint8_and_latched_is_reflected(self):
        g = guard()
        observe(g, reason=240, latched=True)
        self.assertEqual(g.reason, 240)
        self.assertTrue(g.latched)

    def test_latched_true_keeps_stop_even_when_active_is_false(self):
        g = guard()
        observe(g, active=False, latched=True)
        self.assertTrue(g.stopped)


class LocalLatchTests(unittest.TestCase):
    """15단계. Q-10: 물리 E-stop 은 수동 reset 까지 latch."""

    def test_incoming_message_cannot_clear_the_local_latch(self):
        # 관제가 latched=false 로 되돌려도 로컬 latch 는 내려가지 않는다.
        # 이것이 arbiter 를 그대로 비추는 것과 방어적 latch 의 차이다.
        g = guard()
        observe(g, active=False, latched=True)
        observe(g, active=False, latched=False, sequence=2)
        self.assertFalse(g.latched)
        self.assertTrue(g.local_latch)
        self.assertTrue(g.stopped)

    def test_reset_is_the_only_way_out(self):
        g = guard()
        observe(g, active=False, latched=True)
        observe(g, active=False, latched=False, sequence=2)
        self.assertTrue(g.reset_local_latch())
        self.assertFalse(g.local_latch)
        self.assertFalse(g.stopped)

    def test_reset_reports_whether_it_had_anything_to_clear(self):
        g = guard()
        self.assertFalse(g.reset_local_latch())
        observe(g, active=False, latched=True)
        self.assertTrue(g.reset_local_latch())
        self.assertFalse(g.reset_local_latch())

    def test_reset_does_not_release_an_active_estop(self):
        # latch 만 내릴 뿐 활성 E-stop 을 해제하지 않는다.
        g = guard()
        observe(g, active=True, latched=True)
        g.reset_local_latch()
        self.assertTrue(g.stopped)

    def test_reset_alone_does_not_override_the_arbiters_latched_flag(self):
        # reset 은 로컬 latch 만 내린다. arbiter 가 여전히 latched 를
        # 주장하면 정지는 유지된다 -- 둘 중 하나만 풀어도 움직이지 않는다.
        g = guard()
        observe(g, active=False, latched=True)
        g.reset_local_latch()
        self.assertFalse(g.local_latch)
        self.assertTrue(g.latched)
        self.assertTrue(g.stopped)

    def test_latch_reengages_on_a_later_latched_message(self):
        g = guard()
        observe(g, active=False, latched=True)
        observe(g, active=False, latched=False, sequence=2)
        g.reset_local_latch()
        self.assertFalse(g.stopped)
        observe(g, active=False, latched=True, sequence=3)
        self.assertTrue(g.local_latch)
        self.assertTrue(g.stopped)

    def test_other_robots_latched_message_does_not_engage_it(self):
        g = guard('robot1')
        observe(g, target_robot_id='robot6', active=True, latched=True)
        self.assertFalse(g.local_latch)

    def test_stale_latched_message_does_not_engage_it(self):
        g = guard()
        observe(g, active=False, latched=False, sequence=5)
        observe(g, active=False, latched=True, sequence=3)
        self.assertFalse(g.local_latch)

    def test_never_latched_guard_reports_no_local_latch(self):
        g = guard()
        observe(g, active=False, latched=False)
        self.assertFalse(g.local_latch)
        self.assertFalse(g.stopped)

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
            ('', True, 0, False, 1),
            ('robot1', 1, 0, False, 1),
            ('robot1', True, -1, False, 1),
            ('robot1', True, 256, False, 1),
            ('robot1', True, 0, 0, 1),
            ('robot1', True, 0, False, 0),
            ('robot1', True, 0, False, True),
        )
        for args in cases:
            with self.subTest(args=args):
                g = guard()
                with self.assertRaises(ValueError):
                    g.observe(*args)
                self.assertIsNone(g.last_sequence)


if __name__ == '__main__':
    unittest.main()
