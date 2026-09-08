"""Compose Nav2 pose navigation and TurtleBot docking behind one gateway."""

from __future__ import annotations

import threading

from patrol_amr.docking_runner import DockingRunner
from patrol_amr.nav2_goal_runner import Nav2GoalRunner
from patrol_amr.navigation_types import NavigationResult, Waypoint


class NavigationAdapter:
    """Own one navigator instance on the mission worker thread."""

    def __init__(self, namespace: str, motion_ready=lambda: True) -> None:
        from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator

        self._navigator = TurtleBot4Navigator(namespace=namespace)
        self._nav2 = Nav2GoalRunner(self._navigator, motion_ready)
        self._docking = DockingRunner(self._navigator)

    def wait_until_active(self) -> None:
        self._navigator.waitUntilNav2Active()

    def go_to(
        self,
        waypoint: Waypoint,
        cancel_event: threading.Event,
    ) -> NavigationResult:
        return self._nav2.go_to(waypoint, cancel_event)

    def cancel(self) -> None:
        self._nav2.cancel()

    def ensure_undocked(
        self,
        cancel_event: threading.Event,
    ) -> NavigationResult:
        return self._docking.ensure_undocked(cancel_event)

    def dock(
        self,
        cancel_event: threading.Event,
        timeout_s: float,
        stable_s: float,
    ) -> NavigationResult:
        return self._docking.dock(cancel_event, timeout_s, stable_s)

    def destroy(self) -> None:
        self._navigator.destroy_node()


__all__ = ['NavigationAdapter', 'NavigationResult', 'Waypoint']
