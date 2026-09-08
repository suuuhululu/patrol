"""Deterministic SafetyGate tests; no robot or ROS graph required.

local_safety_supervisor.py imports its sibling guard modules as members
of the patrol_amr_safety package. We add the package root to sys.path so
those imports resolve straight from the source tree, without needing a
colcon build first.
"""

from pathlib import Path
import sys
import unittest


PATROL_AMR_PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / 'src/patrol_amr_safety'
)
sys.path.insert(0, str(PATROL_AMR_PACKAGE_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/patrol_amr'))

from patrol_amr_safety import (  # noqa: E402 (sys.path 설정 후 import)
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
    g.observe_heartbeat(control_session_id, message_sequence, now)
    return g.observe_drive_token(
        control_session_id,
        token_id,
        holder or g.robot_id,
        lease,
        message_sequence,
        now,
    )


def set_estop(g, active, sequence, reason=1, target=None):
    return g.observe_estop(target or g.robot_id, active, reason, sequence)


class DefaultStateTests(unittest.TestCase):
    def test_blocked_before_any_message(self):
        g = gate()
        # 초기 상태: token 없음(MISSING) + estop 기본 정지(True) 둘 다 차단.
        reasons = g.blocked_reasons(0.0)
        self.assertIn(mg.MotionBlockReason.DRIVE_TOKEN_NOT_GRANTED, reasons)
        self.assertIn(mg.MotionBlockReason.ESTOP_ACTIVE, reasons)
        self.assertIn(mg.MotionBlockReason.HEARTBEAT_NOT_HEALTHY, reasons)
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
        g.observe_heartbeat(SESSION, 1, 0.0)
        set_estop(g, False, sequence=1)
        self.assertEqual(
            g.blocked_reasons(0.0),
            frozenset({mg.MotionBlockReason.DRIVE_TOKEN_NOT_GRANTED}),
        )

    def test_heartbeat_timeout_blocks_and_new_session_revokes_token(self):
        g = gate()
        grant_token(g, 0.0)
        set_estop(g, False, sequence=1)
        self.assertTrue(g.motion_allowed(0.5))
        self.assertFalse(g.motion_allowed(1.1))
        self.assertIn(
            mg.MotionBlockReason.HEARTBEAT_NOT_HEALTHY,
            g.blocked_reasons(1.1),
        )
        g.observe_heartbeat('ctrl-20260907T120100', 1, 1.2)
        self.assertEqual(g.token_status(1.2), lss.TokenStatus('', False))


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


class TokenStatusTests(unittest.TestCase):
    """16단계 RobotStatus용 accepted token view."""

    def test_missing_token_is_empty_and_invalid(self):
        self.assertEqual(gate().token_status(0.0), lss.TokenStatus('', False))

    def test_accepted_token_exposes_id_and_validity(self):
        g = gate()
        grant_token(g, 0.0, token_id='tok-current')
        self.assertEqual(
            g.token_status(0.5), lss.TokenStatus('tok-current', True)
        )

    def test_expired_token_is_empty_and_invalid(self):
        g = gate()
        grant_token(g, 0.0, token_id='tok-expiring', lease=1.0)
        self.assertEqual(g.token_status(1.0), lss.TokenStatus('', False))

    def test_revoked_token_is_empty_and_invalid(self):
        g = gate()
        grant_token(g, 0.0)
        grant_token(g, 0.1, token_id='', message_sequence=2)
        self.assertEqual(g.token_status(0.1), lss.TokenStatus('', False))

    def test_other_holder_is_empty_and_invalid(self):
        g = gate('robot1')
        g.observe_drive_token(
            SESSION, 'tok-robot6', 'robot6', LEASE, 1, 0.0
        )
        self.assertEqual(g.token_status(0.0), lss.TokenStatus('', False))


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


class CandidateOutputTests(unittest.TestCase):
    """12단계 최종 속도 게이트. 두 시계를 따로 넘긴다."""

    def permit(self, g, monotonic_now=0.0):
        grant_token(g, monotonic_now)
        set_estop(g, False, sequence=1)

    def test_no_candidate_blocks_even_when_permitted(self):
        g = gate()
        self.permit(g)
        self.assertTrue(g.motion_allowed(0.0))
        output, reasons = g.output(0.0, 100.0)
        self.assertEqual(output, mg.STOP)
        self.assertEqual(
            reasons, frozenset({mg.MotionBlockReason.CANDIDATE_MISSING})
        )

    def test_fresh_candidate_passes_through_unchanged(self):
        g = gate()
        self.permit(g)
        self.assertTrue(g.observe_candidate(0.25, -0.4, 100.0))
        output, reasons = g.output(0.0, 100.2)
        self.assertEqual(output, (0.25, -0.4))
        self.assertEqual(reasons, frozenset())

    def test_candidate_ages_out_under_q17(self):
        g = gate()
        self.permit(g)
        g.observe_candidate(0.25, 0.0, 100.0)
        # 0.5초 경계는 통과, 넘으면 정지.
        self.assertEqual(g.output(0.0, 100.5)[1], frozenset())
        output, reasons = g.output(0.0, 100.6)
        self.assertEqual(output, mg.STOP)
        self.assertEqual(
            reasons, frozenset({mg.MotionBlockReason.CANDIDATE_STALE})
        )

    def test_expired_lease_stops_a_fresh_candidate(self):
        g = gate()
        self.permit(g, monotonic_now=0.0)
        g.observe_candidate(0.25, 0.0, 100.0)
        self.assertEqual(g.output(0.5, 100.0)[1], frozenset())
        # Q-01 lease 는 monotonic 시계로만 만료된다.
        output, reasons = g.output(LEASE + 0.1, 100.0)
        self.assertEqual(output, mg.STOP)
        self.assertEqual(
            reasons,
            frozenset({
                mg.MotionBlockReason.DRIVE_TOKEN_NOT_GRANTED,
                mg.MotionBlockReason.HEARTBEAT_NOT_HEALTHY,
            }),
        )

    def test_active_estop_stops_a_fresh_candidate(self):
        g = gate()
        self.permit(g)
        g.observe_candidate(0.25, 0.0, 100.0)
        set_estop(g, True, sequence=2)
        output, reasons = g.output(0.0, 100.0)
        self.assertEqual(output, mg.STOP)
        self.assertEqual(
            reasons, frozenset({mg.MotionBlockReason.ESTOP_ACTIVE})
        )

    def test_two_clocks_are_independent(self):
        # monotonic 이 진행해도 후보 age 는 ROS 시계로만 잰다.
        g = gate()
        self.permit(g, monotonic_now=0.0)
        g.observe_candidate(0.25, 0.0, 100.0)
        output, reasons = g.output(0.9, 100.0)
        self.assertEqual(output, (0.25, 0.0))
        self.assertEqual(reasons, frozenset())

    def test_non_finite_candidate_is_rejected_and_previous_kept(self):
        g = gate()
        self.permit(g)
        g.observe_candidate(0.25, 0.0, 100.0)
        for linear, angular, stamp in (
            (float('nan'), 0.0, 100.1),
            (0.0, float('inf'), 100.1),
            (0.0, 0.0, float('nan')),
            (True, 0.0, 100.1),
            ('0.1', 0.0, 100.1),
        ):
            with self.subTest(linear=linear, angular=angular, stamp=stamp):
                self.assertFalse(g.observe_candidate(linear, angular, stamp))
        # 폐기된 표본은 저장되지 않아 이전 후보가 그대로 남고, 그 후보는
        # Q-17 로 만료된다 — 실패 방향이 STOP 이다.
        self.assertEqual(g.output(0.0, 100.2)[0], (0.25, 0.0))
        self.assertEqual(g.output(0.0, 100.6)[0], mg.STOP)

    def test_int_candidate_components_accepted(self):
        g = gate()
        self.permit(g)
        self.assertTrue(g.observe_candidate(0, 0, 100))
        self.assertEqual(g.output(0.0, 100.0)[0], (0.0, 0.0))

    def test_every_reason_can_apply_at_once(self):
        g = gate()
        grant_token(g, 0.0)
        set_estop(g, True, sequence=1)
        g.observe_candidate(0.25, 0.0, 100.0)
        _, reasons = g.output(LEASE + 0.1, 101.0)
        self.assertEqual(
            reasons,
            frozenset({
                mg.MotionBlockReason.DRIVE_TOKEN_NOT_GRANTED,
                mg.MotionBlockReason.ESTOP_ACTIVE,
                mg.MotionBlockReason.HEARTBEAT_NOT_HEALTHY,
                mg.MotionBlockReason.CANDIDATE_STALE,
            }),
        )


class PermissionGateIsolationTests(unittest.TestCase):
    """motion_allowed 가 후보 유무에 흔들리지 않아야 한다 (6단계 회귀)."""

    def test_motion_allowed_ignores_missing_candidate(self):
        g = gate()
        grant_token(g, 0.0)
        set_estop(g, False, sequence=1)
        self.assertTrue(g.motion_allowed(0.0))
        self.assertEqual(
            g.output(0.0, 100.0)[1],
            frozenset({mg.MotionBlockReason.CANDIDATE_MISSING}),
        )

    def test_motion_allowed_ignores_stale_candidate(self):
        g = gate()
        grant_token(g, 0.0)
        set_estop(g, False, sequence=1)
        g.observe_candidate(0.25, 0.0, 100.0)
        self.assertTrue(g.motion_allowed(0.0))
        self.assertEqual(
            g.output(0.0, 200.0)[1],
            frozenset({mg.MotionBlockReason.CANDIDATE_STALE}),
        )

    def test_blocked_reasons_never_reports_candidate_reasons(self):
        g = gate()
        candidate_reasons = {
            mg.MotionBlockReason.CANDIDATE_MISSING,
            mg.MotionBlockReason.CANDIDATE_STALE,
        }
        for monotonic_now in (0.0, LEASE + 1.0):
            with self.subTest(now=monotonic_now):
                self.assertFalse(
                    candidate_reasons & set(g.blocked_reasons(monotonic_now))
                )


class RobotIdTests(unittest.TestCase):
    def test_robot_id_property_matches_constructor(self):
        self.assertEqual(gate('robot6').robot_id, 'robot6')

    def test_unknown_robot_id_rejected(self):
        with self.assertRaises(ValueError):
            gate('robot2')


if __name__ == '__main__':
    unittest.main()
