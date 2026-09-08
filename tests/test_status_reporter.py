"""Pure status_reporter tests; no ROS graph required."""

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


PATROL_AMR_PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / 'src/patrol_amr_safety'
)
sys.path.insert(0, str(PATROL_AMR_PACKAGE_ROOT))

from patrol_amr_safety import status_reporter as MODULE  # noqa: E402


def pose_payload(value=0.0):
    return SimpleNamespace(
        pose=SimpleNamespace(
            position=SimpleNamespace(x=value, y=0.0, z=0.0),
            orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
        ),
        covariance=[0.0] * 36,
    )


class PosePayloadTests(unittest.TestCase):
    def test_finite_pose_and_covariance_are_accepted(self):
        self.assertTrue(MODULE.pose_payload_is_finite(pose_payload()))

    def test_nonfinite_position_is_rejected(self):
        self.assertFalse(
            MODULE.pose_payload_is_finite(pose_payload(float('nan')))
        )

    def test_nonfinite_orientation_is_rejected(self):
        payload = pose_payload()
        payload.pose.orientation.w = float('inf')
        self.assertFalse(MODULE.pose_payload_is_finite(payload))

    def test_nonfinite_covariance_is_rejected(self):
        payload = pose_payload()
        payload.covariance[12] = float('nan')
        self.assertFalse(MODULE.pose_payload_is_finite(payload))


class AcceptedTokenFieldTests(unittest.TestCase):
    def test_nonempty_id_is_valid(self):
        self.assertEqual(
            MODULE.accepted_token_fields('tok-a'), ('tok-a', True)
        )

    def test_empty_id_is_invalid(self):
        self.assertEqual(MODULE.accepted_token_fields(''), ('', False))

    def test_non_string_is_rejected(self):
        for value in (None, True, 1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    MODULE.accepted_token_fields(value)


class ConfigurationTests(unittest.TestCase):
    def test_valid_explicit_configuration(self):
        MODULE.validate_configuration(
            'robot1', 'robot1-20260907T120000', 200
        )

    def test_invalid_configuration_is_rejected(self):
        cases = (
            ('robot2', 'robot1-20260907T120000', 0),
            ('robot1', '', 0),
            ('robot1', 'session', -1),
            ('robot1', 'session', 256),
            ('robot1', 'session', True),
        )
        for args in cases:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    MODULE.validate_configuration(*args)


class PublicationGateTests(unittest.TestCase):
    def test_first_publication_is_immediately_due(self):
        self.assertTrue(MODULE.PublicationGate().due(0.0))

    def test_unchanged_status_is_periodic_at_two_hz(self):
        gate = MODULE.PublicationGate()
        gate.mark_published(0.0)
        self.assertFalse(gate.due(0.499999))
        self.assertTrue(gate.due(0.5))

    def test_change_waits_for_ten_hz_limit(self):
        gate = MODULE.PublicationGate()
        gate.mark_published(0.0)
        gate.note_change()
        self.assertFalse(gate.due(0.099999))
        self.assertTrue(gate.due(0.1))

    def test_publication_clears_pending_change(self):
        gate = MODULE.PublicationGate()
        gate.mark_published(0.0)
        gate.note_change()
        gate.mark_published(0.1)
        self.assertFalse(gate.due(0.2))
        self.assertTrue(gate.due(0.6))

    def test_bad_or_backward_times_are_rejected(self):
        gate = MODULE.PublicationGate()
        gate.mark_published(2.0)
        for value in (1.9, None, True, float('nan'), float('inf')):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    gate.due(value)


class StatusSequenceTests(unittest.TestCase):
    def test_sequence_starts_at_one_and_increases(self):
        sequence = MODULE.StatusSequence()
        self.assertEqual(sequence.next(), 1)
        self.assertEqual(sequence.next(), 2)

    def test_sequence_refuses_uint64_overflow(self):
        sequence = MODULE.StatusSequence()
        sequence._value = MODULE.UINT64_MAX
        with self.assertRaises(OverflowError):
            sequence.next()


if __name__ == '__main__':
    unittest.main()
