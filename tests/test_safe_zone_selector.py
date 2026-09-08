"""Q-08 safe-zone candidate selection tests."""

from pathlib import Path
import sys
import unittest


PATROL_AMR_PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / 'src/patrol_amr'
)
sys.path.insert(0, str(PATROL_AMR_PACKAGE_ROOT))

from patrol_amr import safe_zone_selector as MODULE  # noqa: E402


def candidate(candidate_id='safe-a', **overrides):
    values = {
        'candidate_id': candidate_id,
        'pose': MODULE.MapPose(1.0, 2.0, 0.0),
        'free_cell': True,
        'inside_keepout': False,
        'obstacle_clearance_m': 0.5,
        'vehicle_path_clearance_m': 1.0,
        'path_available': True,
        'overlaps_other_amr': False,
        'path_cost': 10.0,
    }
    values.update(overrides)
    return MODULE.SafeZoneCandidate(**values)


class ContractGateTests(unittest.TestCase):
    def test_exact_q08_distance_boundaries_are_eligible(self):
        self.assertEqual(MODULE.rejection_reasons(candidate()), ())

    def test_every_q08_gate_has_a_distinct_rejection(self):
        cases = (
            ({'pose': MODULE.MapPose(1, 2, 0, 'odom')}, MODULE.RejectionReason.NOT_MAP_FRAME),
            ({'free_cell': False}, MODULE.RejectionReason.NOT_FREE_CELL),
            ({'inside_keepout': True}, MODULE.RejectionReason.INSIDE_KEEPOUT),
            ({'obstacle_clearance_m': 0.499}, MODULE.RejectionReason.OBSTACLE_CLEARANCE),
            ({'vehicle_path_clearance_m': 0.999}, MODULE.RejectionReason.VEHICLE_PATH_CLEARANCE),
            ({'path_available': False}, MODULE.RejectionReason.PATH_UNAVAILABLE),
            ({'overlaps_other_amr': True}, MODULE.RejectionReason.OTHER_AMR_OVERLAP),
        )
        for change, reason in cases:
            with self.subTest(reason=reason):
                self.assertIn(reason, MODULE.rejection_reasons(candidate(**change)))

    def test_all_reasons_are_reported_together(self):
        item = candidate(
            pose=MODULE.MapPose(0, 0, 0, 'odom'), free_cell=False,
            inside_keepout=True, obstacle_clearance_m=0,
            vehicle_path_clearance_m=0, path_available=False,
            overlaps_other_amr=True,
        )
        self.assertEqual(len(MODULE.rejection_reasons(item)), 7)


class SelectionTests(unittest.TestCase):
    def test_vehicle_clearance_is_ranked_before_path_cost(self):
        near = candidate('near', vehicle_path_clearance_m=1.1, path_cost=1)
        far = candidate('far', vehicle_path_clearance_m=2.0, path_cost=100)
        self.assertEqual(MODULE.select_safe_zone((near, far)).selected, far)

    def test_path_cost_then_id_break_ties_deterministically(self):
        costly = candidate('costly', vehicle_path_clearance_m=2, path_cost=3)
        beta = candidate('beta', vehicle_path_clearance_m=2, path_cost=1)
        alpha = candidate('alpha', vehicle_path_clearance_m=2, path_cost=1)
        decision = MODULE.select_safe_zone((costly, beta, alpha))
        self.assertEqual(decision.selected, alpha)
        self.assertEqual(decision.eligible_ids, ('alpha', 'beta', 'costly'))

    def test_ineligible_candidates_are_never_selected(self):
        invalid = candidate('invalid', vehicle_path_clearance_m=9, inside_keepout=True)
        valid = candidate('valid', vehicle_path_clearance_m=1)
        self.assertEqual(MODULE.select_safe_zone((invalid, valid)).selected, valid)

    def test_no_candidate_returns_fixed_failure_without_pose(self):
        decision = MODULE.select_safe_zone(())
        self.assertIsNone(decision.selected)
        self.assertEqual(decision.reason_code, MODULE.SAFE_ZONE_NOT_FOUND)
        self.assertEqual(decision.reason, 'SAFE_ZONE_NOT_FOUND')

    def test_duplicate_ids_and_invalid_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.select_safe_zone((candidate(), candidate()))
        with self.assertRaises(ValueError):
            MODULE.select_safe_zone('safe-a')


class ValueValidationTests(unittest.TestCase):
    def test_pose_and_measurements_must_be_finite(self):
        with self.assertRaises(ValueError):
            MODULE.MapPose(float('nan'), 0, 0)
        with self.assertRaises(ValueError):
            candidate(path_cost=float('inf'))
        with self.assertRaises(ValueError):
            candidate(obstacle_clearance_m=-0.1)

    def test_boolean_evidence_must_be_boolean(self):
        with self.assertRaises(ValueError):
            candidate(free_cell=1)


if __name__ == '__main__':
    unittest.main()
