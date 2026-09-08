"""Shared navigation value objects without ROS imports."""

from dataclasses import dataclass
from enum import Enum


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
