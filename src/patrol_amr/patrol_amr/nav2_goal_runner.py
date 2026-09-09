"""Run one Nav2 pose goal and normalize its terminal result."""

from __future__ import annotations

import threading
import time

from patrol_amr.navigation_types import (
    MAX_GOAL_RETRIES,
    NavigationResult,
    Waypoint,
)


class Nav2GoalRunner:
    """Single-threaded owner of pose goals for a TurtleBot4Navigator."""

    def __init__(self, navigator, motion_ready=lambda: True) -> None:
        self._navigator = navigator
        self._motion_ready = motion_ready
        self._task_active = False
        self._last_feedback = None

    @property
    def last_feedback(self):
        """Most recent BasicNavigator feedback observed for the active goal."""
        return self._last_feedback

    def go_to(
        self,
        waypoint: Waypoint,
        cancel_event: threading.Event,
    ) -> NavigationResult:
        """Run one goal, retrying ordinary Nav2 failure at most three times."""
        total_attempts = MAX_GOAL_RETRIES + 1
        for attempt in range(1, total_attempts + 1):
            result = self._go_to_once(waypoint, cancel_event)
            if result in {
                NavigationResult.SUCCEEDED,
                NavigationResult.CANCELED,
            }:
                return result
            if cancel_event.is_set() or not self._motion_ready():
                return NavigationResult.CANCELED
            if attempt == total_attempts:
                self._warn(
                    f'{waypoint.name} failed after {total_attempts} attempts: '
                    f'{result.value}')
                return result
            self._warn(
                f'{waypoint.name} attempt {attempt}/{total_attempts} failed: '
                f'{result.value}; retrying')
        return NavigationResult.UNKNOWN  # pragma: no cover - exhaustive loop

    def _go_to_once(
        self,
        waypoint: Waypoint,
        cancel_event: threading.Event,
    ) -> NavigationResult:
        if cancel_event.is_set():
            return NavigationResult.CANCELED
        if not self._motion_ready():
            return NavigationResult.CANCELED
        self._last_feedback = None
        pose = self._navigator.getPoseStamped(
            [waypoint.x, waypoint.y], waypoint.yaw_deg)
        # TurtleBot4 BasicNavigator returns False for explicit rejection while
        # compatible test doubles or older implementations may return None.
        # Only the explicit False value is a rejected goal.
        if self._navigator.goToPose(pose) is False:
            return NavigationResult.REJECTED
        self._task_active = True
        cancel_sent = False
        readiness_lost = False
        try:
            while not self._navigator.isTaskComplete():
                feedback_reader = getattr(self._navigator, 'getFeedback', None)
                if callable(feedback_reader):
                    self._last_feedback = feedback_reader()
                if not self._motion_ready():
                    readiness_lost = True
                if (cancel_event.is_set() or readiness_lost) and not cancel_sent:
                    self._navigator.cancelTask()
                    cancel_sent = True
                time.sleep(0.02)
        finally:
            self._task_active = False

        from nav2_simple_commander.robot_navigator import TaskResult

        result = self._navigator.getResult()
        if readiness_lost:
            return NavigationResult.CANCELED
        return {
            TaskResult.SUCCEEDED: NavigationResult.SUCCEEDED,
            TaskResult.FAILED: NavigationResult.FAILED,
            TaskResult.CANCELED: NavigationResult.CANCELED,
        }.get(result, NavigationResult.UNKNOWN)

    def cancel(self) -> None:
        if self._task_active:
            self._navigator.cancelTask()

    def _warn(self, message: str) -> None:
        """Make retry evidence visible when the navigator has a ROS logger."""
        get_logger = getattr(self._navigator, 'get_logger', None)
        if callable(get_logger):
            get_logger().warning(message)
