"""Deterministic DriveToken guard tests; no ROS graph required."""

import importlib.util
from pathlib import Path
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / 'src/patrol_amr/'
          'patrol_amr/drive_token_guard.py')
SPEC = importlib.util.spec_from_file_location('drive_token_guard', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
V = MODULE.TokenVerdict
A = MODULE.DriveAuthority

LEASE = 1.0
SESSION = 'ctrl-20260907T120000'


def guard(robot_id='robot1'):
    return MODULE.DriveTokenGuard(robot_id)


def accept(
    g,
    now,
    token_id='tok-a',
    message_sequence=1,
    holder=None,
    lease=LEASE,
    control_session_id=SESSION,
):
    return g.observe(
        control_session_id,
        token_id,
        holder or g.robot_id,
        lease,
        message_sequence,
        now,
    )


class DurationTests(unittest.TestCase):
    def test_duration_to_seconds(self):
        self.assertEqual(MODULE.duration_to_seconds(1, 0), 1.0)
        self.assertAlmostEqual(MODULE.duration_to_seconds(0, 500_000_000), 0.5)

    def test_duration_rejects_non_int(self):
        for sec, nanosec in ((1.0, 0), (0, 1.5), (True, 0), (0, False)):
            with self.subTest(sec=sec, nanosec=nanosec):
                with self.assertRaises(ValueError):
                    MODULE.duration_to_seconds(sec, nanosec)


class LeaseTests(unittest.TestCase):
    def test_initial_state_has_no_authority(self):
        g = guard()
        self.assertIs(g.authority(0.0), A.MISSING)
        self.assertIsNone(g.control_session_id)
        self.assertIsNone(g.token_id)

    def test_valid_token_grants_until_inclusive_lease_end(self):
        g = guard()
        self.assertIs(accept(g, 0.0), V.ACCEPTED)
        self.assertIs(g.authority(0.999999), A.GRANTED)
        self.assertIs(g.authority(1.0), A.EXPIRED)

    def test_renewal_extends_lease(self):
        g = guard()
        accept(g, 0.0, message_sequence=1)
        accept(g, 0.8, message_sequence=2)
        self.assertIs(g.authority(1.0), A.GRANTED)
        self.assertIs(g.authority(1.8), A.EXPIRED)

    def test_remaining_lease_floors_at_zero(self):
        g = guard()
        accept(g, 0.0)
        self.assertAlmostEqual(g.remaining_lease(0.25), 0.75)
        self.assertEqual(g.remaining_lease(1.0), 0.0)

    def test_invalid_lease_does_not_grant_or_extend(self):
        for lease in (0.0, -1.0, float('nan'), float('inf')):
            with self.subTest(lease=lease):
                g = guard()
                self.assertIs(accept(g, 0.0, lease=lease), V.INVALID_LEASE)
                self.assertIs(g.authority(0.0), A.MISSING)


class SessionAndSequenceTests(unittest.TestCase):
    def test_same_session_replay_is_discarded(self):
        g = guard()
        accept(g, 0.0, message_sequence=7)
        for sequence in (1, 6, 7):
            with self.subTest(sequence=sequence):
                self.assertIs(
                    accept(g, 0.1, message_sequence=sequence),
                    V.STALE_MESSAGE_SEQUENCE,
                )

    def test_token_change_does_not_reset_same_session_sequence(self):
        g = guard()
        accept(g, 0.0, token_id='tok-a', message_sequence=9)
        self.assertIs(
            accept(g, 0.1, token_id='tok-b', message_sequence=1),
            V.STALE_MESSAGE_SEQUENCE,
        )
        self.assertEqual(g.token_id, 'tok-a')

    def test_new_control_session_resets_sequence_and_replaces_token(self):
        g = guard()
        accept(g, 0.0, token_id='tok-a', message_sequence=900)
        verdict = accept(
            g,
            0.1,
            token_id='tok-b',
            message_sequence=1,
            control_session_id='ctrl-20260907T120100',
        )
        self.assertIs(verdict, V.ACCEPTED)
        self.assertEqual(g.token_id, 'tok-b')
        self.assertEqual(g.last_message_sequence, 1)

    def test_retired_control_session_cannot_replace_current_session(self):
        g = guard()
        accept(g, 0.0, token_id='tok-a', message_sequence=9)
        accept(
            g,
            0.1,
            token_id='tok-b',
            message_sequence=1,
            control_session_id='ctrl-20260907T120100',
        )
        verdict = accept(
            g,
            0.2,
            token_id='tok-old-replay',
            message_sequence=10,
            control_session_id=SESSION,
        )
        self.assertIs(verdict, V.STALE_CONTROL_SESSION)
        self.assertEqual(g.control_session_id, 'ctrl-20260907T120100')
        self.assertEqual(g.token_id, 'tok-b')

    def test_discarded_replay_does_not_extend_lease(self):
        g = guard()
        accept(g, 0.0, message_sequence=7)
        accept(g, 0.9, message_sequence=7)
        self.assertIs(g.authority(1.0), A.EXPIRED)


class HolderAndRevocationTests(unittest.TestCase):
    def test_newer_other_holder_invalidates_immediately(self):
        g = guard('robot1')
        accept(g, 0.0, message_sequence=1)
        verdict = accept(
            g, 0.2, token_id='tok-b', message_sequence=2, holder='robot6'
        )
        self.assertIs(verdict, V.HOLDER_CHANGED)
        self.assertIs(g.authority(0.2), A.MISSING)

    def test_duplicate_other_holder_is_discarded(self):
        g = guard('robot1')
        accept(g, 0.0, token_id='tok-b', message_sequence=5, holder='robot6')
        verdict = accept(
            g, 0.1, token_id='tok-b', message_sequence=5, holder='robot6'
        )
        self.assertIs(verdict, V.OTHER_HOLDER)

    def test_empty_token_id_revokes_designated_holder(self):
        g = guard()
        accept(g, 0.0, message_sequence=1)
        self.assertIs(
            accept(g, 0.1, token_id='', message_sequence=2), V.REVOKED
        )
        self.assertTrue(g.revoked_last)
        self.assertIs(g.authority(0.1), A.MISSING)


class CallerErrorTests(unittest.TestCase):
    def test_robot_id_must_be_known(self):
        for robot_id in ('robot2', '', 'ROBOT1', None):
            with self.subTest(robot_id=robot_id):
                with self.assertRaises(ValueError):
                    guard(robot_id)

    def test_invalid_observation_arguments_raise(self):
        g = guard()
        bad = (
            ('', 'tok-a', 'robot1', LEASE, 1, 0.0),
            (SESSION, None, 'robot1', LEASE, 1, 0.0),
            (SESSION, 'tok-a', 'robot2', LEASE, 1, 0.0),
            (SESSION, 'tok-a', 'robot1', None, 1, 0.0),
            (SESSION, 'tok-a', 'robot1', LEASE, 0, 0.0),
            (SESSION, 'tok-a', 'robot1', LEASE, True, 0.0),
            (SESSION, 'tok-a', 'robot1', LEASE, MODULE.UINT64_MAX + 1, 0.0),
            (SESSION, 'tok-a', 'robot1', LEASE, 1, float('nan')),
        )
        for args in bad:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    g.observe(*args)

    def test_observation_clock_must_not_move_backwards(self):
        g = guard()
        accept(g, 5.0)
        with self.assertRaises(ValueError):
            accept(g, 4.9, message_sequence=2)

    def test_uint64_max_sequence_is_accepted(self):
        g = guard()
        self.assertIs(
            accept(g, 0.0, message_sequence=MODULE.UINT64_MAX), V.ACCEPTED
        )


if __name__ == '__main__':
    unittest.main()
