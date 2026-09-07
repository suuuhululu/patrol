"""Deterministic SafetyGate tests; no robot or ROS graph required.

local_safety_supervisor.py imports its sibling guard modules with plain
(non-package) imports because src/patrol_amr has no __init__.py yet
(9단계 scope) -- see the file's own docstring. We add the module's
directory to sys.path so those plain imports resolve here too, the same
way Python does automatically when the file is run directly.
"""

from pathlib import Path
import sys
import unittest


PATROL_AMR_DIR = (
    Path(__file__).resolve().parents[1] / 'src/patrol_amr/patrol_amr'
)
sys.path.insert(0, str(PATROL_AMR_DIR))

import local_safety_supervisor as lss  # noqa: E402 (sys.path 설정 후 import)
import drive_token_guard as dtg  # noqa: E402
import estop_guard as eg  # noqa: E402
import motion_guard as mg  # noqa: E402

LEASE = 1.0


def gate(robot_id='robot1'):
    return lss.SafetyGate(robot_id)


def grant_token(g, now, token='t1', sequence=1, lease=LEASE, holder=None):
    return g.observe_drive_token(
        token, holder or g.robot_id, lease, sequence, now
    )


def set_estop(g, active, sequence, cause=eg.EStopCause.OPERATOR):
    return g.observe_estop(active, cause, False, 'test', sequence, 0.0, 0.0)


class DefaultStateTests(unittest.TestCase):
    def test_blocked_before_any_message(self):
        g = gate()
        # 초기 상태: token 없음(MISSING) + estop 기본 정지(True) 둘 다 차단.
        reasons = g.blocked_reasons(0.0)
        self.assertIn(mg.MotionBlockReason.DRIVE_TOKEN_NOT_GRANTED, reasons)
        self.assertIn(mg.MotionBlockReason.ESTOP_ACTIVE, reasons)
        self.assertFalse(g.motion_allowed(0.0))


class CombinationTests(unittest.TestCase):
    def test_allowed_only_when_both_guards_permit(self):
        g = gate()
        grant_token(g, 0.0)
        set_estop(g, False, sequence=1)
        self.assertEqual(g.blocked_reasons(0.0), frozenset())
        self.assertTrue(g.motion_allowed(0.0))

    def test_estop_alone_blocks_even_with_valid_token(self):
        g = gate()
        grant_token(g, 0.0)
        set_estop(g, True, sequence=1)
        self.assertEqual(
            g.blocked_reasons(0.0), frozenset({mg.MotionBlockReason.ESTOP_ACTIVE})
        )

    def test_missing_token_alone_blocks_even_without_estop(self):
        g = gate()
        set_estop(g, False, sequence=1)
        self.assertEqual(
            g.blocked_reasons(0.0),
            frozenset({mg.MotionBlockReason.DRIVE_TOKEN_NOT_GRANTED}),
        )


class DriveTokenLeaseTests(unittest.TestCase):
    def test_lease_expiry_blocks_without_a_new_message(self):
        """Q-01: 새 메시지 없이도 lease 가 시계로 만료된다."""
        g = gate()
        grant_token(g, 0.0, lease=1.0)
        set_estop(g, False, sequence=1)
        self.assertTrue(g.motion_allowed(0.5))
        self.assertFalse(g.motion_allowed(1.0))
        self.assertIn(
            mg.MotionBlockReason.DRIVE_TOKEN_NOT_GRANTED, g.blocked_reasons(1.0)
        )

    def test_renewal_before_expiry_keeps_motion_allowed(self):
        g = gate()
        grant_token(g, 0.0, sequence=1, lease=1.0)
        set_estop(g, False, sequence=1)
        grant_token(g, 0.8, sequence=2, lease=1.0)
        self.assertTrue(g.motion_allowed(1.0))


class DiscardedObservationTests(unittest.TestCase):
    def test_other_robots_newer_token_does_not_grant_this_robot(self):
        g = gate('robot1')
        # 최초 관측이라 수락되지만(HOLDER_CHANGED), 이 로봇의 권한은 아니다.
        verdict = g.observe_drive_token('t6', 'robot6', LEASE, 1, 0.0)
        self.assertIs(verdict, dtg.TokenVerdict.HOLDER_CHANGED)
        self.assertFalse(g.motion_allowed(0.0))

    def test_other_robots_duplicate_token_is_discarded(self):
        g = gate('robot1')
        g.observe_drive_token('t6', 'robot6', LEASE, 5, 0.0)
        verdict = g.observe_drive_token('t6', 'robot6', LEASE, 5, 0.1)
        self.assertIs(verdict, dtg.TokenVerdict.OTHER_HOLDER)
        self.assertFalse(g.motion_allowed(0.1))

    def test_stale_estop_sequence_does_not_change_state(self):
        g = gate()
        grant_token(g, 0.0)
        set_estop(g, False, sequence=5)
        self.assertTrue(g.motion_allowed(0.0))
        # 역순 메시지는 폐기되어 상태를 바꾸지 않는다.
        verdict = set_estop(g, True, sequence=3)
        self.assertIs(verdict, eg.EStopVerdict.STALE_SEQUENCE)
        self.assertTrue(g.motion_allowed(0.0))


class RobotIdTests(unittest.TestCase):
    def test_robot_id_property_matches_constructor(self):
        self.assertEqual(gate('robot6').robot_id, 'robot6')

    def test_unknown_robot_id_rejected(self):
        with self.assertRaises(ValueError):
            gate('robot2')


if __name__ == '__main__':
    unittest.main()
