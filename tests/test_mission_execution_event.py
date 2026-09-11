"""MissionExecutionEvent validation tests without a ROS graph."""

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
for package in ('src/patrol_amr_safety', 'src/patrol_amr'):
    sys.path.insert(0, str(ROOT / package))

from patrol_amr_safety import mission_execution_event as MODULE  # noqa: E402


def report(**overrides):
    values = dict(
        report_id='rpt-robot1-20260909T084600-0001',
        robot_id='robot1',
        source_session_id='robot1-20260909T084600',
        command_id='cmd-1',
        mission_id='msn-1',
        result=0,
        reason_code=0,
        reason='',
        started_at=SimpleNamespace(sec=1, nanosec=2),
        finished_at=SimpleNamespace(sec=3, nanosec=4),
        final_waypoint_id='W7',
        related_event_ids=[],
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def event(**overrides):
    values = dict(
        command_id='cmd-1',
        mission_id='msn-1',
        robot_id='robot1',
        event_type=MODULE.EventType.ADMITTED,
        source_session_id='robot1-20260909T084600',
        sequence=1,
        mission_state=2,
        reason_code=0,
        reason='',
        has_report=False,
        report=report(),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class MissionExecutionEventTest(unittest.TestCase):
    def test_admitted_event_has_no_report(self):
        parsed = MODULE.from_message(event())
        self.assertIs(parsed.event_type, MODULE.EventType.ADMITTED)
        self.assertIsNone(parsed.report)
        self.assertEqual(parsed.report_id, '')

    def test_rejected_requires_reason(self):
        for reason_code, reason in ((0, 'INVALID'), (206, '')):
            with self.subTest(reason_code=reason_code, reason=reason):
                with self.assertRaises(ValueError):
                    MODULE.from_message(event(
                        event_type=MODULE.EventType.REJECTED,
                        reason_code=reason_code,
                        reason=reason,
                    ))

    def test_result_report_identity_and_fields_are_preserved(self):
        parsed = MODULE.from_message(event(
            event_type=MODULE.EventType.RESULT_STORED,
            has_report=True,
        ))
        self.assertEqual(parsed.report.report_id, report().report_id)
        self.assertEqual(parsed.report.started_at.sec, 1)
        self.assertEqual(parsed.report.finished_at.nanosec, 4)

    def test_result_requires_report_and_other_events_forbid_it(self):
        with self.assertRaises(ValueError):
            MODULE.from_message(event(
                event_type=MODULE.EventType.RESULT_STORED,
                has_report=False,
            ))
        with self.assertRaises(ValueError):
            MODULE.from_message(event(has_report=True))

    def test_report_identity_must_match_event(self):
        with self.assertRaisesRegex(ValueError, 'identity'):
            MODULE.from_message(event(
                event_type=MODULE.EventType.RESULT_STORED,
                has_report=True,
                report=report(command_id='cmd-other'),
            ))

    def test_unknown_event_and_unsigned_ranges_are_rejected(self):
        for change in (
            {'event_type': 0},
            {'sequence': -1},
            {'mission_state': 256},
            {'reason_code': 2 ** 32},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                MODULE.from_message(event(**change))


if __name__ == '__main__':
    unittest.main()
