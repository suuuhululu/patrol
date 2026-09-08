"""Numbered waypoint patrol scenario."""

from __future__ import annotations

import threading
import time
from typing import Callable, Sequence

from patrol_amr.mission_command_store import CommandStore
from patrol_amr.navigation_types import NavigationResult, Waypoint


class PatrolScenario:
    def __init__(
        self,
        navigation,
        store: CommandStore,
        waypoints: Sequence[Waypoint],
        dwell_s: float,
        state_callback: Callable[[str, int], None],
    ):
        if not waypoints:
            raise ValueError('at least one waypoint is required')
        if dwell_s < 0:
            raise ValueError('waypoint dwell must be non-negative')
        self._navigation = navigation
        self._store = store
        self._waypoints = tuple(waypoints)
        self._dwell_s = dwell_s
        self._state_callback = state_callback

    def run(
        self,
        patrol_id: str,
        start_index: int,
        cancel_event: threading.Event,
    ) -> NavigationResult:
        if start_index < 0 or start_index > len(self._waypoints):
            raise ValueError('checkpoint is outside the waypoint list')
        for index in range(start_index, len(self._waypoints)):
            if cancel_event.is_set():
                return NavigationResult.CANCELED
            self._state_callback('MISSION_PATROLLING', index)
            result = self._navigation.go_to(self._waypoints[index], cancel_event)
            if result is not NavigationResult.SUCCEEDED:
                return result
            self._store.save_checkpoint(patrol_id, index + 1)
            if self._dwell(cancel_event) is NavigationResult.CANCELED:
                return NavigationResult.CANCELED
        self._store.clear_checkpoint(patrol_id)
        return NavigationResult.SUCCEEDED

    def _dwell(self, cancel_event: threading.Event) -> NavigationResult:
        deadline = time.monotonic() + self._dwell_s
        while time.monotonic() < deadline:
            if cancel_event.wait(timeout=min(0.1, deadline - time.monotonic())):
                return NavigationResult.CANCELED
        return NavigationResult.SUCCEEDED
