"""Tests for non-blocking command admission and interruption."""

import unittest

from patrol_amr.mission_arbiter import (
    MissionArbiter, SubmissionResult)
from patrol_amr.mission_types import MissionRequest, MissionType


def request(command, suffix):
    """Create a unique internal request for arbitration tests."""
    return MissionRequest(
        command_id=f'cmd-{suffix}',
        mission_id=f'msn-{suffix}',
        robot_id='robot1',
        command=command,
    )


class MissionArbiterTest(unittest.TestCase):
    """Verify fail-closed motion admission and immediate cancellation."""

    def test_motion_rejected_until_safety_path_ready(self):
        """A disabled final speed path prevents navigation admission."""
        arbiter = MissionArbiter(False)
        result = arbiter.submit(request(MissionType.START_PATROL, 1))
        self.assertIs(result, SubmissionResult.SAFETY_NOT_READY)

    def test_second_motion_is_busy_until_first_finishes(self):
        """Only one motion command can be queued or active."""
        arbiter = MissionArbiter(True)
        first = request(MissionType.START_PATROL, 1)
        second = request(MissionType.DOCK, 2)
        self.assertIs(arbiter.submit(first), SubmissionResult.ACCEPTED)
        self.assertIs(arbiter.submit(second), SubmissionResult.BUSY)
        self.assertIs(arbiter.next_request(0.0), first)
        arbiter.begin(first)
        arbiter.finish(first)
        self.assertIs(arbiter.submit(second), SubmissionResult.ACCEPTED)

    def test_interrupt_sets_cancel_until_interrupt_finishes(self):
        """STOP wakes an active action before its queued handler executes."""
        arbiter = MissionArbiter(True)
        stop = request(MissionType.STOP, 3)
        self.assertIs(arbiter.submit(stop), SubmissionResult.ACCEPTED)
        self.assertTrue(arbiter.cancel_event.is_set())
        self.assertIs(arbiter.next_request(0.0), stop)
        arbiter.finish(stop)
        self.assertFalse(arbiter.cancel_event.is_set())

    def test_permanent_motion_failure_exposes_its_reason(self):
        """Operator diagnostics distinguish worker failure from readiness."""
        arbiter = MissionArbiter(True)
        arbiter.disable_motion('NAVIGATION_INITIALIZATION_FAILED')
        result = arbiter.submit(request(MissionType.START_PATROL, 4))
        self.assertIs(result, SubmissionResult.SAFETY_NOT_READY)
        self.assertEqual(
            arbiter.motion_disabled_reason,
            'NAVIGATION_INITIALIZATION_FAILED',
        )

    def test_external_stop_cancels_active_work_until_it_finishes(self):
        """A renewed token cannot erase cancellation under active work."""
        arbiter = MissionArbiter(True)
        first = request(MissionType.START_PATROL, 5)
        self.assertIs(arbiter.submit(first), SubmissionResult.ACCEPTED)
        arbiter.begin(arbiter.next_request(0.0))

        arbiter.set_external_stop(True)
        self.assertTrue(arbiter.cancel_event.is_set())
        arbiter.set_external_stop(False)
        self.assertTrue(arbiter.cancel_event.is_set())

        arbiter.finish(first)
        self.assertFalse(arbiter.cancel_event.is_set())
