import unittest

from patrol_amr.mission_state import MissionStateTracker


class MissionStateTrackerTest(unittest.TestCase):
    def test_restart_can_continue_revision_after_persisted_snapshot(self):
        tracker = MissionStateTracker(starting_revision=8)
        self.assertEqual(tracker.snapshot().revision, 8)
        tracker.command_started('cmd-1', 'msn-1')
        self.assertEqual(tracker.snapshot().revision, 9)

    def test_invalid_starting_revision_is_rejected(self):
        for value in (-1, 1.5, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MissionStateTracker(starting_revision=value)

    def test_progress_and_terminal_result_are_preserved(self):
        tracker = MissionStateTracker()
        tracker.command_started('cmd-1', 'msn-1')
        tracker.transition('MISSION_PATROLLING', 6)
        tracker.command_finished('FAILED', 'GOAL_ABORTED', 303)

        snapshot = tracker.snapshot()
        self.assertEqual(snapshot.mission, 'MISSION_FAILED')
        self.assertEqual(snapshot.waypoint_index, -1)
        self.assertEqual(snapshot.last_waypoint_index, 6)
        self.assertEqual(snapshot.command_id, '')
        self.assertEqual(snapshot.mission_id, '')
        self.assertEqual(snapshot.reason_code, 303)
        self.assertEqual(snapshot.reason, 'GOAL_ABORTED')
        self.assertGreaterEqual(snapshot.revision, 3)

    def test_next_command_clears_previous_terminal_fields(self):
        tracker = MissionStateTracker()
        tracker.command_finished('FAILED', 'OLD', 1001)
        tracker.command_started('cmd-2', 'msn-2')
        snapshot = tracker.snapshot()
        self.assertEqual(snapshot.command_id, 'cmd-2')
        self.assertEqual(snapshot.mission_id, 'msn-2')
        self.assertEqual(snapshot.reason_code, 0)
        self.assertEqual(snapshot.reason, '')
        self.assertEqual(snapshot.last_waypoint_index, -1)


if __name__ == '__main__':
    unittest.main()
