"""Admission deadline and restart replay policy tests."""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/patrol_amr_safety'))

from patrol_amr_safety import pending_dispatch as MODULE  # noqa: E402


class PendingDispatchTest(unittest.TestCase):
    def test_new_process_replays_unexpired_pending_once(self):
        self.assertIs(
            MODULE.decide(
                received_at=10.0, now=13.999,
                replayed_since_start=False,
            ),
            MODULE.PendingAction.REDISPATCH,
        )
        self.assertIs(
            MODULE.decide(
                received_at=10.0, now=13.999,
                replayed_since_start=True,
            ),
            MODULE.PendingAction.WAIT,
        )

    def test_four_seconds_is_timeout(self):
        self.assertIs(
            MODULE.decide(
                received_at=10.0, now=14.0,
                replayed_since_start=False,
            ),
            MODULE.PendingAction.REJECT_TIMEOUT,
        )

    def test_clock_rollback_fails_closed(self):
        self.assertIs(
            MODULE.decide(
                received_at=10.0, now=9.0,
                replayed_since_start=False,
            ),
            MODULE.PendingAction.REJECT_TIMEOUT,
        )

    def test_invalid_times_are_rejected(self):
        for value in (True, -1.0, float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.decide(
                    received_at=value, now=1.0,
                    replayed_since_start=False,
                )


if __name__ == '__main__':
    unittest.main()
