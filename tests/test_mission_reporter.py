import threading
import unittest

from patrol_amr.mission_reporter import (
    MissionReporter, ReportPublishError, ReportResult)
from patrol_amr.mission_types import (
    MissionOutcome, MissionRequest, MissionType)


class MissionReporterTest(unittest.TestCase):
    @staticmethod
    def request(command_id='cmd-1', robot_id='robot1'):
        return MissionRequest(
            command_id=command_id,
            mission_id='msn-ctrl-20260907T160000-robot1-0001',
            robot_id=robot_id,
            command=MissionType.START_PATROL,
            target_id='patrol-a',
        )

    def test_success_creates_stable_completion(self):
        published = []
        reporter = MissionReporter(published.append)

        result = reporter.report(self.request(), 'SUCCEEDED')

        self.assertIs(result, ReportResult.PUBLISHED)
        self.assertEqual(len(published), 1)
        completion = published[0]
        self.assertEqual(completion.command_id, 'cmd-1')
        self.assertEqual(
            completion.mission_id,
            'msn-ctrl-20260907T160000-robot1-0001',
        )
        self.assertEqual(completion.robot_id, 'robot1')
        self.assertIs(completion.command, MissionType.START_PATROL)
        self.assertIs(completion.outcome, MissionOutcome.SUCCEEDED)
        self.assertEqual(completion.reason_code, 0)
        self.assertEqual(completion.started_at_ns, 0)
        self.assertEqual(completion.finished_at_ns, 0)
        self.assertTrue(reporter.was_published('cmd-1'))

    def test_duplicate_command_is_not_published_twice(self):
        published = []
        reporter = MissionReporter(published.append)

        first = reporter.report(self.request(), 'SUCCEEDED')
        duplicate = reporter.report(self.request(), 'SUCCEEDED')

        self.assertIs(first, ReportResult.PUBLISHED)
        self.assertIs(duplicate, ReportResult.DUPLICATE)
        self.assertEqual(len(published), 1)

    def test_failed_and_canceled_results_require_reason(self):
        reporter = MissionReporter(lambda completion: None)
        for outcome in ('FAILED', 'CANCELED'):
            with self.subTest(outcome=outcome):
                with self.assertRaisesRegex(ValueError, 'requires a reason'):
                    reporter.report(self.request(outcome), outcome, '   ')

    def test_rejected_command_is_not_a_patrol_report_result(self):
        published = []
        reporter = MissionReporter(published.append)

        result = reporter.report(self.request(), 'REJECTED', 'NOT_READY')

        self.assertIs(result, ReportResult.NOT_REPORTABLE)
        self.assertEqual(published, [])

    def test_failed_sink_can_be_retried(self):
        published = []

        def flaky_sink(completion):
            if not published:
                published.append('failed-once')
                raise RuntimeError('temporary failure')
            published.append(completion)

        reporter = MissionReporter(flaky_sink)
        with self.assertRaises(ReportPublishError):
            reporter.report(self.request(), 'SUCCEEDED')

        result = reporter.report(self.request(), 'SUCCEEDED')

        self.assertIs(result, ReportResult.PUBLISHED)
        self.assertEqual(len(published), 2)
        self.assertTrue(reporter.was_published('cmd-1'))

    def test_concurrent_duplicate_is_suppressed_while_sink_runs(self):
        entered = threading.Event()
        release = threading.Event()
        published = []
        first_result = []

        def blocking_sink(completion):
            published.append(completion)
            entered.set()
            release.wait(timeout=1.0)

        reporter = MissionReporter(blocking_sink)
        thread = threading.Thread(
            target=lambda: first_result.append(
                reporter.report(self.request(), 'SUCCEEDED')))
        thread.start()
        self.assertTrue(entered.wait(timeout=1.0))

        duplicate = reporter.report(self.request(), 'SUCCEEDED')
        release.set()
        thread.join(timeout=1.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(first_result, [ReportResult.PUBLISHED])
        self.assertIs(duplicate, ReportResult.DUPLICATE)
        self.assertEqual(len(published), 1)

    def test_invalid_robot_and_unknown_outcome_are_rejected(self):
        reporter = MissionReporter(lambda completion: None)
        with self.assertRaisesRegex(ValueError, 'unsupported robot_id'):
            reporter.report(self.request(robot_id='robot2'), 'SUCCEEDED')
        with self.assertRaisesRegex(ValueError, 'unsupported report outcome'):
            reporter.report(self.request(), 'UNKNOWN')

    def test_failure_requires_public_reason_code(self):
        reporter = MissionReporter(lambda completion: None)
        with self.assertRaisesRegex(ValueError, 'nonzero reason_code'):
            reporter.report(self.request(), 'FAILED', 'NAV_ABORTED')

    def test_timestamps_waypoint_and_events_are_preserved(self):
        published = []
        reporter = MissionReporter(published.append)
        reporter.report(
            self.request(),
            'FAILED',
            'PATROL_GOAL_ABORTED',
            reason_code=303,
            started_at_ns=10,
            finished_at_ns=20,
            final_waypoint_id='W4',
            related_event_ids=['det-1'],
        )
        completion = published[0]
        self.assertEqual(completion.reason_code, 303)
        self.assertEqual(completion.started_at_ns, 10)
        self.assertEqual(completion.finished_at_ns, 20)
        self.assertEqual(completion.final_waypoint_id, 'W4')
        self.assertEqual(completion.related_event_ids, ('det-1',))


if __name__ == '__main__':
    unittest.main()
