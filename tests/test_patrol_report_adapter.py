from pathlib import Path
from dataclasses import replace
import sys
from types import SimpleNamespace
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for package_root in ('src/patrol_amr_safety', 'src/patrol_amr'):
    sys.path.insert(0, str(REPOSITORY_ROOT / package_root))

from patrol_amr_safety.patrol_report_adapter import (
    nanoseconds_to_time, PatrolReportDrain, PatrolReportPublishError)
from patrol_amr.patrol_report_outbox import PendingPatrolReport


def time_message():
    return SimpleNamespace(sec=0, nanosec=0)


def report_message():
    return SimpleNamespace(
        header=SimpleNamespace(stamp=None),
        started_at=time_message(),
        finished_at=time_message(),
    )


class FakeOutbox:
    def __init__(self, records):
        self.records = records
        self.removed = []

    def pending(self):
        return tuple(self.records)

    def mark_published(self, report_id):
        self.removed.append(report_id)
        return True


class FakePublisher:
    def __init__(self, subscribers=1, fail=False):
        self.subscribers = subscribers
        self.fail = fail
        self.messages = []

    def get_subscription_count(self):
        return self.subscribers

    def publish(self, message):
        if self.fail:
            raise RuntimeError('DDS failure')
        self.messages.append(message)


def record():
    return PendingPatrolReport(
        report_id='rpt-robot6-20260908T100000-0001',
        report_sequence=1,
        robot_id='robot6',
        source_session_id='robot6-20260908T100000',
        command_id='cmd-1',
        mission_id='msn-1',
        result=0,
        reason_code=0,
        reason='',
        started_at_ns=1_000_000_002,
        finished_at_ns=3_000_000_004,
        final_waypoint_id='W7',
        related_event_ids=('det-1',),
    )


class PatrolReportAdapterTest(unittest.TestCase):
    def test_no_subscriber_leaves_report_pending(self):
        outbox = FakeOutbox([record()])
        publisher = FakePublisher(subscribers=0)
        drain = PatrolReportDrain(
            outbox, publisher, report_message, lambda: 'now')
        self.assertEqual(drain.publish_pending(), 0)
        self.assertEqual(outbox.removed, [])

    def test_message_is_filled_and_then_removed(self):
        outbox = FakeOutbox([record()])
        publisher = FakePublisher()
        drain = PatrolReportDrain(
            outbox, publisher, report_message, lambda: 'now')
        self.assertEqual(drain.publish_pending(), 1)
        message = publisher.messages[0]
        self.assertEqual(message.header.stamp, 'now')
        self.assertEqual(message.report_id, record().report_id)
        self.assertEqual((message.started_at.sec, message.started_at.nanosec),
                         (1, 2))
        self.assertEqual((message.finished_at.sec, message.finished_at.nanosec),
                         (3, 4))
        self.assertEqual(message.related_event_ids, ['det-1'])
        self.assertEqual(outbox.removed, [record().report_id])

    def test_publish_failure_keeps_report_pending(self):
        outbox = FakeOutbox([record()])
        drain = PatrolReportDrain(
            outbox, FakePublisher(fail=True), report_message, lambda: 'now')
        with self.assertRaises(PatrolReportPublishError):
            drain.publish_pending()
        self.assertEqual(outbox.removed, [])

    def test_nanosecond_conversion_rejects_negative_time(self):
        with self.assertRaises(ValueError):
            nanoseconds_to_time(-1, time_message())

    def test_ros_time_range_and_types(self):
        for invalid in (True, 1.5, '1', None, (2 ** 31) * 1_000_000_000):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    nanoseconds_to_time(invalid, time_message())
        message = nanoseconds_to_time((2 ** 31) * 1_000_000_000 - 1, time_message())
        self.assertEqual((message.sec, message.nanosec), (2 ** 31 - 1, 999_999_999))

    def test_conversion_failure_keeps_record_and_recovery_can_retry(self):
        outbox = FakeOutbox([replace(record(), finished_at_ns=(2 ** 31) * 1_000_000_000)])
        publisher = FakePublisher()
        drain = PatrolReportDrain(outbox, publisher, report_message, lambda: 'now')
        with self.assertRaises(PatrolReportPublishError):
            drain.publish_pending()
        self.assertEqual(publisher.messages, [])
        self.assertEqual(outbox.removed, [])
        outbox.records = [record()]
        self.assertEqual(drain.publish_pending(), 1)


if __name__ == '__main__':
    unittest.main()
