"""Persistent MissionCommand ingress decision tests."""

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


PATROL_AMR_PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / 'src/patrol_amr'
)
sys.path.insert(0, str(PATROL_AMR_PACKAGE_ROOT))

from patrol_amr import command_check as CHECKS  # noqa: E402
from patrol_amr import command_store as STORE  # noqa: E402
from patrol_amr import mission_ingress as MODULE  # noqa: E402
from patrol_amr import patrol_report as REPORTS  # noqa: E402


def args(**overrides):
    values = {
        'command_id': 'cmd-control-robot1-start-0001',
        'mission_id': 'msn-control-robot1-0001',
        'robot_id': 'robot1',
        'command': STORE.MissionCommand.START_PATROL,
        'target_id': 'P1',
        'target_pose': {'frame_id': 'map', 'x': 1.0},
        'received_at': 10.0,
    }
    values.update(overrides)
    return values


def ingress(store):
    return MODULE.MissionIngress(store)


class DecisionTests(unittest.TestCase):
    def test_new_command_is_accepted_and_dispatched_once(self):
        with STORE.CommandStore(':memory:', 'robot1') as store:
            first = ingress(store).observe(**args())
            retry = ingress(store).observe(**args(received_at=99.0))
        self.assertIs(first.check_meaning, CHECKS.CheckMeaning.ACCEPTED)
        self.assertTrue(first.dispatch_new)
        self.assertIs(retry.check_meaning, CHECKS.CheckMeaning.ACCEPTED)
        self.assertFalse(retry.dispatch_new)

    def test_executing_retry_reports_executing_without_dispatch(self):
        with STORE.CommandStore(':memory:', 'robot1') as store:
            store.register(**args())
            store.mark_executing(args()['command_id'])
            decision = ingress(store).observe(**args())
        self.assertIs(decision.check_meaning, CHECKS.CheckMeaning.EXECUTING)
        self.assertFalse(decision.dispatch_new)

    def test_completed_retry_replays_exact_report_without_check(self):
        with STORE.CommandStore(':memory:', 'robot1') as store:
            store.register(**args())
            report = REPORTS.PatrolReportFactory(
                'robot1', 'robot1-20260908T120000'
            ).create(
                command_id=args()['command_id'],
                mission_id=args()['mission_id'],
                result=REPORTS.PatrolResult.SUCCEEDED,
                reason_code=REPORTS.ReasonCode.NONE,
                reason='',
                started_at=REPORTS.ReportTime(1),
                finished_at=REPORTS.ReportTime(2),
            )
            store.complete_report(args()['command_id'], report)
            decision = ingress(store).observe(**args())
        self.assertIsNone(decision.check_meaning)
        self.assertFalse(decision.dispatch_new)
        self.assertEqual(decision.replay_report, report)

    def test_conflicting_retry_uses_fixed_v1_code(self):
        with STORE.CommandStore(':memory:', 'robot1') as store:
            store.register(**args())
            decision = MODULE.MissionIngress(store).observe(
                **args(target_id='P2'))
        self.assertIs(decision.check_meaning, CHECKS.CheckMeaning.REJECTED)
        self.assertEqual(
            (decision.reason_code, decision.reason),
            (int(REPORTS.ReasonCode.COMMAND_ID_CONFLICT), 'COMMAND_ID_CONFLICT'),
        )

    def test_invalid_command_is_rejected_without_persistence(self):
        with STORE.CommandStore(':memory:', 'robot1') as store:
            decision = ingress(store).observe(**args(command=99))
            self.assertEqual(store.count(), 0)
        self.assertIs(decision.check_meaning, CHECKS.CheckMeaning.REJECTED)
        self.assertEqual(
            decision.reason_code,
            int(REPORTS.ReasonCode.INVALID_PARAMETERS),
        )


class WireCopyTests(unittest.TestCase):
    def test_mission_command_copy_includes_full_pose_fingerprint(self):
        vector = lambda **values: SimpleNamespace(**values)
        pose = SimpleNamespace(
            header=SimpleNamespace(
                stamp=SimpleNamespace(sec=1, nanosec=2), frame_id='map'
            ),
            pose=SimpleNamespace(
                position=vector(x=3.0, y=4.0, z=5.0),
                orientation=vector(x=0.0, y=0.0, z=0.5, w=0.5),
            ),
        )
        message = SimpleNamespace(
            command_id='cmd-1', mission_id='msn-1', robot_id='robot1',
            command=1, target_id='P1', target_pose=pose,
        )
        fields = MODULE.mission_command_fields(message, received_at=9.0)
        self.assertEqual(fields['target_pose']['header']['frame_id'], 'map')
        self.assertEqual(fields['target_pose']['pose']['position']['z'], 5.0)
        self.assertEqual(fields['target_pose']['pose']['orientation']['w'], 0.5)
        self.assertEqual(fields['received_at'], 9.0)

    def test_missing_wire_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.mission_command_fields(SimpleNamespace(), received_at=1.0)


if __name__ == '__main__':
    unittest.main()
