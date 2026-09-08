"""Execute an explicit safe-zone pose selected by control."""

import threading

from patrol_amr.mission_types import PoseTarget
from patrol_amr.navigation_types import NavigationResult, Waypoint


def move_to_safe_zone(
    navigation,
    target_id: str,
    target: PoseTarget,
    cancel_event: threading.Event,
) -> NavigationResult:
    if target.frame_id != 'map':
        return NavigationResult.REJECTED
    return navigation.go_to(
        Waypoint(target_id or 'safe_zone', target.x, target.y, target.yaw_deg),
        cancel_event,
    )
