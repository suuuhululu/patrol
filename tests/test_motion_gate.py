"""Tests for final-safety and stock-Nav2 readiness policies."""

import unittest

from patrol_amr.motion_gate import MotionGate
from patrol_amr.robot_readiness import ReadinessSnapshot


class MotionGateTest(unittest.TestCase):
    """Keep final Q-05 checks separate from the hardware test path."""

    def test_final_safety_path_enforces_q05_pose_age(self):
        """An old AMCL pose blocks the final integrated drive path."""
        snapshot = ReadinessSnapshot(True, 2.0, True, True)
        gate = MotionGate(
            'robot6', True, False, 'ENABLE_ROBOT6_MOTION', lambda: snapshot)
        self.assertFalse(gate.ready())
        self.assertIn('AMCL_POSE_STALE', gate.blocking_reasons())

    def test_stock_nav2_test_accepts_valid_stationary_pose(self):
        """Stock Nav2 handles TF freshness after a valid pose was received."""
        snapshot = ReadinessSnapshot(True, 80.0, True, True)
        gate = MotionGate(
            'robot6', False, True, 'ENABLE_ROBOT6_MOTION', lambda: snapshot)
        self.assertTrue(gate.ready())

