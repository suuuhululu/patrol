"""RESUME_PATROL policy isolated while TBD-AMR-005 remains open."""

import threading

from patrol_amr.navigation_types import NavigationResult


def resume_patrol(
    patrol,
    store,
    patrol_id: str,
    resume_policy: str,
    cancel_event: threading.Event,
) -> tuple[NavigationResult | None, str]:
    """Resume only when an explicit configured policy and checkpoint exist."""
    if resume_policy == 'disabled':
        return None, 'TBD_AMR_005_RESUME_POLICY_OPEN'
    checkpoint = store.load_checkpoint(patrol_id)
    if checkpoint is None:
        return None, 'NO_PATROL_CHECKPOINT'
    start_index = (checkpoint if resume_policy == 'next_waypoint'
                   else max(0, checkpoint - 1))
    return patrol.run(patrol_id, start_index, cancel_event), 'PATROL_NAVIGATION'
