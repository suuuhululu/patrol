"""command_gateway configuration tests; no ROS graph required.

The node itself needs rclpy, but its refusal-to-start rules are pure and keep
robot/session identity aligned with the fixed v1.0 wire values.
"""

from pathlib import Path
import sys
import unittest


# 이 시험은 두 패키지를 걸친다. command_gateway 는 안전 패키지로 옮겼지만
# check_state 매핑 타입은 patrol_amr 의 command_check 에 남아 있다.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for package_root in ('src/patrol_amr_safety', 'src/patrol_amr'):
    sys.path.insert(0, str(REPOSITORY_ROOT / package_root))

from patrol_amr import command_check as cc  # noqa: E402
from patrol_amr_safety import command_gateway as cg  # noqa: E402


VALID = dict(
    robot_id='robot1',
    source_session_id='robot1-20260908T160000',
)


def configure(**overrides):
    values = dict(VALID)
    values.update(overrides)
    return cg.validate_configuration(**values)


class ConfigurationTests(unittest.TestCase):
    def test_valid_configuration_returns_the_mapping(self):
        mapping = configure()
        self.assertIsInstance(mapping, cc.CheckStateMapping)
        self.assertEqual(mapping.wire_value(cc.CheckMeaning.ACCEPTED), 1)
        self.assertEqual(mapping.wire_value(cc.CheckMeaning.EXECUTING), 2)
        self.assertEqual(mapping.wire_value(cc.CheckMeaning.REJECTED), 3)

    def test_unknown_robot_id_refuses(self):
        for robot_id in ('', 'robot2', 'ROBOT1'):
            with self.subTest(robot_id=robot_id):
                with self.assertRaises(ValueError):
                    configure(robot_id=robot_id)

    def test_missing_source_session_refuses(self):
        with self.assertRaises(ValueError):
            configure(source_session_id='')

class DatabasePathTests(unittest.TestCase):
    def test_path_is_per_robot_and_outside_the_install_tree(self):
        one = cg.default_database_path('robot1')
        six = cg.default_database_path('robot6')
        self.assertNotEqual(one, six)
        self.assertIn('robot1', one)
        self.assertIn('robot6', six)
        # 재빌드가 "이미 실행한 명령" 기록을 지우면 안 된다.
        self.assertNotIn('/install/', one)

    def test_state_home_is_honoured(self):
        import os

        previous = os.environ.get('XDG_STATE_HOME')
        os.environ['XDG_STATE_HOME'] = '/tmp/patrol-state-test'
        try:
            path = cg.default_database_path('robot1')
        finally:
            if previous is None:
                del os.environ['XDG_STATE_HOME']
            else:
                os.environ['XDG_STATE_HOME'] = previous
        self.assertTrue(path.startswith('/tmp/patrol-state-test'))


if __name__ == '__main__':
    unittest.main()
