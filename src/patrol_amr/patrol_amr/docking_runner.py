"""Run Dock/Undock actions and apply the confirmed Q-09 success window."""

from __future__ import annotations

import threading
import time

from patrol_amr.navigation_types import NavigationResult


class DockingRunner:
    """TurtleBot docking actions isolated from waypoint navigation."""

    def __init__(self, navigator) -> None:
        self._navigator = navigator

    def ensure_undocked(
        self,
        cancel_event: threading.Event,
    ) -> NavigationResult:
        if self._navigator.is_docked is False:
            return NavigationResult.SUCCEEDED
        if self._navigator.is_docked is None:
            return NavigationResult.UNKNOWN
        return self._run_action(
            self._navigator.undock_action_client,
            action='undock',
            cancel_event=cancel_event,
            deadline=None,
        )

    def dock(
        self,
        cancel_event: threading.Event,
        timeout_s: float,
        stable_s: float,
    ) -> NavigationResult:
        deadline = time.monotonic() + timeout_s
        result = self._run_action(
            self._navigator.dock_action_client,
            action='dock',
            cancel_event=cancel_event,
            deadline=deadline,
        )
        if result is not NavigationResult.SUCCEEDED:
            return result
        return self._confirm_docked(cancel_event, deadline, stable_s)

    def _confirm_docked(
        self,
        cancel_event: threading.Event,
        deadline: float | None,
        stable_s: float,
    ) -> NavigationResult:
        import rclpy

        stable_since = None
        while time.monotonic() < deadline:
            if cancel_event.is_set():
                return NavigationResult.CANCELED
            rclpy.spin_once(self._navigator, timeout_sec=0.1)
            if self._navigator.is_docked:
                stable_since = stable_since or time.monotonic()
                if time.monotonic() - stable_since >= stable_s:
                    return NavigationResult.SUCCEEDED
            else:
                stable_since = None
        return NavigationResult.FAILED

    def _run_action(
        self,
        client,
        action: str,
        cancel_event: threading.Event,
        deadline: float,
    ) -> NavigationResult:
        import rclpy
        from action_msgs.msg import GoalStatus
        from irobot_create_msgs.action import Dock, Undock

        while not client.wait_for_server(timeout_sec=0.2):
            terminal = self._deadline_result(cancel_event, deadline)
            if terminal is not None:
                return terminal
        goal = Dock.Goal() if action == 'dock' else Undock.Goal()
        send_future = client.send_goal_async(goal)
        while not send_future.done():
            terminal = self._deadline_result(cancel_event, deadline)
            if terminal is not None:
                return terminal
            rclpy.spin_until_future_complete(
                self._navigator, send_future, timeout_sec=0.1)
        handle = send_future.result()
        if handle is None or not handle.accepted:
            return NavigationResult.REJECTED

        result_future = handle.get_result_async()
        cancel_sent = False
        while not result_future.done():
            terminal = self._deadline_result(cancel_event, deadline)
            if terminal is not None and not cancel_sent:
                cancel_future = handle.cancel_goal_async()
                rclpy.spin_until_future_complete(
                    self._navigator, cancel_future, timeout_sec=1.0)
                cancel_sent = True
            if (terminal is not None and deadline is not None
                    and time.monotonic() >= deadline + 1.0):
                return terminal
            rclpy.spin_until_future_complete(
                self._navigator, result_future, timeout_sec=0.1)
        status = result_future.result().status
        if deadline is not None and time.monotonic() >= deadline:
            return (NavigationResult.CANCELED if cancel_event.is_set()
                    else NavigationResult.FAILED)
        return {
            GoalStatus.STATUS_SUCCEEDED: NavigationResult.SUCCEEDED,
            GoalStatus.STATUS_CANCELED: NavigationResult.CANCELED,
            GoalStatus.STATUS_ABORTED: NavigationResult.FAILED,
        }.get(status, NavigationResult.UNKNOWN)

    @staticmethod
    def _deadline_result(cancel_event, deadline):
        if cancel_event.is_set():
            return NavigationResult.CANCELED
        if deadline is not None and time.monotonic() >= deadline:
            return NavigationResult.FAILED
        return None
