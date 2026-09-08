"""Tests for Nav2 result handling independent of ROS."""

import sys
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from patrol_amr.nav2_goal_runner import Nav2GoalRunner
from patrol_amr.navigation_types import NavigationResult, Waypoint


class FakeNavigator:
    """Minimal navigator whose goToPose intentionally returns None."""

    def __init__(self):
        self.sent = False
        self.send_calls = 0

    def getPoseStamped(self, position, yaw):
        """Return a traceable stand-in pose."""
        return position, yaw

    def goToPose(self, pose):
        """Match BasicNavigator's void-style asynchronous start."""
        self.sent = True
        self.send_calls += 1
        return None

    def isTaskComplete(self):
        """Complete immediately after the task was sent."""
        return self.sent

    def getResult(self):
        """Return the fake SUCCEEDED enum value."""
        return 1

    def cancelTask(self):
        """Support the runner cancellation interface."""


class RejectingNavigator(FakeNavigator):
    """Navigator that explicitly rejects a goal before execution."""

    def goToPose(self, pose):
        """Match TurtleBot4Navigator's explicit rejection return."""
        self.send_calls += 1
        return False


class RunningNavigator(FakeNavigator):
    """Navigator kept active until a safety gate cancels it."""

    def __init__(self, gate):
        super().__init__()
        self.gate = gate
        self.polls = 0
        self.canceled = False

    def isTaskComplete(self):
        """Drop readiness after one active poll, then finish on cancel."""
        self.polls += 1
        if self.polls == 1:
            self.gate['ready'] = False
        return self.canceled

    def cancelTask(self):
        """Record the safety-triggered cancellation."""
        self.canceled = True

    def getResult(self):
        """Return canceled after the gate requested a stop."""
        return 3

    def getFeedback(self):
        """Return one traceable feedback object while moving."""
        return {'distance_remaining': 1.0}


class ResultNavigator(FakeNavigator):
    """Return one configured terminal result per goal attempt."""

    def __init__(self, results):
        super().__init__()
        self.results = iter(results)

    def getResult(self):
        return next(self.results)


class LoggedResultNavigator(ResultNavigator):
    """Result navigator exposing the ROS logger surface used in hardware."""

    def __init__(self, results):
        super().__init__(results)
        self.warnings = []

    def get_logger(self):
        return self

    def warning(self, message):
        self.warnings.append(message)


class Nav2GoalRunnerTest(unittest.TestCase):
    """Prevent regressions in BasicNavigator return-value handling."""

    def test_none_from_go_to_pose_is_not_goal_rejection(self):
        """Terminal getResult, rather than goToPose return, decides success."""
        package = ModuleType('nav2_simple_commander')
        module = ModuleType('nav2_simple_commander.robot_navigator')
        module.TaskResult = SimpleNamespace(SUCCEEDED=1, FAILED=2, CANCELED=3)
        modules = {
            'nav2_simple_commander': package,
            'nav2_simple_commander.robot_navigator': module,
        }
        navigator = FakeNavigator()
        with patch.dict(sys.modules, modules):
            result = Nav2GoalRunner(navigator).go_to(
                Waypoint('W1', 1.0, 2.0, 90.0), threading.Event())
        self.assertIs(result, NavigationResult.SUCCEEDED)

    def test_preexisting_cancel_does_not_send_goal(self):
        """Canceled work never reaches Nav2."""
        cancel = threading.Event()
        cancel.set()
        navigator = FakeNavigator()
        result = Nav2GoalRunner(navigator).go_to(
            Waypoint('W1', 1.0, 2.0, 90.0), cancel)
        self.assertIs(result, NavigationResult.CANCELED)
        self.assertFalse(navigator.sent)

    def test_explicit_goal_rejection_is_reported(self):
        """TurtleBot4Navigator's False result maps to REJECTED."""
        navigator = RejectingNavigator()
        result = Nav2GoalRunner(navigator).go_to(
            Waypoint('W1', 1.0, 2.0, 90.0), threading.Event())
        self.assertIs(result, NavigationResult.REJECTED)
        self.assertEqual(4, navigator.send_calls)

    def test_readiness_loss_cancels_an_active_goal(self):
        """A stale live gate stops a goal that was already moving."""
        package = ModuleType('nav2_simple_commander')
        module = ModuleType('nav2_simple_commander.robot_navigator')
        module.TaskResult = SimpleNamespace(SUCCEEDED=1, FAILED=2, CANCELED=3)
        modules = {
            'nav2_simple_commander': package,
            'nav2_simple_commander.robot_navigator': module,
        }
        gate = {'ready': True}
        navigator = RunningNavigator(gate)
        runner = Nav2GoalRunner(navigator, lambda: gate['ready'])
        with patch.dict(sys.modules, modules):
            result = runner.go_to(
                    Waypoint('W1', 1.0, 2.0, 90.0), threading.Event())
        self.assertIs(result, NavigationResult.CANCELED)
        self.assertTrue(navigator.canceled)
        self.assertEqual({'distance_remaining': 1.0}, runner.last_feedback)

    def test_three_failures_are_retried_then_fourth_attempt_succeeds(self):
        package = ModuleType('nav2_simple_commander')
        module = ModuleType('nav2_simple_commander.robot_navigator')
        module.TaskResult = SimpleNamespace(SUCCEEDED=1, FAILED=2, CANCELED=3)
        modules = {
            'nav2_simple_commander': package,
            'nav2_simple_commander.robot_navigator': module,
        }
        navigator = ResultNavigator([2, 2, 2, 1])
        runner = Nav2GoalRunner(navigator)
        with patch.dict(sys.modules, modules):
            result = runner.go_to(
                Waypoint('W1', 1.0, 2.0, 90.0), threading.Event())
        self.assertIs(result, NavigationResult.SUCCEEDED)
        self.assertEqual(4, navigator.send_calls)

    def test_four_failed_attempts_return_failure(self):
        package = ModuleType('nav2_simple_commander')
        module = ModuleType('nav2_simple_commander.robot_navigator')
        module.TaskResult = SimpleNamespace(SUCCEEDED=1, FAILED=2, CANCELED=3)
        modules = {
            'nav2_simple_commander': package,
            'nav2_simple_commander.robot_navigator': module,
        }
        navigator = LoggedResultNavigator([2, 2, 2, 2])
        with patch.dict(sys.modules, modules):
            result = Nav2GoalRunner(navigator).go_to(
                Waypoint('W1', 1.0, 2.0, 90.0), threading.Event())
        self.assertIs(result, NavigationResult.FAILED)
        self.assertEqual(4, navigator.send_calls)
        self.assertEqual(
            navigator.warnings,
            [
                'W1 attempt 1/4 failed: FAILED; retrying',
                'W1 attempt 2/4 failed: FAILED; retrying',
                'W1 attempt 3/4 failed: FAILED; retrying',
                'W1 failed after 4 attempts: FAILED',
            ],
        )
