"""Run one Nav2 pose goal and normalize its terminal result."""

from __future__ import annotations

import threading
import time

from patrol_amr.navigation_types import NavigationResult, Waypoint


class Nav2GoalRunner:
    """Single-threaded owner of pose goals for a TurtleBot4Navigator."""

    def __init__(self, navigator, motion_ready=lambda: True) -> None:
        self._navigator = navigator
        self._motion_ready = motion_ready
        self._task_active = False

    def go_to(
        self,
        waypoint: Waypoint,
        cancel_event: threading.Event,
    ) -> NavigationResult:
        if cancel_event.is_set():
            return NavigationResult.CANCELED
        if not self._motion_ready():
            return NavigationResult.REJECTED
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
            return NavigationResult.FAILED
        return {
            TaskResult.SUCCEEDED: NavigationResult.SUCCEEDED,
            TaskResult.FAILED: NavigationResult.FAILED,
            TaskResult.CANCELED: NavigationResult.CANCELED,
        }.get(result, NavigationResult.UNKNOWN)

    def cancel(self) -> None:
        if self._task_active:
            self._navigator.cancelTask()
