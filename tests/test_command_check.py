"""CommandCheck construction tests for the fixed v1.0 values."""

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


PATROL_AMR_PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / 'src/patrol_amr'
)
sys.path.insert(0, str(PATROL_AMR_PACKAGE_ROOT))

from patrol_amr import command_check as MODULE  # noqa: E402
from patrol_amr.patrol_report import ReportTime  # noqa: E402


def message():
    return SimpleNamespace(
        header=SimpleNamespace(stamp=SimpleNamespace(sec=0, nanosec=0)),
        command_id='', mission_id='', robot_id='', check_state=0,
        reason_code=0, reason='', source_session_id='', sequence=0,
    )


class MappingTests(unittest.TestCase):
    def test_values_match_the_fixed_v1_contract(self):
        mapping = MODULE.CheckStateMapping()
        self.assertEqual(mapping.wire_value(MODULE.CheckMeaning.ACCEPTED), 1)
        self.assertEqual(mapping.wire_value(MODULE.CheckMeaning.EXECUTING), 2)
        self.assertEqual(mapping.wire_value(MODULE.CheckMeaning.REJECTED), 3)

    def test_non_contract_values_are_rejected(self):
        for values in ((9, 4, 7), (0, 0, 1), (-1, 1, 2), (1, 2, 256)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                MODULE.CheckStateMapping(*values)


class FactoryTests(unittest.TestCase):
    def factory(self, **kwargs):
        return MODULE.CommandCheckFactory(
            'robot1',
            'robot1-20260908T120000',
            MODULE.CheckStateMapping(),
            **kwargs,
        )

    def test_sequence_and_wire_value_are_allocated(self):
        factory = self.factory(next_sequence=5)
        record = factory.create(
            command_id='cmd-1', mission_id='msn-1',
            meaning=MODULE.CheckMeaning.ACCEPTED,
        )
        self.assertEqual((record.check_state, record.sequence), (1, 5))
        self.assertEqual(factory.next_sequence, 6)

    def test_rejected_check_preserves_reason_fields(self):
        record = self.factory().create(
            command_id='cmd-1', mission_id='msn-1',
            meaning=MODULE.CheckMeaning.REJECTED,
            reason_code=200, reason='INVALID_COMMAND',
        )
        self.assertEqual((record.check_state, record.reason_code), (3, 200))
        self.assertEqual(record.reason, 'INVALID_COMMAND')

    def test_empty_ids_can_be_echoed_for_malformed_input_rejection(self):
        record = self.factory().create(
            command_id='', mission_id='', meaning=MODULE.CheckMeaning.REJECTED,
        )
        self.assertEqual((record.command_id, record.mission_id), ('', ''))

    def test_invalid_configuration_and_payload_are_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.CommandCheckFactory(
                'robot6', 'robot1-20260908T120000',
                MODULE.CheckStateMapping(),
            )
        with self.assertRaises(ValueError):
            self.factory().create(
                command_id=None, mission_id='msn-1',
                meaning=MODULE.CheckMeaning.ACCEPTED,
            )
        with self.assertRaises(ValueError):
            self.factory().create(
                command_id='cmd-1', mission_id='msn-1',
                meaning=MODULE.CheckMeaning.REJECTED,
                reason_code=MODULE.UINT32_MAX + 1,
            )

    def test_sequence_refuses_uint64_exhaustion(self):
        factory = self.factory(next_sequence=MODULE.UINT64_MAX)
        with self.assertRaises(OverflowError):
            factory.create(
                command_id='cmd-1', mission_id='msn-1',
                meaning=MODULE.CheckMeaning.ACCEPTED,
            )


class WireTests(unittest.TestCase):
    def test_every_wire_field_is_populated_and_published_once(self):
        record = FactoryTests().factory().create(
            command_id='cmd-1', mission_id='msn-1',
            meaning=MODULE.CheckMeaning.EXECUTING,
            reason_code=12, reason='running',
        )
        publisher = SimpleNamespace(messages=[])
        publisher.publish = publisher.messages.append
        result = MODULE.publish_record(
            publisher, message, record, ReportTime(10, 20)
        )
        self.assertEqual(len(publisher.messages), 1)
        self.assertIs(publisher.messages[0], result)
        self.assertEqual((result.header.stamp.sec, result.header.stamp.nanosec), (10, 20))
        self.assertEqual(
            (result.command_id, result.mission_id, result.robot_id),
            ('cmd-1', 'msn-1', 'robot1'),
        )
        self.assertEqual(
            (result.check_state, result.reason_code, result.reason),
            (2, 12, 'running'),
        )
        self.assertEqual(
            (result.source_session_id, result.sequence),
            ('robot1-20260908T120000', 1),
        )

    def test_qos_depth_matches_interface_contract(self):
        self.assertEqual(MODULE.COMMAND_CHECK_QOS_DEPTH, 10)


if __name__ == '__main__':
    unittest.main()
