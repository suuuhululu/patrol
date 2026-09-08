"""Tests for non-blocking command admission and interruption."""

from types import SimpleNamespace
import unittest

from patrol_amr.mission_arbiter import (
    MissionArbiter, SubmissionResult)
from patrol_amr.mission_types import MissionRequest, MissionType


def request(command, suffix, mission_id=None, command_id=None):
    """Create a unique internal request for arbitration tests."""
    return MissionRequest(
        command_id=command_id or f'cmd-{suffix}',
        mission_id=mission_id or f'msn-{suffix}',
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

    def test_lower_priority_motion_is_rejected_while_active(self):
        """A lower-priority command is never kept in a stale FIFO."""
        arbiter = MissionArbiter(True)
        first = request(MissionType.MOVE_TO_SAFE_ZONE, 1)
        second = request(MissionType.DOCK, 2)
        self.assertIs(arbiter.submit(first), SubmissionResult.ACCEPTED)
        self.assertIs(
            arbiter.submit(second), SubmissionResult.INVALID_STATE)
        self.assertIs(arbiter.next_request(0.0), first)
        self.assertTrue(arbiter.begin(first))
        arbiter.finish(first)
        self.assertIs(arbiter.submit(second), SubmissionResult.ACCEPTED)

    def test_interrupt_sets_cancel_until_interrupt_finishes(self):
        """STOP wakes an active action before its queued handler executes."""
        arbiter = MissionArbiter(True)
        active = request(MissionType.START_PATROL, 1)
        stop = request(MissionType.STOP, 3)
        self.assertIs(arbiter.submit(active), SubmissionResult.ACCEPTED)
        self.assertTrue(arbiter.begin(arbiter.next_request(0.0)))
        self.assertIs(arbiter.submit(stop), SubmissionResult.ACCEPTED)
        self.assertTrue(arbiter.cancel_event.is_set())
        self.assertTrue(arbiter.was_superseded(active))
        arbiter.finish(active)
        self.assertIs(arbiter.next_request(0.0), stop)
        self.assertTrue(arbiter.begin(stop))
        self.assertFalse(arbiter.cancel_event.is_set())
        arbiter.finish(stop)
        self.assertFalse(arbiter.cancel_event.is_set())

    def test_official_priority_order_is_fixed(self):
        commands = (
            MissionType.STOP,
            MissionType.MOVE_TO_SAFE_ZONE,
            MissionType.DOCK,
            MissionType.CANCEL,
            MissionType.RESUME_PATROL,
            MissionType.START_PATROL,
        )
        priorities = [MissionArbiter.priority(command) for command in commands]
        self.assertEqual(priorities, sorted(priorities, reverse=True))

    def test_higher_priority_replaces_active_command(self):
        arbiter = MissionArbiter(True)
        patrol = request(MissionType.START_PATROL, 1, 'msn-shared')
        safe_zone = request(
            MissionType.MOVE_TO_SAFE_ZONE, 2, 'msn-shared')
        self.assertIs(arbiter.submit(patrol), SubmissionResult.ACCEPTED)
        self.assertTrue(arbiter.begin(arbiter.next_request(0.0)))

        self.assertIs(arbiter.submit(safe_zone), SubmissionResult.ACCEPTED)
        self.assertTrue(arbiter.cancel_event.is_set())
        self.assertTrue(arbiter.was_superseded(patrol))

        arbiter.finish(patrol)
        self.assertIs(arbiter.next_request(0.0), safe_zone)
        self.assertTrue(arbiter.begin(safe_zone))
        self.assertFalse(arbiter.cancel_event.is_set())

    def test_queued_loser_is_skipped_after_higher_priority_arrives(self):
        arbiter = MissionArbiter(True)
        patrol = request(MissionType.START_PATROL, 1, 'msn-shared')
        dock = request(MissionType.DOCK, 2, 'msn-shared')
        self.assertIs(arbiter.submit(patrol), SubmissionResult.ACCEPTED)
        self.assertIs(arbiter.submit(dock), SubmissionResult.ACCEPTED)
        self.assertIs(
            arbiter.submit(patrol),
            SubmissionResult.DUPLICATE,
        )
        self.assertFalse(arbiter.begin(arbiter.next_request(0.0)))
        self.assertTrue(arbiter.begin(arbiter.next_request(0.0)))

    def test_duplicate_and_command_id_conflict_are_distinguished(self):
        arbiter = MissionArbiter(True)
        original = request(MissionType.START_PATROL, 1)
        same = request(
            MissionType.START_PATROL,
            99,
            mission_id=original.mission_id,
            command_id=original.command_id,
        )
        conflict = MissionRequest(
            command_id=original.command_id,
            mission_id=original.mission_id,
            robot_id=original.robot_id,
            command=MissionType.DOCK,
            target_id='dock_1',
        )
        self.assertIs(arbiter.submit(original), SubmissionResult.ACCEPTED)
        self.assertIs(arbiter.submit(same), SubmissionResult.DUPLICATE)
        self.assertIs(
            arbiter.submit(conflict),
            SubmissionResult.COMMAND_ID_CONFLICT,
        )

    def test_stateful_admission_requires_matching_active_mission(self):
        state = SimpleNamespace(
            mission='MISSION_PAUSED',
            mission_id='msn-active',
        )
        arbiter = MissionArbiter(True, lambda: state)
        mismatch = request(
            MissionType.MOVE_TO_SAFE_ZONE, 1, 'msn-other')
        resume = request(MissionType.RESUME_PATROL, 2, 'msn-active')
        self.assertIs(
            arbiter.submit(mismatch), SubmissionResult.INVALID_STATE)
        self.assertIs(arbiter.submit(resume), SubmissionResult.ACCEPTED)

    def test_start_and_cancel_require_correct_mission_lifetime(self):
        state = SimpleNamespace(
            mission='MISSION_PATROLLING',
            mission_id='msn-active',
        )
        arbiter = MissionArbiter(True, lambda: state)
        self.assertIs(
            arbiter.submit(request(MissionType.START_PATROL, 1)),
            SubmissionResult.INVALID_STATE,
        )
        self.assertIs(
            arbiter.submit(request(MissionType.CANCEL, 2, 'msn-other')),
            SubmissionResult.INVALID_STATE,
        )
        self.assertIs(
            arbiter.submit(request(MissionType.CANCEL, 3, 'msn-active')),
            SubmissionResult.ACCEPTED,
        )

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
        self.assertTrue(arbiter.external_stop_triggered)
        arbiter.set_external_stop(False)
        self.assertTrue(arbiter.cancel_event.is_set())
        self.assertTrue(arbiter.external_stop_triggered)

        arbiter.finish(first)
        self.assertFalse(arbiter.cancel_event.is_set())
        self.assertFalse(arbiter.external_stop_triggered)
