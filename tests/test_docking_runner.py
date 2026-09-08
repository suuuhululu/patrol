"""Tests for docking state confirmation and fail-closed sensor handling."""

import sys
import threading
from types import ModuleType
import unittest
from unittest.mock import patch

from patrol_amr.docking_runner import DockingRunner
from patrol_amr.navigation_types import NavigationResult


class FakeClock:
    """Advance one second whenever the fake ROS executor spins."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        """Return simulated monotonic time."""
        return self.now

    def advance(self):
        """Advance the simulated executor by one second."""
        self.now += 1.0


class DockingRunnerTest(unittest.TestCase):
    """Verify the continuous dock-sensor part of Q-09."""

    def test_unknown_dock_state_blocks_undock_assumption(self):
        """An absent sensor state cannot be treated as already undocked."""
        navigator = type('Navigator', (), {'is_docked': None})()
        result = DockingRunner(navigator).ensure_undocked(threading.Event())
        self.assertIs(result, NavigationResult.UNKNOWN)

    def test_docked_state_must_remain_true_for_stable_window(self):
        """Three uninterrupted simulated seconds confirm docking."""
        clock = FakeClock()
        navigator = type('Navigator', (), {'is_docked': True})()
        rclpy = ModuleType('rclpy')
        rclpy.spin_once = lambda node, timeout_sec: clock.advance()
        with patch.dict(sys.modules, {'rclpy': rclpy}):
            with patch(
                'patrol_amr.docking_runner.time.monotonic',
                clock.monotonic,
            ):
                result = DockingRunner(navigator)._confirm_docked(
                    threading.Event(), deadline=5.0, stable_s=3.0)
        self.assertIs(result, NavigationResult.SUCCEEDED)

    def test_sensor_break_resets_stable_window(self):
        """A false sample prevents accumulated non-continuous confirmation."""
        clock = FakeClock()
        navigator = type('Navigator', (), {'is_docked': False})()
        samples = iter([True, True, False, True, True])
        rclpy = ModuleType('rclpy')

        def spin_once(node, timeout_sec):
            clock.advance()
            node.is_docked = next(samples, True)

        rclpy.spin_once = spin_once
        with patch.dict(sys.modules, {'rclpy': rclpy}):
            with patch(
                'patrol_amr.docking_runner.time.monotonic',
                clock.monotonic,
            ):
                result = DockingRunner(navigator)._confirm_docked(
                    threading.Event(), deadline=5.0, stable_s=3.0)
        self.assertIs(result, NavigationResult.FAILED)
