"""AMR-05 persistent MissionCommand deduplication tests."""

from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


PATROL_AMR_PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / 'src/patrol_amr'
)
sys.path.insert(0, str(PATROL_AMR_PACKAGE_ROOT))

from patrol_amr import command_store as MODULE  # noqa: E402
from patrol_amr import patrol_report as REPORTS  # noqa: E402


V = MODULE.RegisterVerdict
S = MODULE.CommandState
C = MODULE.MissionCommand


def command_args(index=1, **overrides):
    values = {
        'command_id': f'cmd-control-robot1-start-{index:04d}',
        'mission_id': 'msn-control-robot1-0001',
        'robot_id': 'robot1',
        'command': C.START_PATROL,
        'target_id': 'P1',
        'target_pose': {
            'header': {'frame_id': 'map', 'stamp': [100, 5]},
            'pose': {'x': 1.0, 'y': 2.0, 'yaw': 0.5},
        },
        'received_at': 1000.0 + index,
    }
    values.update(overrides)
    return values


class CommandEnumTests(unittest.TestCase):
    def test_values_match_mission_command_message(self):
        self.assertEqual(
            tuple(int(value) for value in C), (0, 1, 2, 3, 4, 5)
        )


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / 'commands.sqlite3')

    def tearDown(self):
        self.directory.cleanup()

    def store(self):
        return MODULE.CommandStore(self.path, 'robot1')

    def test_new_command_is_persisted_as_accepted(self):
        with self.store() as store:
            observed = store.register(**command_args())
            self.assertIs(observed.verdict, V.NEW)
            self.assertIs(observed.state, S.ACCEPTED)
            self.assertEqual(store.count(), 1)

    def test_exact_retry_returns_current_state_without_new_row(self):
        with self.store() as store:
            store.register(**command_args())
            observed = store.register(
                **command_args(received_at=9999.0)
            )
            self.assertIs(observed.verdict, V.DUPLICATE_ACCEPTED)
            self.assertIs(observed.state, S.ACCEPTED)
            self.assertEqual(store.count(), 1)

    def test_conflict_fields_are_all_compared(self):
        changes = (
            {'mission_id': 'msn-other'},
            {'robot_id': 'robot6'},
            {'command': C.CANCEL},
            {'target_id': 'P2'},
            {'target_pose': {'pose': {'x': 9.0}}},
        )
        for change in changes:
            with self.subTest(change=change):
                with self.store() as store:
                    store.register(**command_args())
                    observed = store.register(**command_args(**change))
                    self.assertIs(
                        observed.verdict, V.COMMAND_ID_CONFLICT
                    )
                    self.assertIsNone(observed.state)
                    self.assertEqual(store.count(), 1)

    def test_target_pose_key_order_is_not_a_conflict(self):
        with self.store() as store:
            store.register(**command_args(
                target_pose={'x': 1, 'y': 2}
            ))
            observed = store.register(**command_args(
                target_pose={'y': 2, 'x': 1}
            ))
            self.assertIs(observed.verdict, V.DUPLICATE_ACCEPTED)

    def test_executing_retry_does_not_execute_again(self):
        with self.store() as store:
            store.register(**command_args())
            self.assertIs(
                store.mark_executing(command_args()['command_id']),
                S.EXECUTING,
            )
            observed = store.register(**command_args())
            self.assertIs(observed.verdict, V.DUPLICATE_EXECUTING)
            self.assertIs(observed.state, S.EXECUTING)

    def test_completed_retry_returns_exact_report_for_retransmit(self):
        report_id = 'rpt-robot1-20260908T120000-0001'
        report_json = '{"result":0,"report_id":"' + report_id + '"}'
        with self.store() as store:
            store.register(**command_args())
            store.complete(
                command_args()['command_id'],
                report_id=report_id,
                report_payload_json=report_json,
            )
            observed = store.register(**command_args())
            self.assertIs(observed.verdict, V.DUPLICATE_COMPLETED)
            self.assertEqual(observed.report_id, report_id)
            self.assertEqual(observed.report_payload_json, report_json)

    def test_restart_preserves_state_and_completed_report(self):
        command_id = command_args()['command_id']
        with self.store() as store:
            store.register(**command_args())
            store.mark_executing(command_id)
        with self.store() as reopened:
            self.assertIs(
                reopened.register(**command_args()).verdict,
                V.DUPLICATE_EXECUTING,
            )
            reopened.complete(
                command_id,
                report_id='rpt-robot1-20260908T120000-0001',
                report_payload_json='{"result":0}',
            )
        with self.store() as reopened_again:
            observed = reopened_again.register(**command_args())
            self.assertIs(observed.verdict, V.DUPLICATE_COMPLETED)
            self.assertEqual(observed.report_payload_json, '{"result":0}')

    def test_validated_report_round_trips_through_store_restart(self):
        command_id = command_args()['command_id']
        report = REPORTS.PatrolReportFactory(
            'robot1', 'robot1-20260908T120000'
        ).create(
            command_id=command_id,
            mission_id=command_args()['mission_id'],
            result=REPORTS.PatrolResult.SUCCEEDED,
            reason_code=REPORTS.ReasonCode.NONE,
            reason='',
            started_at=REPORTS.ReportTime(10),
            finished_at=REPORTS.ReportTime(20),
        )
        with self.store() as store:
            store.register(**command_args())
            store.complete_report(command_id, report)
        with self.store() as reopened:
            self.assertEqual(reopened.completed_report(command_id), report)

    def test_all_completed_reports_restore_in_receive_order(self):
        factory = REPORTS.PatrolReportFactory(
            'robot1', 'robot1-20260908T120000'
        )
        expected = []
        with self.store() as store:
            for index, received_at in ((2, 20.0), (1, 10.0)):
                args = command_args(index=index, received_at=received_at)
                store.register(**args)
                report = factory.create(
                    command_id=args['command_id'],
                    mission_id=args['mission_id'],
                    result=REPORTS.PatrolResult.SUCCEEDED,
                    reason_code=REPORTS.ReasonCode.NONE,
                    reason='',
                    started_at=REPORTS.ReportTime(index),
                    finished_at=REPORTS.ReportTime(index + 1),
                )
                store.complete_report(args['command_id'], report)
                expected.append(report)

            pending = command_args(index=3, received_at=5.0)
            store.register(**pending)

        with self.store() as reopened:
            self.assertEqual(
                reopened.completed_reports(),
                (expected[1], expected[0]),
            )

    def test_report_identity_must_match_stored_command_and_robot(self):
        command_id = command_args()['command_id']
        with self.store() as store:
            store.register(**command_args())
            other_command = REPORTS.PatrolReportFactory(
                'robot1', 'robot1-20260908T120000'
            ).create(
                command_id='cmd-other',
                mission_id=command_args()['mission_id'],
                result=REPORTS.PatrolResult.SUCCEEDED,
                reason_code=REPORTS.ReasonCode.NONE,
                reason='',
                started_at=REPORTS.ReportTime(10),
                finished_at=REPORTS.ReportTime(20),
            )
            with self.assertRaises(ValueError):
                store.complete_report(command_id, other_command)

    def test_state_transitions_are_idempotent_but_not_reversible(self):
        command_id = command_args()['command_id']
        with self.store() as store:
            store.register(**command_args())
            store.mark_executing(command_id)
            store.mark_executing(command_id)
            store.complete(
                command_id,
                report_id='rpt-session-0001',
                report_payload_json='{"result":0}',
            )
            store.complete(
                command_id,
                report_id='rpt-session-0001',
                report_payload_json='{"result":0}',
            )
            with self.assertRaises(ValueError):
                store.mark_executing(command_id)
            with self.assertRaises(ValueError):
                store.complete(
                    command_id,
                    report_id='rpt-session-0002',
                    report_payload_json='{"result":1}',
                )

    def test_other_robot_new_command_is_not_persisted(self):
        with self.store() as store:
            with self.assertRaises(ValueError):
                store.register(**command_args(robot_id='robot6'))
            self.assertEqual(store.count(), 0)

    def test_invalid_input_is_rejected_before_insert(self):
        cases = (
            {'command_id': ''},
            {'mission_id': ''},
            {'command': 6},
            {'command': True},
            {'target_id': None},
            {'target_pose': float('nan')},
            {'received_at': float('nan')},
        )
        with self.store() as store:
            for change in cases:
                with self.subTest(change=change), self.assertRaises(
                    ValueError
                ):
                    store.register(**command_args(**change))
            self.assertEqual(store.count(), 0)

    def test_legacy_parameters_column_is_removed_without_losing_records(self):
        connection = sqlite3.connect(self.path)
        connection.execute(
            '''
            CREATE TABLE mission_commands (
                command_id TEXT PRIMARY KEY,
                mission_id TEXT NOT NULL,
                robot_id TEXT NOT NULL,
                command INTEGER NOT NULL,
                target_id TEXT NOT NULL,
                target_pose_json TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                received_at REAL NOT NULL,
                state TEXT NOT NULL,
                report_id TEXT,
                report_payload_json TEXT
            )
            '''
        )
        args = command_args()
        connection.execute(
            '''
            INSERT INTO mission_commands VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                args['command_id'], args['mission_id'], args['robot_id'],
                int(args['command']), args['target_id'],
                MODULE._canonical_json(args['target_pose'], 'target_pose'),
                '{"legacy":true}', args['received_at'], 'accepted', None, None,
            ),
        )
        connection.commit()
        connection.close()

        with self.store() as store:
            columns = {
                row['name'] for row in store._connection.execute(
                    'PRAGMA table_info(mission_commands)')
            }
            self.assertNotIn('parameters_json', columns)
            self.assertIs(
                store.register(**args).verdict, V.DUPLICATE_ACCEPTED)

    def test_unknown_command_lookup_fails(self):
        with self.store() as store:
            with self.assertRaises(KeyError):
                store.observation('missing-command')


class RetentionTests(unittest.TestCase):
    def test_keeps_all_recent_and_newest_thousand_old_records(self):
        with MODULE.CommandStore(':memory:', 'robot1') as store:
            for index in range(MODULE.MIN_OLD_RECORDS + 2):
                store.register(**command_args(
                    index=index + 1,
                    received_at=float(index),
                ))
            recent = command_args(
                index=2000,
                received_at=MODULE.RETENTION_SECONDS + 5000.0,
            )
            store.register(**recent)
            deleted = store.prune(
                MODULE.RETENTION_SECONDS + 5000.0
            )
            self.assertEqual(deleted, 2)
            self.assertEqual(store.count(), MODULE.MIN_OLD_RECORDS + 1)
            self.assertIs(
                store.observation(recent['command_id']).state,
                S.ACCEPTED,
            )

    def test_exactly_24_hours_old_is_retained(self):
        with MODULE.CommandStore(':memory:', 'robot1') as store:
            store.register(**command_args(received_at=100.0))
            self.assertEqual(
                store.prune(100.0 + MODULE.RETENTION_SECONDS), 0
            )


if __name__ == '__main__':
    unittest.main()
