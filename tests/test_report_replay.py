"""PatrolReport reconnection replay tests."""

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


PATROL_AMR_PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / 'src/patrol_amr'
)
sys.path.insert(0, str(PATROL_AMR_PACKAGE_ROOT))

from patrol_amr import patrol_report as REPORTS  # noqa: E402
from patrol_amr import report_replay as MODULE  # noqa: E402


class Message:
    def __init__(self):
        self.header = SimpleNamespace(
            stamp=SimpleNamespace(sec=0, nanosec=0)
        )
        self.report_id = ''
        self.robot_id = ''
        self.source_session_id = ''
        self.command_id = ''
        self.mission_id = ''
        self.result = 0
        self.reason_code = 0
        self.reason = ''
        self.started_at = SimpleNamespace(sec=0, nanosec=0)
        self.finished_at = SimpleNamespace(sec=0, nanosec=0)
        self.final_waypoint_id = ''
        self.related_event_ids = []


class Publisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


class Store:
    def __init__(self, records):
        self.records = tuple(records)

    def completed_reports(self):
        return self.records


def report(command_index):
    return REPORTS.PatrolReportFactory(
        'robot1', 'robot1-20260908T120000', next_sequence=command_index
    ).create(
        command_id=f'cmd-control-robot1-start-{command_index:04d}',
        mission_id='msn-control-robot1-0001',
        result=REPORTS.PatrolResult.SUCCEEDED,
        reason_code=REPORTS.ReasonCode.NONE,
        reason='',
        started_at=REPORTS.ReportTime(command_index),
        finished_at=REPORTS.ReportTime(command_index + 1),
    )


class ConnectionEpochTests(unittest.TestCase):
    def test_first_connection_and_reconnection_each_trigger_once(self):
        tracker = MODULE.SubscriberConnectionReplay()
        self.assertFalse(tracker.observe(0))
        self.assertTrue(tracker.observe(1))
        self.assertFalse(tracker.observe(2))
        self.assertFalse(tracker.observe(1))
        self.assertFalse(tracker.observe(0))
        self.assertTrue(tracker.observe(3))

    def test_initial_positive_count_triggers_startup_replay(self):
        tracker = MODULE.SubscriberConnectionReplay()
        self.assertTrue(tracker.observe(1))
        self.assertTrue(tracker.connected)

    def test_invalid_subscription_counts_do_not_change_state(self):
        tracker = MODULE.SubscriberConnectionReplay()
        for value in (-1, 1.0, True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tracker.observe(value)
            self.assertFalse(tracker.connected)


class ReplayTests(unittest.TestCase):
    def test_replays_all_records_in_store_order_with_same_ids(self):
        records = (report(1), report(2))
        publisher = Publisher()
        times = iter((REPORTS.ReportTime(100), REPORTS.ReportTime(101)))

        report_ids = MODULE.replay_completed_reports(
            Store(records), publisher, Message, lambda: next(times)
        )

        self.assertEqual(report_ids, tuple(item.report_id for item in records))
        self.assertEqual(
            tuple(message.report_id for message in publisher.messages),
            report_ids,
        )
        self.assertEqual(
            tuple(message.header.stamp.sec for message in publisher.messages),
            (100, 101),
        )

    def test_empty_store_publishes_nothing(self):
        publisher = Publisher()
        self.assertEqual(
            MODULE.replay_completed_reports(
                Store(()),
                publisher,
                Message,
                lambda: REPORTS.ReportTime(1),
            ),
            (),
        )
        self.assertEqual(publisher.messages, [])

    def test_collaborators_are_validated(self):
        with self.assertRaises(ValueError):
            MODULE.replay_completed_reports(
                object(), Publisher(), Message, lambda: REPORTS.ReportTime(1)
            )
        with self.assertRaises(ValueError):
            MODULE.replay_completed_reports(
                Store(()), Publisher(), Message, None
            )


if __name__ == '__main__':
    unittest.main()
