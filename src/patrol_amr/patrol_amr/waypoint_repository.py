"""Build and validate the shared W1-W7 map-frame waypoint set."""

from __future__ import annotations

import math
from typing import Iterable

from patrol_amr.navigation_types import Waypoint


WAYPOINT_COUNT = 7
VALUES_PER_WAYPOINT = 3


def load_waypoints(values: Iterable[float]) -> tuple[Waypoint, ...]:
    """Convert seven x/y/yaw triples into immutable named waypoints."""
    try:
        flat = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError('waypoint coordinates must be numeric') from exc
    expected = WAYPOINT_COUNT * VALUES_PER_WAYPOINT
    if len(flat) != expected:
        raise ValueError(
            'waypoints_xyyaw must contain exactly 7 x/y/yaw triples')
    if not all(math.isfinite(value) for value in flat):
        raise ValueError('waypoint coordinates must be finite')
    return tuple(
        Waypoint(f'W{index + 1}', *flat[index * 3:index * 3 + 3])
        for index in range(WAYPOINT_COUNT)
    )
