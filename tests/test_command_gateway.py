"""command_gateway configuration tests; no ROS graph required.

The node itself needs rclpy, but its refusal-to-start rules are pure and
are the part that keeps undecided wire values out of the system.
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
    accepted=1,
    executing=2,
    rejected=3,
    invalid_reason_code=200,
    conflict_reason_code=101,
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

    def test_missing_check_state_refuses(self):
        # TBD-IF-001 의 열린 항목이라 숫자를 지어내지 않는다.
        for field in ('accepted', 'executing', 'rejected'):
            with self.subTest(field=field):
                with self.assertRaises(ValueError) as caught:
                    configure(**{field: -1})
                self.assertIn('TBD-IF-001', str(caught.exception))

    def test_missing_reason_codes_refuse(self):
        for field in ('invalid_reason_code', 'conflict_reason_code'):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    configure(**{field: -1})

    def test_duplicate_check_state_values_refuse(self):
        with self.assertRaises(ValueError):
            configure(accepted=1, executing=1, rejected=2)

    def test_check_state_must_fit_uint8(self):
        with self.assertRaises(ValueError):
            configure(accepted=256)


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
