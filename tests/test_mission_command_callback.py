"""Tests for MissionCommand parsing without generated ROS classes."""

import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


sys.path.insert(0, str(
    Path(__file__).resolve().parents[1] / 'src/patrol_amr'))

from patrol_amr.mission_command_parser import (
    InvalidMissionCommand, MissionCommandParser)
from patrol_amr.mission_types import MissionType


COMMAND_ID = 'cmd-ctrl-20260907T160000-robot1-start-0001'
MISSION_ID = 'msn-ctrl-20260907T160000-robot1-0001'


def message(**changes):
    """Create a minimal object matching the proposed MissionCommand fields."""
    pose = SimpleNamespace(
        header=SimpleNamespace(
            frame_id='', stamp=SimpleNamespace(sec=0, nanosec=0)),
        pose=SimpleNamespace(
            position=SimpleNamespace(x=0.0, y=0.0, z=0.0),
            orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
        ),
    )
    values = {
        'command_id': COMMAND_ID,
        'mission_id': MISSION_ID,
        'robot_id': 'robot1',
        'command': int(MissionType.START_PATROL),
        'target_id': 'robot1_default',
        'target_pose': pose,
        'issued_by': 'control',
    }
    values.update(changes)
    return SimpleNamespace(**values)


class MissionCommandParserTest(unittest.TestCase):
    """Exercise confirmed validation while leaving TBD fields open."""

    def setUp(self):
        """Create the robot1 parser used by each test."""
        self.parser = MissionCommandParser('robot1')

    def test_accepts_structured_ids(self):
        """A valid command becomes a deterministic internal request."""
        request = self.parser.parse(message())
        self.assertEqual(request.command_id, COMMAND_ID)
        self.assertEqual(request.mission_id, MISSION_ID)
        self.assertEqual(request.target_id, 'robot1_default')

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

    def test_safe_zone_requires_empty_target_and_pose(self):
        """AMR chooses the safe-zone pose rather than accepting one."""
        request = self.parser.parse(
            message(
                command=int(MissionType.MOVE_TO_SAFE_ZONE),
                target_id='',
            ))
        self.assertIsNone(request.target_pose)

    def test_rejects_nonempty_target_pose(self):
        half = math.sqrt(0.5)
        pose = SimpleNamespace(
            header=SimpleNamespace(
                frame_id='map', stamp=SimpleNamespace(sec=0, nanosec=0)),
            pose=SimpleNamespace(
                position=SimpleNamespace(x=1.25, y=-2.5, z=0.0),
                orientation=SimpleNamespace(
                    x=0.0, y=0.0, z=half, w=half),
            ),
        )
        with self.assertRaises(InvalidMissionCommand) as raised:
            self.parser.parse(message(target_pose=pose))
        self.assertEqual(raised.exception.reason_code, 205)

    def test_unused_pose_requires_the_generated_ros_default(self):
        candidate = message()
        candidate.target_pose.pose.orientation.w = 0.0
        with self.assertRaises(InvalidMissionCommand):
            self.parser.parse(candidate)

    def test_stop_allows_empty_mission_when_idle(self):
        request = self.parser.parse(message(
            command=int(MissionType.STOP), mission_id='', target_id=''))
        self.assertEqual(request.mission_id, '')

    def test_dock_requires_robot_specific_target(self):
        with self.assertRaises(InvalidMissionCommand) as raised:
            self.parser.parse(message(
                command=int(MissionType.DOCK), target_id='dock_6'))
        self.assertEqual(raised.exception.reason_code, 201)

        request = self.parser.parse(message(
            command=int(MissionType.DOCK), target_id='dock_1'))
        self.assertEqual(request.target_id, 'dock_1')
