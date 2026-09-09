import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / 'src/patrol_amr'))

from patrol_amr import command_lifecycle as MODULE
from patrol_amr import patrol_report


def report():
    return patrol_report.PatrolReportFactory(
        'robot1', 'robot1-20260908T190000')


def report_record():
    return report().create(
        command_id='cmd-1',
        mission_id='msn-1',
        result=patrol_report.PatrolResult.SUCCEEDED,
        reason_code=patrol_report.ReasonCode.NONE,
        reason='',
        started_at=patrol_report.ReportTime(1, 2),
        finished_at=patrol_report.ReportTime(3, 4),
    )


class CommandLifecycleTest(unittest.TestCase):
    def test_executing_round_trip_has_full_identity(self):
        event = MODULE.executing(SimpleNamespace(
            command_id='cmd-1', mission_id='msn-1', robot_id='robot1'))
        self.assertEqual(MODULE.from_json(MODULE.to_json(event)), event)
        self.assertIs(event.kind, MODULE.LifecycleKind.EXECUTING)
        self.assertIsNone(event.report)

    def test_completed_round_trip_preserves_exact_report(self):
        event = MODULE.completed(report_record())
        restored = MODULE.from_json(MODULE.to_json(event))
        self.assertEqual(restored, event)
        self.assertEqual(restored.report.report_id, report_record().report_id)

    def test_completed_identity_mismatch_is_rejected(self):
        event = MODULE.CommandLifecycleEvent(
            kind=MODULE.LifecycleKind.COMPLETED,
            command_id='different-command',
            mission_id='msn-1',
            robot_id='robot1',
            report=report_record(),
        )
        with self.assertRaisesRegex(ValueError, 'identity'):
            MODULE.to_json(event)

    def test_unknown_schema_and_extra_fields_are_rejected(self):
        payload = json.loads(MODULE.to_json(MODULE.executing(SimpleNamespace(
            command_id='cmd-1', mission_id='msn-1', robot_id='robot1'))))
        for change in (
            {'schema_version': 99},
            {'extra': True},
        ):
            with self.subTest(change=change):
                candidate = dict(payload)
                candidate.update(change)
                with self.assertRaises(ValueError):
                    MODULE.from_json(json.dumps(candidate))


if __name__ == '__main__':
    unittest.main()
