"""Static contract checks for the mission supervisor ROS boundary."""

import ast
from pathlib import Path
import unittest


SOURCE = (
    Path(__file__).resolve().parents[1]
    / 'src/patrol_amr/patrol_amr/mission_supervisor.py'
)


class MissionSupervisorWiringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        cls.string_literals = {
            node.value
            for node in ast.walk(cls.tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        cls.imported_names = {
            alias.name
            for node in ast.walk(cls.tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }

    def test_uses_internal_mission_dispatch_topic(self):
        assignments = {
            target.id: node.value.value
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        self.assertEqual(assignments['MISSION_DISPATCH_TOPIC'], 'mission_dispatch')
        self.assertNotIn('mission_command', self.string_literals)

    def test_does_not_duplicate_local_safety_drive_token_guard(self):
        self.assertNotIn('/control/drive_token', self.string_literals)
        self.assertNotIn('DriveTokenCallback', self.imported_names)
        self.assertNotIn('MissionDriveTokenGuard', self.imported_names)


if __name__ == '__main__':
    unittest.main()
