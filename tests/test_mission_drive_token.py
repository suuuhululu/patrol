"""Tests for monotonic DriveToken ordering, expiry, and revocation."""

import unittest
from types import SimpleNamespace

from patrol_amr.mission_drive_token import (
    DriveTokenDecision, MissionDriveTokenGuard)
from patrol_amr.mission_arbiter import (
    MissionArbiter, SubmissionResult)
from patrol_amr.mission_types import MissionRequest, MissionType


class FakeClock:
    """Controllable monotonic clock for lease tests."""

    def __init__(self) -> None:
        """Start away from zero to expose accidental absolute assumptions."""
        self.now = 10.0

    def __call__(self) -> float:
        """Return the current fake monotonic value."""
        return self.now


def token(
    sequence,
    token_id='tok-a',
    holder='robot6',
    session='ctrl-a',
    sec=1,
):
    """Build a small object with the generated DriveToken field shape."""
    return SimpleNamespace(
        control_session_id=session,
        token_id=token_id,
        holder_robot_id=holder,
        lease_duration=SimpleNamespace(sec=sec, nanosec=0),
        message_sequence=sequence,
    )


class DriveTokenGuardTest(unittest.TestCase):
    """Exercise token identity, ordering, revocation, and expiry."""

    def setUp(self) -> None:
        """Create one robot6 guard for each test."""
        self.clock = FakeClock()
        self.guard = MissionDriveTokenGuard('robot6', self.clock)

    def test_grant_refresh_and_local_expiry(self):
        """Increasing sequence refreshes a lease measured locally."""
        self.assertIs(
            self.guard.update_message(token(1)), DriveTokenDecision.GRANTED)
        self.assertTrue(self.guard.valid())
        self.clock.now += 0.8
        self.assertIs(
            self.guard.update_message(token(2)), DriveTokenDecision.REFRESHED)
        self.clock.now += 0.8
        self.assertTrue(self.guard.valid())
        self.clock.now += 0.21
        self.assertFalse(self.guard.valid())
        self.assertEqual(
            self.guard.snapshot().blocking_reason, 'DRIVE_TOKEN_EXPIRED')

    def test_stale_sequence_does_not_extend_lease(self):
        """A duplicate sequence cannot keep driving authority alive."""
        self.guard.update_message(token(3))
        self.clock.now += 0.9
        self.assertIs(
            self.guard.update_message(token(3)),
            DriveTokenDecision.IGNORED_STALE,
        )
        self.clock.now += 0.11
        self.assertFalse(self.guard.valid())

    def test_newer_other_holder_revokes_our_mission_authority(self):
        """A handoff to robot1 immediately removes robot6 authority."""
        self.guard.update_message(token(1))
        self.assertIs(
            self.guard.update_message(token(2, holder='robot1')),
            DriveTokenDecision.HOLDER_CHANGED,
        )
        self.assertFalse(self.guard.valid())
        self.assertEqual(self.guard.snapshot().token_id, '')

    def test_empty_token_revokes_immediately(self):
        """An ordered empty token revokes the selected holder."""
        self.guard.update_message(token(1))
        self.assertIs(
            self.guard.update_message(token(2, token_id='', sec=0)),
            DriveTokenDecision.REVOKED,
        )
        self.assertFalse(self.guard.valid())
        self.assertEqual(
            self.guard.snapshot().blocking_reason, 'DRIVE_TOKEN_REVOKED')

    def test_old_control_session_cannot_return(self):
        """Messages from a replaced control process stay retired."""
        self.guard.update_message(token(1, session='ctrl-a'))
        self.assertIs(
            self.guard.update_message(token(1, session='ctrl-b')),
            DriveTokenDecision.GRANTED,
        )
        self.assertIs(
            self.guard.update_message(token(99, session='ctrl-a')),
            DriveTokenDecision.IGNORED_STALE,
        )

    def test_publisher_supplied_q01_lease_expires_locally(self):
        """The agreed one-second lease expires on the local monotonic clock."""
        self.guard.update_message(token(1, sec=1))
        self.clock.now += 1.01
        self.assertFalse(self.guard.valid())

    def test_mission_needs_token_and_expiry_cancels_active_work(self):
        """The mission gate requires both a command and a live lease."""
        arbiter = MissionArbiter(self.guard.valid)
        arbiter.set_external_stop(True)
        request = MissionRequest(
            command_id='cmd-token-test',
            mission_id='msn-token-test',
            robot_id='robot6',
            command=MissionType.START_PATROL,
        )
        self.assertIs(
            arbiter.submit(request), SubmissionResult.SAFETY_NOT_READY)

        self.guard.update_message(token(1))
        arbiter.set_external_stop(False)
        self.assertIs(arbiter.submit(request), SubmissionResult.ACCEPTED)
        arbiter.begin(arbiter.next_request(0.0))

        self.clock.now += 1.01
        arbiter.set_external_stop(not self.guard.valid())
        self.assertTrue(arbiter.cancel_event.is_set())


if __name__ == '__main__':
    unittest.main()
