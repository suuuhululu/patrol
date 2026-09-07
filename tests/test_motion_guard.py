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
FRESH = 0.0
MAX_AGE = MODULE.CANDIDATE_MAX_AGE_SECONDS


def guard():
    return MODULE.MotionGuard()


class GateTests(unittest.TestCase):
    def test_all_permit_passes_candidate_through_unchanged(self):
        g = guard()
        output, reasons = g.evaluate(True, False, CANDIDATE, FRESH)
        self.assertEqual(output, CANDIDATE)
        self.assertEqual(reasons, frozenset())

    def test_missing_drive_token_forces_stop(self):
        g = guard()
        output, reasons = g.evaluate(False, False, CANDIDATE, FRESH)
        self.assertEqual(output, MODULE.STOP)
        self.assertEqual(reasons, frozenset({R.DRIVE_TOKEN_NOT_GRANTED}))

    def test_active_estop_forces_stop(self):
        g = guard()
        output, reasons = g.evaluate(True, True, CANDIDATE, FRESH)
        self.assertEqual(output, MODULE.STOP)
        self.assertEqual(reasons, frozenset({R.ESTOP_ACTIVE}))

    def test_both_permission_reasons_reported(self):
        g = guard()
        output, reasons = g.evaluate(False, True, CANDIDATE, FRESH)
        self.assertEqual(output, MODULE.STOP)
        self.assertEqual(
            reasons, frozenset({R.DRIVE_TOKEN_NOT_GRANTED, R.ESTOP_ACTIVE})
        )

    def test_every_reason_can_apply_at_once(self):
        g = guard()
        output, reasons = g.evaluate(False, True, CANDIDATE, MAX_AGE + 0.1)
        self.assertEqual(output, MODULE.STOP)
        self.assertEqual(
            reasons,
            frozenset({
                R.DRIVE_TOKEN_NOT_GRANTED,
                R.ESTOP_ACTIVE,
                R.CANDIDATE_STALE,
            }),
        )

    def test_stop_output_is_exactly_zero(self):
        g = guard()
        output, _ = g.evaluate(False, False, CANDIDATE, FRESH)
        self.assertEqual(output, (0.0, 0.0))

    def test_candidate_values_are_returned_as_float(self):
        g = guard()
        output, _ = g.evaluate(True, False, (1, -2), FRESH)
        self.assertEqual(output, (1.0, -2.0))
        self.assertIsInstance(output[0], float)
        self.assertIsInstance(output[1], float)

    def test_stateless_across_calls(self):
        g = guard()
        g.evaluate(False, True, CANDIDATE, MAX_AGE + 1.0)
        # 이전 호출의 차단 사유가 다음 호출에 남지 않는다.
        output, reasons = g.evaluate(True, False, CANDIDATE, FRESH)
        self.assertEqual(output, CANDIDATE)
        self.assertEqual(reasons, frozenset())


class CandidateFreshnessTests(unittest.TestCase):
    """Q-17 후보 신선도 (TBD-IF-009, 2026-09-08 AMR 확정 0.5초)."""

    def test_agreed_limit_is_the_drive_base_timeout(self):
        # 구동부 diffdrive_controller 의 cmd_vel_timeout 과 같은 값이다.
        self.assertEqual(MAX_AGE, 0.5)

    def test_just_under_limit_is_fresh(self):
        g = guard()
        output, reasons = g.evaluate(True, False, CANDIDATE, MAX_AGE - 0.001)
        self.assertEqual(output, CANDIDATE)
        self.assertEqual(reasons, frozenset())

    def test_exactly_at_limit_is_fresh(self):
        # Q-17 은 "0.5초를 넘으면" 정지다. 경계값 자체는 통과한다.
        g = guard()
        output, reasons = g.evaluate(True, False, CANDIDATE, MAX_AGE)
        self.assertEqual(output, CANDIDATE)
        self.assertEqual(reasons, frozenset())

    def test_just_over_limit_is_stale(self):
        g = guard()
        output, reasons = g.evaluate(True, False, CANDIDATE, MAX_AGE + 0.001)
        self.assertEqual(output, MODULE.STOP)
        self.assertEqual(reasons, frozenset({R.CANDIDATE_STALE}))

    def test_missing_candidate_blocks_with_its_own_reason(self):
        g = guard()
        output, reasons = g.evaluate(True, False, None, None)
        self.assertEqual(output, MODULE.STOP)
        self.assertEqual(reasons, frozenset({R.CANDIDATE_MISSING}))

    def test_missing_and_stale_are_distinct_reasons(self):
        g = guard()
        _, missing = g.evaluate(True, False, None, None)
        _, stale = g.evaluate(True, False, CANDIDATE, MAX_AGE + 1.0)
        self.assertNotEqual(missing, stale)

    def test_future_stamp_is_not_treated_as_stale(self):
        # 같은 PC·같은 시계이므로 음수 age 는 시계 역행이며, 허용 폭을 정한
        # 문서가 없어 임의 임계값을 만들지 않았다.
        g = guard()
        output, reasons = g.evaluate(True, False, CANDIDATE, -0.25)
        self.assertEqual(output, CANDIDATE)
        self.assertEqual(reasons, frozenset())

    def test_stale_candidate_still_reports_permission_reasons(self):
        g = guard()
        _, reasons = g.evaluate(False, False, CANDIDATE, MAX_AGE + 1.0)
        self.assertEqual(
            reasons,
            frozenset({R.DRIVE_TOKEN_NOT_GRANTED, R.CANDIDATE_STALE}),
        )


class BlockedReasonsTests(unittest.TestCase):
    """candidate 없이 권한만 묻는 경로 (6단계 신선도 재확인용)."""

    def test_matches_evaluate_for_all_permission_combinations(self):
        g = guard()
        for drive, estop in (
            (True, False), (False, False), (True, True), (False, True)
        ):
            with self.subTest(drive=drive, estop=estop):
                _, expected = g.evaluate(drive, estop, CANDIDATE, FRESH)
                self.assertEqual(g.blocked_reasons(drive, estop), expected)

    def test_no_candidate_required(self):
        g = guard()
        self.assertEqual(g.blocked_reasons(True, False), frozenset())
        self.assertEqual(
            g.blocked_reasons(False, True),
            frozenset({R.DRIVE_TOKEN_NOT_GRANTED, R.ESTOP_ACTIVE}),
        )

    def test_candidate_freshness_does_not_affect_permission(self):
        # motion_allowed 가 Nav2 후보 유무에 따라 흔들리지 않아야 한다.
        g = guard()
        self.assertEqual(g.blocked_reasons(True, False), frozenset())
        _, reasons = g.evaluate(True, False, None, None)
        self.assertEqual(reasons, frozenset({R.CANDIDATE_MISSING}))

    def test_non_bool_flags_raise(self):
        g = guard()
        with self.assertRaises(ValueError):
            g.blocked_reasons(1, False)
        with self.assertRaises(ValueError):
            g.blocked_reasons(True, 0)


class CallerErrorTests(unittest.TestCase):
    def test_non_bool_flags_raise(self):
        g = guard()
        for drive, estop in ((1, False), (True, 0), (None, False), (True, 'x')):
            with self.subTest(drive=drive, estop=estop):
                with self.assertRaises(ValueError):
                    g.evaluate(drive, estop, CANDIDATE, FRESH)

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
        ]
        for candidate in bad:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    g.evaluate(True, False, candidate, FRESH)

    def test_malformed_candidate_age_raises(self):
        g = guard()
        bad = [True, False, '0.1', float('nan'), float('inf'), object()]
        for age in bad:
            with self.subTest(age=age):
                with self.assertRaises(ValueError):
                    g.evaluate(True, False, CANDIDATE, age)

    def test_candidate_and_age_must_be_paired(self):
        g = guard()
        with self.assertRaises(ValueError):
            g.evaluate(True, False, CANDIDATE, None)
        with self.assertRaises(ValueError):
            g.evaluate(True, False, None, FRESH)

    def test_int_candidate_components_are_accepted(self):
        g = guard()
        output, _ = g.evaluate(True, False, (0, 0), FRESH)
        self.assertEqual(output, (0.0, 0.0))

    def test_int_candidate_age_is_accepted(self):
        g = guard()
        output, reasons = g.evaluate(True, False, CANDIDATE, 0)
        self.assertEqual(output, CANDIDATE)
        self.assertEqual(reasons, frozenset())


if __name__ == '__main__':
    unittest.main()
