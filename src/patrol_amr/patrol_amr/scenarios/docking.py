"""Docking scenario using Q-09's timeout and stable sensor condition."""

import threading

from patrol_amr.navigation_types import NavigationResult


def dock(
    navigation,
    cancel_event: threading.Event,
    timeout_s: float = 60.0,
    sensor_stable_s: float = 2.0,
) -> NavigationResult:
    return navigation.dock(cancel_event, timeout_s, sensor_stable_s)
