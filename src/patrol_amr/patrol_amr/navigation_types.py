"""Shared navigation value objects without ROS imports."""

from dataclasses import dataclass
from enum import Enum


MAX_GOAL_RETRIES = 3


class NavigationResult(Enum):
    """Normalized result returned by all motion adapters."""

    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'
    CANCELED = 'CANCELED'
    REJECTED = 'REJECTED'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True)
class Waypoint:
    """Named map waypoint measured in metres and degrees."""

    name: str
    x: float
    y: float
    yaw_deg: float
