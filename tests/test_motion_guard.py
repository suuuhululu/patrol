"""Deterministic motion guard tests; no robot or ROS graph required."""

import importlib.util
from pathlib import Path
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / 'src/patrol_amr/'
          'patrol_amr/motion_guard.py')
SPEC = importlib.util.spec_from_file_location('motion_guard', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
R = MODULE.MotionBlockReason

CANDIDATE = (0.3, -0.1)


def guard():
    return MODULE.MotionGuard()


class GateTests(unittest.TestCase):
    def test_both_permit_passes_candidate_through_unchanged(self):
        g = guard()
        output, reasons = g.evaluate(True, False, CANDIDATE)
        self.assertEqual(output, CANDIDATE)
        self.assertEqual(reasons, frozenset())

    def test_missing_drive_token_forces_stop(self):
        g = guard()
        output, reasons = g.evaluate(False, False, CANDIDATE)
        self.assertEqual(output, MODULE.STOP)
        self.assertEqual(reasons, frozenset({R.DRIVE_TOKEN_NOT_GRANTED}))

    def test_active_estop_forces_stop(self):
        g = guard()
        output, reasons = g.evaluate(True, True, CANDIDATE)
        self.assertEqual(output, MODULE.STOP)
        self.assertEqual(reasons, frozenset({R.ESTOP_ACTIVE}))

    def test_both_blocking_reports_both_reasons(self):
        g = guard()
        output, reasons = g.evaluate(False, True, CANDIDATE)
        self.assertEqual(output, MODULE.STOP)
        self.assertEqual(
            reasons, frozenset({R.DRIVE_TOKEN_NOT_GRANTED, R.ESTOP_ACTIVE})
        )

    def test_stop_output_is_exactly_zero(self):
        g = guard()
        output, _ = g.evaluate(False, False, CANDIDATE)
        self.assertEqual(output, (0.0, 0.0))

    def test_candidate_values_are_returned_as_float(self):
        g = guard()
        output, _ = g.evaluate(True, False, (1, -2))
        self.assertEqual(output, (1.0, -2.0))
        self.assertIsInstance(output[0], float)
        self.assertIsInstance(output[1], float)

    def test_stateless_across_calls(self):
        g = guard()
        g.evaluate(False, True, CANDIDATE)
        # 이전 호출의 차단 사유가 다음 호출에 남지 않는다.
        output, reasons = g.evaluate(True, False, CANDIDATE)
        self.assertEqual(output, CANDIDATE)
        self.assertEqual(reasons, frozenset())


class CallerErrorTests(unittest.TestCase):
    def test_non_bool_flags_raise(self):
        g = guard()
        for drive, estop in ((1, False), (True, 0), (None, False), (True, 'x')):
            with self.subTest(drive=drive, estop=estop):
                with self.assertRaises(ValueError):
                    g.evaluate(drive, estop, CANDIDATE)

    def test_malformed_candidate_raises(self):
        g = guard()
        bad = [
            [0.1, 0.2],          # list, not tuple
            (0.1,),               # wrong length
            (0.1, 0.2, 0.3),      # wrong length
            (True, 0.0),          # bool disguised as number
            (0.0, True),
            ('0.1', 0.2),
            (float('nan'), 0.0),
            (0.0, float('inf')),
            None,
        ]
        for candidate in bad:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    g.evaluate(True, False, candidate)

    def test_int_candidate_components_are_accepted(self):
        g = guard()
        output, _ = g.evaluate(True, False, (0, 0))
        self.assertEqual(output, (0.0, 0.0))


if __name__ == '__main__':
    unittest.main()
