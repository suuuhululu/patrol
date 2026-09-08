"""Tests for MissionCommand parsing without generated ROS classes."""

import math
from types import SimpleNamespace
import unittest

from patrol_amr.mission_command_parser import (
    InvalidMissionCommand, MissionCommandParser)
from patrol_amr.mission_types import MissionType


COMMAND_ID = 'cmd-ctrl-20260907T160000-robot1-start-0001'
MISSION_ID = 'msn-ctrl-20260907T160000-robot1-0001'


def message(**changes):
    """Create a minimal object matching the proposed MissionCommand fields."""
    half = math.sqrt(0.5)
    pose = SimpleNamespace(
        header=SimpleNamespace(frame_id='map'),
        pose=SimpleNamespace(
            position=SimpleNamespace(x=1.25, y=-2.5),
            orientation=SimpleNamespace(x=0.0, y=0.0, z=half, w=half),
        ),
    )
    values = {
        'command_id': COMMAND_ID,
        'mission_id': MISSION_ID,
        'robot_id': 'robot1',
        'command': int(MissionType.START_PATROL),
        'target_id': 'patrol-a',
        'target_pose': pose,
        'issued_by': 'control',
        'parameters_json': '{"b":2,"a":1}',
    }
    values.update(changes)
    return SimpleNamespace(**values)


class MissionCommandParserTest(unittest.TestCase):
    """Exercise confirmed validation while leaving TBD fields open."""

    def setUp(self):
        """Create the robot1 parser used by each test."""
        self.parser = MissionCommandParser('robot1')

    def test_accepts_structured_ids_and_normalizes_json(self):
        """A valid command becomes a deterministic internal request."""
        request = self.parser.parse(message())
        self.assertEqual(request.command_id, COMMAND_ID)
        self.assertEqual(request.mission_id, MISSION_ID)
        self.assertEqual(request.parameters_json, '{"a":1,"b":2}')

    def test_rejects_wrong_robot(self):
        """Namespace identity cannot accept the other robot's command."""
        with self.assertRaises(InvalidMissionCommand):
            self.parser.parse(message(robot_id='robot6'))

    def test_rejects_legacy_uuid(self):
        """The replaced UUID command identity is no longer accepted."""
        with self.assertRaises(InvalidMissionCommand):
            self.parser.parse(
                message(command_id='00000000-0000-4000-8000-000000000001'))

    def test_rejects_invalid_mission_id(self):
        """Mission correlation requires the confirmed structured ID."""
        with self.assertRaises(InvalidMissionCommand):
            self.parser.parse(message(mission_id=''))

    def test_safe_zone_requires_map_pose_and_converts_yaw(self):
        """Safe-zone navigation receives a finite map-frame pose."""
        request = self.parser.parse(
            message(command=int(MissionType.MOVE_TO_SAFE_ZONE)))
        self.assertAlmostEqual(request.target_pose.yaw_deg, 90.0)

    def test_rejects_invalid_parameters_json(self):
        """Schema is TBD, but malformed JSON is never accepted."""
        with self.assertRaises(InvalidMissionCommand):
            self.parser.parse(message(parameters_json='{bad-json'))

    def test_does_not_invent_parameters_schema(self):
        """A valid non-object remains allowed while TBD-IF-001 is open."""
        request = self.parser.parse(message(parameters_json='[2, 1]'))
        self.assertEqual(request.parameters_json, '[2,1]')
