"""Static checks for mission/status persistent-path launch boundaries."""

import ast
from pathlib import Path
import unittest


SOURCE = (
    Path(__file__).resolve().parents[1]
    / 'src/patrol_amr/launch/patrol.launch.py'
)


class PatrolLaunchContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        cls.string_literals = {
            node.value
            for node in ast.walk(cls.tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

    def test_exposes_robot_specific_persistent_paths(self):
        for parameter_name in (
            'command_store_path',
            'mission_status_path',
            'report_outbox_path',
        ):
            with self.subTest(parameter_name=parameter_name):
                self.assertIn(parameter_name, self.string_literals)


if __name__ == '__main__':
    unittest.main()
