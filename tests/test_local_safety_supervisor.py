"""Deterministic SafetyGate tests; no robot or ROS graph required.

local_safety_supervisor.py imports its sibling guard modules as members
of the patrol_amr package (9단계). We add the package root to sys.path so
those imports resolve straight from the source tree, without needing a
colcon build first.
"""

from pathlib import Path
import sys
import unittest


PATROL_AMR_PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / 'src/patrol_amr'
)
sys.path.insert(0, str(PATROL_AMR_PACKAGE_ROOT))

from patrol_amr import (  # noqa: E402 (sys.path 설정 후 import)
    drive_token_guard as dtg,
    estop_guard as eg,
    local_safety_supervisor as lss,
    motion_guard as mg,
)

LEASE = 1.0
SESSION = 'ctrl-20260907T120000'


def gate(robot_id='robot1'):
    return lss.SafetyGate(robot_id)


def grant_token(
    g,
    now,
    token_id='tok-a',
    message_sequence=1,
    lease=LEASE,
    holder=None,
    control_session_id=SESSION,
):
    return g.observe_drive_token(
        control_session_id,
        token_id,
        holder or g.robot_id,
        lease,
        message_sequence,
        now,
    )


def set_estop(g, active, sequence, reason=17, target=None):
    return g.observe_estop(
        target or g.robot_id, active, reason, False, sequence
    )


class DefaultStateTests(unittest.TestCase):
    def test_blocked_before_any_message(self):
        g = gate()
        # 초기 상태: token 없음(MISSING) + estop 기본 정지(True) 둘 다 차단.
        reasons = g.blocked_reasons(0.0)
        self.assertIn(mg.MotionBlockReason.DRIVE_TOKEN_NOT_GRANTED, reasons)
        self.assertIn(mg.MotionBlockReason.ESTOP_ACTIVE, reasons)
        self.assertFalse(g.motion_allowed(0.0))


class EStopTransitionLogTests(unittest.TestCase):
    def test_estop_active_exposes_reflected_state(self):
        g = gate()
        self.assertTrue(g.estop_active)
        set_estop(g, False, sequence=1)
        self.assertFalse(g.estop_active)

    def test_accepted_release_selects_auto_released_log(self):
        event = lss.estop_transition_event(
            True, False, eg.EStopVerdict.ACCEPTED
        )
        self.assertEqual(event, eg.EVENT_AUTO_RELEASED)

    def test_non_release_or_stale_observation_has_no_release_log(self):
        cases = (
            (True, True, eg.EStopVerdict.ACCEPTED),
            (False, False, eg.EStopVerdict.ACCEPTED),
            (False, True, eg.EStopVerdict.ACCEPTED),
            (True, False, eg.EStopVerdict.STALE_SEQUENCE),
        )
        for previous, current, verdict in cases:
            with self.subTest(
                previous=previous, current=current, verdict=verdict
            ):
                self.assertIsNone(
                    lss.estop_transition_event(previous, current, verdict)
                )


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
        grant_token(g, 0.0, message_sequence=1, lease=1.0)
        set_estop(g, False, sequence=1)
        grant_token(g, 0.8, message_sequence=2, lease=1.0)
        self.assertTrue(g.motion_allowed(1.0))


class DiscardedObservationTests(unittest.TestCase):
    def test_other_robots_newer_token_does_not_grant_this_robot(self):
        g = gate('robot1')
        # 최초 관측이라 수락되지만(HOLDER_CHANGED), 이 로봇의 권한은 아니다.
        verdict = g.observe_drive_token(
            SESSION, 'tok-robot6', 'robot6', LEASE, 1, 0.0
        )
        self.assertIs(verdict, dtg.TokenVerdict.HOLDER_CHANGED)
        self.assertFalse(g.motion_allowed(0.0))

    def test_other_robots_duplicate_token_is_discarded(self):
        g = gate('robot1')
        g.observe_drive_token(
            SESSION, 'tok-robot6', 'robot6', LEASE, 5, 0.0
        )
        verdict = g.observe_drive_token(
            SESSION, 'tok-robot6', 'robot6', LEASE, 5, 0.1
        )
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
