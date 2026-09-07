"""Deterministic drive token guard tests; no robot or ROS graph required."""

import importlib.util
from pathlib import Path
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / 'src/patrol_amr/'
          'patrol_amr/drive_token_guard.py')
SPEC = importlib.util.spec_from_file_location('drive_token_guard', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
V = MODULE.TokenVerdict
A = MODULE.DriveAuthority

LEASE = 1.0


def guard(robot_id='robot1'):
    return MODULE.DriveTokenGuard(robot_id)


def accept(g, now, token='t1', sequence=1, holder=None, lease=LEASE):
    return g.observe(token, holder or g.robot_id, lease, sequence, now)


class DurationTests(unittest.TestCase):
    def test_duration_to_seconds(self):
        self.assertEqual(MODULE.duration_to_seconds(1, 0), 1.0)
        self.assertAlmostEqual(MODULE.duration_to_seconds(0, 500_000_000), 0.5)
        self.assertAlmostEqual(MODULE.duration_to_seconds(2, 250_000_000), 2.25)

    def test_duration_rejects_non_int(self):
        for sec, nanosec in ((1.0, 0), (0, 1.5), (True, 0), (0, False)):
            with self.subTest(sec=sec, nanosec=nanosec):
                with self.assertRaises(ValueError):
                    MODULE.duration_to_seconds(sec, nanosec)


class AcceptanceTests(unittest.TestCase):
    def test_initial_state_has_no_authority(self):
        g = guard()
        self.assertIs(g.authority(0.0), A.MISSING)
        self.assertFalse(g.drive_allowed(0.0))
        self.assertEqual(g.remaining_lease(0.0), 0.0)
        self.assertIsNone(g.token)

    def test_valid_token_grants_until_lease_end(self):
        g = guard()
        self.assertIs(accept(g, 0.0), V.ACCEPTED)
        self.assertIs(g.authority(0.0), A.GRANTED)
        self.assertIs(g.authority(0.999999), A.GRANTED)
        # 만료 경계는 포함이다. lease 경과 시점부터 권한이 없다.
        self.assertIs(g.authority(1.0), A.EXPIRED)
        self.assertIs(g.authority(1.5), A.EXPIRED)
        self.assertFalse(g.drive_allowed(1.0))

    def test_remaining_lease_counts_down_and_floors_at_zero(self):
        g = guard()
        accept(g, 0.0)
        self.assertAlmostEqual(g.remaining_lease(0.25), 0.75)
        self.assertEqual(g.remaining_lease(1.0), 0.0)
        self.assertEqual(g.remaining_lease(9.0), 0.0)

    def test_renewal_extends_lease_from_accepted_message(self):
        g = guard()
        accept(g, 0.0, sequence=1)
        self.assertIs(accept(g, 0.8, sequence=2), V.ACCEPTED)
        # 0.8 초에 갱신했으므로 1.0 초에도 유효하고 1.8 초에 만료된다.
        self.assertIs(g.authority(1.0), A.GRANTED)
        self.assertIs(g.authority(1.8), A.EXPIRED)

    def test_message_lease_duration_is_used(self):
        g = guard()
        accept(g, 0.0, lease=0.4)
        self.assertIs(g.authority(0.39), A.GRANTED)
        self.assertIs(g.authority(0.4), A.EXPIRED)


class DiscardTests(unittest.TestCase):
    def test_newer_other_holder_message_invalidates_immediately(self):
        g = guard('robot1')
        accept(g, 0.0, sequence=5)
        self.assertIs(
            g.observe('t6', 'robot6', LEASE, 6, 0.2), V.HOLDER_CHANGED
        )
        # 관제가 권한을 넘겼으므로 lease 만료를 기다리지 않는다.
        self.assertIs(g.authority(0.2), A.MISSING)
        self.assertIsNone(g.token)
        self.assertFalse(g.revoked_last)

    def test_duplicate_other_holder_message_changes_nothing(self):
        g = guard('robot1')
        self.assertIs(
            g.observe('t6', 'robot6', LEASE, 6, 0.0), V.HOLDER_CHANGED
        )
        # 같은 epoch 의 중복 수신은 폐기한다.
        self.assertIs(
            g.observe('t6', 'robot6', LEASE, 6, 0.1), V.OTHER_HOLDER
        )
        self.assertEqual(g.last_sequence, 6)

    def test_handover_then_return_restores_authority(self):
        g = guard('robot1')
        accept(g, 0.0, token='t1', sequence=5)
        g.observe('t6', 'robot6', LEASE, 6, 0.2)
        self.assertIs(g.authority(0.2), A.MISSING)
        self.assertIs(
            g.observe('t1b', 'robot1', LEASE, 7, 0.4), V.ACCEPTED
        )
        self.assertIs(g.authority(0.4), A.GRANTED)

    def test_stale_or_equal_sequence_is_discarded(self):
        g = guard()
        accept(g, 0.0, sequence=7)
        for sequence in (0, 6, 7):
            with self.subTest(sequence=sequence):
                self.assertIs(
                    g.observe('t1', 'robot1', LEASE, sequence, 0.1),
                    V.STALE_SEQUENCE,
                )
        self.assertIs(accept(g, 0.2, sequence=8), V.ACCEPTED)

    def test_discarded_message_does_not_extend_lease(self):
        g = guard()
        accept(g, 0.0, sequence=7)
        # 수신 사실만으로 lease 를 연장하지 않는다 (interfaces.md 3절).
        g.observe('t1', 'robot1', LEASE, 7, 0.9)
        self.assertIs(g.authority(1.0), A.EXPIRED)

    def test_non_positive_or_non_finite_lease_is_discarded(self):
        for lease in (0.0, -1.0, float('nan'), float('inf')):
            with self.subTest(lease=lease):
                g = guard()
                verdict = g.observe('t1', 'robot1', lease, 1, 0.0)
                self.assertIs(verdict, V.INVALID_LEASE)
                self.assertIs(g.authority(0.0), A.MISSING)


class RevocationTests(unittest.TestCase):
    def test_empty_token_revokes_immediately(self):
        g = guard()
        accept(g, 0.0)
        self.assertIs(g.observe('', 'robot1', LEASE, 2, 0.1), V.REVOKED)
        # 회수는 lease 만료를 기다리지 않는다.
        self.assertIs(g.authority(0.1), A.MISSING)
        self.assertTrue(g.revoked_last)
        self.assertIsNone(g.token)

    def test_changed_token_invalidates_previous_immediately(self):
        g = guard()
        accept(g, 0.0, token='t1', sequence=1)
        # 새 token 은 sequence 가 앞서므로 수락되고 권한이 이어진다.
        self.assertIs(
            g.observe('t2', 'robot1', LEASE, 2, 0.1), V.ACCEPTED
        )
        self.assertEqual(g.token, 't2')
        self.assertIs(g.authority(0.1), A.GRANTED)

    def test_revocation_sets_floor_to_the_empty_token_epoch(self):
        g = guard()
        accept(g, 0.0, sequence=5)
        g.observe('', 'robot1', LEASE, 6, 0.1)
        self.assertEqual(g.sequence_token, '')
        self.assertEqual(g.last_sequence, 6)
        # 같은 회수 메시지의 중복 수신은 폐기한다.
        self.assertIs(
            g.observe('', 'robot1', LEASE, 6, 0.2), V.STALE_SEQUENCE
        )
        self.assertIs(g.authority(0.2), A.MISSING)

    def test_accept_clears_revoked_flag(self):
        g = guard()
        accept(g, 0.0, sequence=1)
        g.observe('', 'robot1', LEASE, 2, 0.1)
        self.assertTrue(g.revoked_last)
        accept(g, 0.2, token='t2', sequence=2)
        self.assertFalse(g.revoked_last)



class SequenceEpochTests(unittest.TestCase):
    """TBD-IF-002 결정(2026-09-07): sequence 하한은 token 문자열 단위다."""

    def test_same_token_replay_is_discarded(self):
        g = guard()
        accept(g, 0.0, token='t1', sequence=7)
        for sequence in (0, 3, 7):
            with self.subTest(sequence=sequence):
                self.assertIs(
                    g.observe('t1', 'robot1', LEASE, sequence, 0.1),
                    V.STALE_SEQUENCE,
                )

    def test_new_token_resets_the_sequence_floor(self):
        g = guard()
        accept(g, 0.0, token='t1', sequence=900)
        self.assertIs(g.observe('t2', 'robot1', LEASE, 1, 0.1), V.ACCEPTED)
        self.assertIs(g.authority(0.1), A.GRANTED)
        self.assertEqual(g.sequence_token, 't2')
        self.assertEqual(g.last_sequence, 1)

    def test_control_restart_recovers_driving(self):
        g = guard()
        accept(g, 0.0, token='epoch-a', sequence=MODULE.SEQUENCE_MAX - 1)
        g.observe('', 'robot1', LEASE, MODULE.SEQUENCE_MAX, 0.1)
        self.assertIs(g.authority(0.1), A.MISSING)
        # 재시작으로 sequence 가 0 으로 돌아가도 새 token epoch 이면 회복한다.
        self.assertIs(
            g.observe('epoch-b', 'robot1', LEASE, 0, 0.2), V.ACCEPTED
        )
        self.assertIs(g.authority(0.2), A.GRANTED)

class CallerErrorTests(unittest.TestCase):
    def test_robot_id_must_be_known(self):
        for robot_id in ('robot2', '', 'ROBOT1', None):
            with self.subTest(robot_id=robot_id):
                with self.assertRaises(ValueError):
                    MODULE.DriveTokenGuard(robot_id)

    def test_invalid_argument_types_raise(self):
        g = guard()
        bad = [
            (None, 'robot1', LEASE, 1, 0.0),
            ('t1', None, LEASE, 1, 0.0),
            ('t1', 'robot1', LEASE, 1.5, 0.0),
            ('t1', 'robot1', LEASE, True, 0.0),
            ('t1', 'robot1', LEASE, -1, 0.0),
            ('t1', 'robot1', LEASE, MODULE.SEQUENCE_MAX + 1, 0.0),
            ('t1', 'robot1', None, 1, 0.0),
            ('t1', 'robot1', LEASE, 1, float('nan')),
            ('t1', 'robot1', LEASE, 1, None),
        ]
        for args in bad:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    g.observe(*args)

    def test_observation_clock_must_not_move_backwards(self):
        g = guard()
        accept(g, 5.0, sequence=1)
        with self.assertRaises(ValueError):
            accept(g, 4.9, sequence=2)

    def test_queries_are_order_independent(self):
        g = guard()
        accept(g, 0.0)
        # 조회는 시계를 소비하지 않는다. 같은 주기 안에서 임의 순서로 물어본다.
        self.assertIs(g.authority(1.5), A.EXPIRED)
        self.assertIs(g.authority(0.5), A.GRANTED)
        self.assertAlmostEqual(g.remaining_lease(0.25), 0.75)
        self.assertIs(g.authority(0.5), A.GRANTED)

    def test_uint32_max_sequence_is_accepted(self):
        g = guard()
        self.assertIs(
            g.observe('t1', 'robot1', LEASE, MODULE.SEQUENCE_MAX, 0.0),
            V.ACCEPTED,
        )


if __name__ == '__main__':
    unittest.main()
