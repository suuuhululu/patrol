"""Load and validate measured patrol waypoints in map coordinates."""

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Tuple

import yaml


@dataclass(frozen=True)
class Waypoint:
    waypoint_id: str
    x: float
    y: float
    yaw_deg: float
    direction_approx: str


@dataclass(frozen=True)
class WaypointCatalog:
    map_id: str
    frame_id: str
    waypoints: Tuple[Waypoint, ...]

    def by_id(self, waypoint_id: str) -> Waypoint:
        if not isinstance(waypoint_id, str) or not waypoint_id:
            raise ValueError('waypoint_id must be a non-empty str')
        for waypoint in self.waypoints:
            if waypoint.waypoint_id == waypoint_id:
                return waypoint
        raise KeyError(waypoint_id)


def load_waypoint_catalog(path) -> WaypointCatalog:
    path = Path(path)
    try:
        payload = yaml.safe_load(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError('waypoint catalog could not be read') from error
    if not isinstance(payload, dict):
        raise ValueError('waypoint catalog root must be a mapping')
    map_id = _nonempty(payload.get('map_id'), 'map_id')
    frame_id = _nonempty(payload.get('frame_id'), 'frame_id')
    if frame_id != 'map':
        raise ValueError('waypoint frame_id must be map')
    raw_waypoints = payload.get('waypoints')
    if not isinstance(raw_waypoints, list) or not raw_waypoints:
        raise ValueError('waypoints must be a non-empty list')

    waypoints = []
    identifiers = set()
    for raw in raw_waypoints:
        if not isinstance(raw, dict):
            raise ValueError('every waypoint must be a mapping')
        waypoint_id = _nonempty(raw.get('id'), 'waypoint id')
        if waypoint_id in identifiers:
            raise ValueError('waypoint IDs must be unique')
        identifiers.add(waypoint_id)
        yaw_deg = _finite(raw.get('yaw_deg'), 'yaw_deg')
        if not 0.0 <= yaw_deg < 360.0:
            raise ValueError('yaw_deg must be in [0, 360)')
        waypoints.append(
            Waypoint(
                waypoint_id=waypoint_id,
                x=_finite(raw.get('x'), 'x'),
                y=_finite(raw.get('y'), 'y'),
                yaw_deg=yaw_deg,
                direction_approx=_nonempty(
                    raw.get('direction_approx'), 'direction_approx'
                ),
            )
        )
    return WaypointCatalog(map_id, frame_id, tuple(waypoints))


def _nonempty(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError(f'{name} must be a non-empty str')
    return value


def _finite(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f'{name} must be finite')
    return float(value)
