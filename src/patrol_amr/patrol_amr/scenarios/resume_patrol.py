"""RESUME_PATROL from the next not-yet-completed waypoint."""

import threading

from patrol_amr.navigation_types import NavigationResult


def resume_patrol(
    patrol,
    store,
    patrol_id: str,
    resume_policy: str,
    cancel_event: threading.Event,
) -> tuple[NavigationResult | None, str]:
    """Resume only when the fixed policy and a checkpoint exist."""
    if resume_policy != 'next_waypoint':
        raise ValueError('resume_policy must be next_waypoint')
    checkpoint = store.load_checkpoint(patrol_id)
    if checkpoint is None:
        return None, 'NO_PATROL_CHECKPOINT'
    return patrol.run(
        patrol_id, checkpoint, cancel_event), 'PATROL_NAVIGATION'
