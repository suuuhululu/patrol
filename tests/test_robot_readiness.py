"""Tests for AMCL, LiDAR, and odometry motion readiness."""

import unittest

from patrol_amr.robot_readiness import RobotReadiness


class FakeMonotonic:
    """Controllable steady clock for pose-freshness tests."""

    def __init__(self):
        self.value = 10.0

    def __call__(self):
        return self.value


class RobotReadinessTest(unittest.TestCase):
    """Apply the confirmed Q-05 pose age and startup stream checks."""

    def setUp(self):
        self.clock = FakeMonotonic()
        self.readiness = RobotReadiness(self.clock)

    def test_all_inputs_make_robot_ready(self):
        """A valid fresh pose plus scan and odom opens the live gate."""
        self.readiness.record_pose(9_500_000_000, 10_000_000_000, True)
        self.readiness.record_scan()
        self.readiness.record_odom()
        self.assertTrue(self.readiness.snapshot().ready)

    def test_pose_becomes_stale_after_q05_limit(self):
        """Pose age over 1.5 seconds closes the gate without a new pose."""
        self.readiness.record_pose(9_500_000_000, 10_000_000_000, True)
        self.readiness.record_scan()
        self.readiness.record_odom()
        self.clock.value += 1.01
        snapshot = self.readiness.snapshot()
        self.assertFalse(snapshot.ready)
        self.assertIn('AMCL_POSE_STALE', snapshot.blocking_reasons)

    def test_future_or_zero_timestamp_is_invalid(self):
        """A malformed source timestamp cannot satisfy pose validity."""
        self.readiness.record_pose(0, 10_000_000_000, True)
        self.assertIn(
            'AMCL_POSE_INVALID_OR_MISSING',
            self.readiness.snapshot().blocking_reasons,
        )
