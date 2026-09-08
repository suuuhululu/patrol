"""START_PATROL lifecycle: clear checkpoint, undock, then patrol."""

import threading

from patrol_amr.navigation_types import NavigationResult


def start_patrol(
    patrol,
    navigation,
    store,
    patrol_id: str,
    cancel_event: threading.Event,
    state_callback,
    dock_timeout_s: float,
    dock_sensor_stable_s: float,
) -> tuple[NavigationResult, str]:
    """Undock, visit W1-W7, then finish by docking."""
    store.clear_checkpoint(patrol_id)
    state_callback('MISSION_UNDOCKING', -1)
    undock = navigation.ensure_undocked(cancel_event)
    if undock is not NavigationResult.SUCCEEDED:
        return undock, 'UNDOCK_NOT_CONFIRMED'
    patrol_result = patrol.run(patrol_id, 0, cancel_event)
    if patrol_result is not NavigationResult.SUCCEEDED:
        return patrol_result, 'PATROL_NAVIGATION'
    state_callback('MISSION_DOCKING', -1)
    dock_result = navigation.dock(
        cancel_event, dock_timeout_s, dock_sensor_stable_s)
    return dock_result, 'PATROL_DOCKING'
