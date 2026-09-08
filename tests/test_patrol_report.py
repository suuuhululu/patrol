"""Stage-18 PatrolReport construction tests; no ROS graph required."""

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


PATROL_AMR_PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / 'src/patrol_amr'
)
sys.path.insert(0, str(PATROL_AMR_PACKAGE_ROOT))

from patrol_amr import patrol_report as MODULE  # noqa: E402


R = MODULE.PatrolResult
C = MODULE.ReasonCode
T = MODULE.ReportTime


def factory(**kwargs):
    return MODULE.PatrolReportFactory(
        'robot1', 'robot1-20260908T120000', **kwargs
    )


def report_args(**overrides):
    values = {
        'command_id': 'cmd-control-robot1-start-0001',
        'mission_id': 'msn-control-robot1-0001',
        'result': R.SUCCEEDED,
        'reason_code': C.NONE,
        'reason': '',
        'started_at': T(100, 1),
        'finished_at': T(120, 2),
        'final_waypoint_id': 'wp-03',
        'related_event_ids': ('det-a', 'det-b'),
    }
    values.update(overrides)
    return values


def wire_message():
    return SimpleNamespace(
        header=SimpleNamespace(stamp=SimpleNamespace(sec=0, nanosec=0)),
        report_id='',
        robot_id='',
        source_session_id='',
        command_id='',
        mission_id='',
        result=255,
        reason_code=0,
        reason='',
        started_at=SimpleNamespace(sec=0, nanosec=0),
        finished_at=SimpleNamespace(sec=0, nanosec=0),
        final_waypoint_id='',
        related_event_ids=[],
    )


class ContractEnumTests(unittest.TestCase):
    def test_result_values_match_patrol_report_message(self):
        self.assertEqual(
            (R.SUCCEEDED, R.FAILED, R.CANCELED), (0, 1, 2)
        )

    def test_reason_values_match_patrol_report_message(self):
        expected = {
            'NONE': 0,
            'CONTROL_CANCELED': 100,
            'COMMAND_SUPERSEDED': 101,
            'SAFETY_POLICY_CANCELED': 102,
            'INVALID_COMMAND': 200,
            'INVALID_TARGET': 201,
            'UNSUPPORTED_COMMAND': 202,
            'NAV_NO_PATH': 300,
            'NAV_TIMEOUT': 301,
            'NAV_GOAL_REJECTED': 302,
            'NAV_GOAL_ABORTED': 303,
            'SAFE_ZONE_NOT_FOUND': 400,
            'KEEPOUT_APPLY_FAILED': 401,
            'KEEPOUT_ROLLBACK_FAILED': 402,
            'LOCALIZATION_INVALID': 500,
            'POSE_STALE': 501,
            'LIDAR_VERIFICATION_FAILED': 502,
            'DRIVE_TOKEN_MISSING': 600,
            'DRIVE_TOKEN_EXPIRED': 601,
            'COMMUNICATION_LOST': 602,
            'E_STOP_ACTIVE': 700,
            'OBSTACLE_BLOCKED': 701,
            'FIRE_DETECTED': 702,
            'BATTERY_LOW': 800,
            'BATTERY_CRITICAL': 801,
            'DOCKING_TIMEOUT': 900,
            'ROLE_HANDOFF': 901,
            'SENSOR_ERROR': 1000,
            'INTERNAL_ERROR': 1001,
        }
        self.assertEqual(
            {item.name: item.value for item in C}, expected
        )


class ReportIdTests(unittest.TestCase):
    def test_id_uses_session_and_at_least_four_digit_sequence(self):
        self.assertEqual(
            MODULE.format_report_id('robot6-20260908T120000', 1),
            'rpt-robot6-20260908T120000-0001',
        )
        self.assertEqual(
            MODULE.format_report_id('robot6-20260908T120000-2', 10000),
            'rpt-robot6-20260908T120000-2-10000',
        )

    def test_invalid_session_and_sequence_are_rejected(self):
        sessions = ('', 'robot1', 'Robot1-20260908T120000',
                    'robot2-20260908T120000')
        for value in sessions:
            with self.subTest(session=value), self.assertRaises(ValueError):
                MODULE.format_report_id(value, 1)
        for value in (0, -1, True, 1.0, MODULE.UINT64_MAX + 1):
            with self.subTest(sequence=value), self.assertRaises(ValueError):
                MODULE.format_report_id('robot1-20260908T120000', value)


class TimeTests(unittest.TestCase):
    def test_time_has_exact_sec_and_nanosec(self):
        self.assertEqual(T(1, 2).sec, 1)
        self.assertEqual(T(1, 2).nanosec, 2)

    def test_invalid_time_is_rejected(self):
        for args in ((-1, 0), (1.0, 0), (True, 0),
                     (1, -1), (1, 1_000_000_000), (1, False)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                T(*args)


class FactoryTests(unittest.TestCase):
    def test_success_report_preserves_terminal_payload_fields(self):
        record = factory().create(**report_args())
        self.assertEqual(
            record.report_id, 'rpt-robot1-20260908T120000-0001'
        )
        self.assertEqual(record.robot_id, 'robot1')
        self.assertEqual(record.source_session_id,
                         'robot1-20260908T120000')
        self.assertEqual(record.command_id,
                         'cmd-control-robot1-start-0001')
        self.assertEqual(record.mission_id, 'msn-control-robot1-0001')
        self.assertIs(record.result, R.SUCCEEDED)
        self.assertIs(record.reason_code, C.NONE)
        self.assertEqual(record.started_at, T(100, 1))
        self.assertEqual(record.finished_at, T(120, 2))
        self.assertEqual(record.final_waypoint_id, 'wp-03')
        self.assertEqual(record.related_event_ids, ('det-a', 'det-b'))

    def test_failed_and_canceled_require_reason_code_and_detail(self):
        terminal_results = (R.FAILED, R.CANCELED)
        for result in terminal_results:
            with self.subTest(result=result), self.assertRaises(ValueError):
                factory().create(**report_args(
                    result=result, reason_code=C.NONE, reason='detail'
                ))
            with self.subTest(result=result), self.assertRaises(ValueError):
                factory().create(**report_args(
                    result=result, reason_code=C.NAV_TIMEOUT, reason=''
                ))
            record = factory().create(**report_args(
                result=result,
                reason_code=C.NAV_TIMEOUT,
                reason='navigation timeout after retry',
            ))
            self.assertIs(record.result, result)

    def test_unknown_result_and_reason_codes_are_rejected(self):
        for values in (
            {'result': 3},
            {'result': True},
            {'reason_code': 999},
            {'reason_code': True},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                factory().create(**report_args(**values))

    def test_required_ids_and_field_types_are_validated(self):
        cases = (
            {'command_id': ''},
            {'mission_id': None},
            {'reason': None},
            {'final_waypoint_id': None},
            {'started_at': (1, 0)},
            {'finished_at': (2, 0)},
            {'related_event_ids': 'det-a'},
            {'related_event_ids': ('det-a', '')},
        )
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                factory().create(**report_args(**values))

    def test_finished_time_cannot_precede_started_time(self):
        with self.assertRaises(ValueError):
            factory().create(**report_args(
                started_at=T(5, 1), finished_at=T(5, 0)
            ))

    def test_exact_retry_returns_same_record_and_same_id(self):
        reports = factory()
        first = reports.create(**report_args())
        second = reports.create(**report_args())
        self.assertIs(first, second)
        self.assertEqual(reports.next_sequence, 2)
        self.assertIs(reports.find(first.command_id), first)

    def test_conflicting_retry_is_rejected_without_consuming_sequence(self):
        reports = factory()
        first = reports.create(**report_args())
        with self.assertRaises(ValueError):
            reports.create(**report_args(
                result=R.FAILED,
                reason_code=C.NAV_TIMEOUT,
                reason='timeout',
            ))
        self.assertEqual(reports.next_sequence, 2)
        second = reports.create(**report_args(
            command_id='cmd-control-robot1-stop-0002'
        ))
        self.assertEqual(second.report_id,
                         'rpt-robot1-20260908T120000-0002')
        self.assertIs(reports.find(first.command_id), first)

    def test_failed_validation_does_not_consume_sequence(self):
        reports = factory()
        with self.assertRaises(ValueError):
            reports.create(**report_args(command_id=''))
        self.assertEqual(reports.next_sequence, 1)

    def test_persistent_owner_can_restore_next_sequence(self):
        reports = factory(next_sequence=42)
        record = reports.create(**report_args())
        self.assertEqual(record.report_id,
                         'rpt-robot1-20260908T120000-0042')
        self.assertEqual(reports.next_sequence, 43)

    def test_robot_and_session_must_match(self):
        with self.assertRaises(ValueError):
            MODULE.PatrolReportFactory(
                'robot1', 'robot6-20260908T120000'
            )
        with self.assertRaises(ValueError):
            MODULE.PatrolReportFactory(
                'robot2', 'robot2-20260908T120000'
            )


class WireMappingTests(unittest.TestCase):
    def record(self):
        return factory().create(**report_args(
            result=R.FAILED,
            reason_code=C.NAV_TIMEOUT,
            reason='navigation timeout',
        ))

    def test_every_patrol_report_field_is_populated(self):
        record = self.record()
        message = MODULE.populate_message(
            wire_message(), record, T(130, 3)
        )
        self.assertEqual(
            (message.header.stamp.sec, message.header.stamp.nanosec),
            (130, 3),
        )
        self.assertEqual(message.report_id, record.report_id)
        self.assertEqual(message.robot_id, record.robot_id)
        self.assertEqual(
            message.source_session_id, record.source_session_id
        )
        self.assertEqual(message.command_id, record.command_id)
        self.assertEqual(message.mission_id, record.mission_id)
        self.assertEqual(message.result, int(R.FAILED))
        self.assertEqual(message.reason_code, int(C.NAV_TIMEOUT))
        self.assertEqual(message.reason, 'navigation timeout')
        self.assertEqual(
            (message.started_at.sec, message.started_at.nanosec),
            (100, 1),
        )
        self.assertEqual(
            (message.finished_at.sec, message.finished_at.nanosec),
            (120, 2),
        )
        self.assertEqual(message.final_waypoint_id, 'wp-03')
        self.assertEqual(message.related_event_ids, ['det-a', 'det-b'])

    def test_mapping_copies_related_event_ids(self):
        record = self.record()
        message = MODULE.populate_message(wire_message(), record, T(1))
        message.related_event_ids.append('det-c')
        self.assertEqual(record.related_event_ids, ('det-a', 'det-b'))

    def test_mapping_requires_record_and_explicit_publish_time(self):
        for record, stamp in ((None, T(1)), (self.record(), (1, 0))):
            with self.subTest(record=record, stamp=stamp):
                with self.assertRaises(ValueError):
                    MODULE.populate_message(wire_message(), record, stamp)

    def test_publish_helper_publishes_exactly_once(self):
        class Publisher:
            def __init__(self):
                self.messages = []

            def publish(self, message):
                self.messages.append(message)

        publisher = Publisher()
        message = MODULE.publish_record(
            publisher, wire_message, self.record(), T(130, 3)
        )
        self.assertEqual(publisher.messages, [message])
        self.assertEqual(message.header.stamp.sec, 130)

    def test_publish_helper_validates_collaborators(self):
        with self.assertRaises(ValueError):
            MODULE.publish_record(None, wire_message, self.record(), T(1))
        with self.assertRaises(ValueError):
            MODULE.publish_record(
                SimpleNamespace(publish=lambda message: None),
                None,
                self.record(),
                T(1),
            )

    def test_qos_depth_matches_interface_contract(self):
        self.assertEqual(MODULE.PATROL_REPORT_QOS_DEPTH, 20)


class PersistenceCodecTests(unittest.TestCase):
    def test_record_json_round_trip_is_exact(self):
        record = factory().create(**report_args(
            result=R.CANCELED,
            reason_code=C.CONTROL_CANCELED,
            reason='사용자 취소',
        ))
        encoded = MODULE.record_to_json(record)
        self.assertEqual(MODULE.record_from_json(encoded), record)
        self.assertEqual(MODULE.record_to_json(record), encoded)

    def test_invalid_record_json_is_rejected(self):
        values = (
            '',
            '[]',
            '{bad',
            '{"report_id":"rpt-bad"}',
            MODULE.record_to_json(factory().create(**report_args())).replace(
                '"result":0', '"result":9'
            ),
        )
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.record_from_json(value)


if __name__ == '__main__':
    unittest.main()
