from pathlib import Path
import tempfile
import unittest

from patrol_amr.mission_reporter import MissionCompletion
from patrol_amr.mission_types import MissionOutcome, MissionType
from patrol_amr.patrol_report_outbox import (
    PatrolReportOutbox, PatrolReportOutboxError)


def completion(command_id='cmd-1', reason='', reason_code=0):
    return MissionCompletion(
        command_id=command_id,
        mission_id='msn-1',
        robot_id='robot6',
        command=MissionType.START_PATROL,
        target_id='patrol-a',
        outcome=(MissionOutcome.SUCCEEDED if reason_code == 0
                 else MissionOutcome.FAILED),
        reason=reason,
        reason_code=reason_code,
        started_at_ns=1_000_000_001,
        finished_at_ns=2_000_000_002,
        final_waypoint_id='W7',
        related_event_ids=('det-1',),
    )


class PatrolReportOutboxTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / 'outbox.json'

    def test_pending_report_survives_reload_with_same_id(self):
        first = PatrolReportOutbox(self.path).enqueue(
            completion(), 'amr-20260908T100000')
        pending = PatrolReportOutbox(self.path).pending()
        self.assertEqual(pending, (first,))
        self.assertEqual(first.report_id, 'rpt-amr-20260908T100000-0001')
        self.assertEqual(first.final_waypoint_id, 'W7')

    def test_duplicate_completion_keeps_original_report(self):
        outbox = PatrolReportOutbox(self.path)
        first = outbox.enqueue(completion(), 'amr-20260908T100000')
        duplicate = outbox.enqueue(completion(), 'amr-20260908T100000')
        self.assertEqual(duplicate, first)
        self.assertEqual(len(outbox.pending()), 1)

    def test_sequence_starts_at_one_for_each_source_session(self):
        outbox = PatrolReportOutbox(self.path)
        a1 = outbox.enqueue(completion('cmd-a1'), 'amr-20260908T100000')
        a2 = outbox.enqueue(completion('cmd-a2'), 'amr-20260908T100000')
        b1 = outbox.enqueue(completion('cmd-b1'), 'amr-20260908T100100')
        self.assertEqual(a1.report_sequence, 1)
        self.assertEqual(a2.report_sequence, 2)
        self.assertEqual(b1.report_sequence, 1)

    def test_conflicting_duplicate_is_rejected(self):
        outbox = PatrolReportOutbox(self.path)
        outbox.enqueue(completion(), 'amr-20260908T100000')
        with self.assertRaises(PatrolReportOutboxError):
            outbox.enqueue(
                completion(reason='ABORTED', reason_code=303),
                'amr-20260908T100000',
            )

    def test_mark_published_removes_only_matching_report(self):
        outbox = PatrolReportOutbox(self.path)
        first = outbox.enqueue(completion('cmd-1'), 'amr-20260908T100000')
        second = outbox.enqueue(completion('cmd-2'), 'amr-20260908T100000')
        self.assertTrue(outbox.mark_published(first.report_id))
        self.assertEqual(outbox.pending(), (second,))
        self.assertFalse(outbox.mark_published(first.report_id))

    def test_damaged_outbox_fails_without_discarding_it(self):
        self.path.write_text('{bad')
        with self.assertRaises(PatrolReportOutboxError):
            PatrolReportOutbox(self.path).pending()
        self.assertEqual(self.path.read_text(), '{bad')


if __name__ == '__main__':
    unittest.main()
