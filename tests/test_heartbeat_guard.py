"""AMR-20 control heartbeat freshness tests."""

from pathlib import Path
import sys
import unittest


PATROL_AMR_PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / 'src/patrol_amr'
)
sys.path.insert(0, str(PATROL_AMR_PACKAGE_ROOT))

from patrol_amr import heartbeat_guard as MODULE  # noqa: E402


V = MODULE.HeartbeatVerdict
S = MODULE.HeartbeatState


class FreshnessTests(unittest.TestCase):
    def test_missing_is_not_healthy(self):
        guard = MODULE.HeartbeatGuard()
        self.assertIs(guard.state(0.0), S.MISSING)
        self.assertFalse(guard.healthy(0.0))
        self.assertIsNone(guard.age(0.0))

    def test_accepted_heartbeat_is_healthy(self):
        guard = MODULE.HeartbeatGuard()
        self.assertIs(guard.observe('ctrl-a', 1, 10.0), V.ACCEPTED)
        self.assertIs(guard.state(10.2), S.HEALTHY)
        self.assertAlmostEqual(guard.age(10.2), 0.2)

    def test_exactly_one_second_is_still_healthy(self):
        guard = MODULE.HeartbeatGuard()
        guard.observe('ctrl-a', 1, 10.0)
        self.assertIs(guard.state(11.0), S.HEALTHY)

    def test_more_than_one_second_is_expired(self):
        guard = MODULE.HeartbeatGuard()
        guard.observe('ctrl-a', 1, 10.0)
        self.assertIs(guard.state(11.000001), S.EXPIRED)
        self.assertFalse(guard.healthy(11.000001))

    def test_increasing_sequence_renews_receive_time(self):
        guard = MODULE.HeartbeatGuard()
        guard.observe('ctrl-a', 1, 10.0)
        guard.observe('ctrl-a', 2, 10.8)
        self.assertIs(guard.state(11.7), S.HEALTHY)
        self.assertIs(guard.state(11.800001), S.EXPIRED)


class SessionAndSequenceTests(unittest.TestCase):
    def test_duplicate_and_reverse_sequence_do_not_refresh(self):
        for sequence in (5, 4):
            with self.subTest(sequence=sequence):
                guard = MODULE.HeartbeatGuard()
                guard.observe('ctrl-a', 5, 1.0)
                self.assertIs(
                    guard.observe('ctrl-a', sequence, 1.9),
                    V.STALE_SEQUENCE,
                )
                self.assertIs(guard.state(2.000001), S.EXPIRED)

    def test_new_control_session_resets_sequence_floor(self):
        guard = MODULE.HeartbeatGuard()
        guard.observe('ctrl-a', 99, 1.0)
        self.assertIs(guard.observe('ctrl-b', 1, 1.1), V.ACCEPTED)
        self.assertEqual(guard.control_session_id, 'ctrl-b')
        self.assertEqual(guard.last_sequence, 1)

    def test_retired_control_session_cannot_return_or_refresh(self):
        guard = MODULE.HeartbeatGuard()
        guard.observe('ctrl-a', 1, 1.0)
        guard.observe('ctrl-b', 1, 1.1)
        self.assertIs(
            guard.observe('ctrl-a', 2, 1.9),
            V.STALE_CONTROL_SESSION,
        )
        self.assertIs(guard.state(2.100001), S.EXPIRED)
        self.assertEqual(guard.control_session_id, 'ctrl-b')


class CallerErrorTests(unittest.TestCase):
    def test_invalid_observations_are_rejected(self):
        cases = (
            ('', 1, 0.0),
            (None, 1, 0.0),
            ('ctrl-a', 0, 0.0),
            ('ctrl-a', True, 0.0),
            ('ctrl-a', MODULE.UINT64_MAX + 1, 0.0),
            ('ctrl-a', 1, float('nan')),
        )
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                MODULE.HeartbeatGuard().observe(*args)

    def test_clock_cannot_move_backwards(self):
        guard = MODULE.HeartbeatGuard()
        guard.observe('ctrl-a', 1, 2.0)
        for call in (
            lambda: guard.observe('ctrl-a', 2, 1.9),
            lambda: guard.state(1.9),
            lambda: guard.age(1.9),
        ):
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()


if __name__ == '__main__':
    unittest.main()
