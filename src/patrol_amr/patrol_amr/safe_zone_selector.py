"""Select a safe-zone candidate using the fixed Q-08 constraints.

This module does not load a map or invent candidate coordinates.  A future
map/traffic provider supplies measured candidates; this module validates every
Q-08 gate and applies the documented ranking deterministically.
"""

from dataclasses import dataclass
from enum import Enum
import math
from typing import Iterable, Optional, Tuple


MIN_OBSTACLE_CLEARANCE_M = 0.5
MIN_VEHICLE_PATH_CLEARANCE_M = 1.0
SAFE_ZONE_NOT_FOUND = 400


class RejectionReason(Enum):
    NOT_MAP_FRAME = 'not_map_frame'
    NOT_FREE_CELL = 'not_free_cell'
    INSIDE_KEEPOUT = 'inside_keepout'
    OBSTACLE_CLEARANCE = 'obstacle_clearance'
    VEHICLE_PATH_CLEARANCE = 'vehicle_path_clearance'
    PATH_UNAVAILABLE = 'path_unavailable'
    OTHER_AMR_OVERLAP = 'other_amr_overlap'


@dataclass(frozen=True)
class MapPose:
    x: float
    y: float
    yaw: float
    frame_id: str = 'map'

    def __post_init__(self):
        for name in ('x', 'y', 'yaw'):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f'{name} must be finite')
            object.__setattr__(self, name, float(value))
        if not isinstance(self.frame_id, str) or not self.frame_id:
            raise ValueError('frame_id must be a non-empty str')


@dataclass(frozen=True)
class SafeZoneCandidate:
    candidate_id: str
    pose: MapPose
    free_cell: bool
    inside_keepout: bool
    obstacle_clearance_m: float
    vehicle_path_clearance_m: float
    path_available: bool
    overlaps_other_amr: bool
    path_cost: float

    def __post_init__(self):
        if not isinstance(self.candidate_id, str) or not self.candidate_id:
            raise ValueError('candidate_id must be a non-empty str')
        if not isinstance(self.pose, MapPose):
            raise ValueError('pose must be a MapPose')
        for name in (
            'free_cell', 'inside_keepout', 'path_available',
            'overlaps_other_amr',
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f'{name} must be bool')
        for name in (
            'obstacle_clearance_m', 'vehicle_path_clearance_m', 'path_cost'
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0.0
            ):
                raise ValueError(f'{name} must be finite and non-negative')
            object.__setattr__(self, name, float(value))


@dataclass(frozen=True)
class SafeZoneDecision:
    selected: Optional[SafeZoneCandidate]
    reason_code: int
    reason: str
    eligible_ids: Tuple[str, ...]


def rejection_reasons(candidate: SafeZoneCandidate) -> Tuple[RejectionReason, ...]:
    if not isinstance(candidate, SafeZoneCandidate):
        raise ValueError('candidate must be a SafeZoneCandidate')
    reasons = []
    if candidate.pose.frame_id != 'map':
        reasons.append(RejectionReason.NOT_MAP_FRAME)
    if not candidate.free_cell:
        reasons.append(RejectionReason.NOT_FREE_CELL)
    if candidate.inside_keepout:
        reasons.append(RejectionReason.INSIDE_KEEPOUT)
    if candidate.obstacle_clearance_m < MIN_OBSTACLE_CLEARANCE_M:
        reasons.append(RejectionReason.OBSTACLE_CLEARANCE)
    if candidate.vehicle_path_clearance_m < MIN_VEHICLE_PATH_CLEARANCE_M:
        reasons.append(RejectionReason.VEHICLE_PATH_CLEARANCE)
    if not candidate.path_available:
        reasons.append(RejectionReason.PATH_UNAVAILABLE)
    if candidate.overlaps_other_amr:
        reasons.append(RejectionReason.OTHER_AMR_OVERLAP)
    return tuple(reasons)


def select_safe_zone(candidates: Iterable[SafeZoneCandidate]) -> SafeZoneDecision:
    if isinstance(candidates, (str, bytes)):
        raise ValueError('candidates must be an iterable of candidates')
    try:
        candidates = tuple(candidates)
    except TypeError as error:
        raise ValueError('candidates must be iterable') from error

    identifiers = []
    eligible = []
    for candidate in candidates:
        if not isinstance(candidate, SafeZoneCandidate):
            raise ValueError('every candidate must be a SafeZoneCandidate')
        if candidate.candidate_id in identifiers:
            raise ValueError('candidate IDs must be unique')
        identifiers.append(candidate.candidate_id)
        if not rejection_reasons(candidate):
            eligible.append(candidate)

    eligible.sort(
        key=lambda item: (
            -item.vehicle_path_clearance_m,
            item.path_cost,
            item.candidate_id,
        )
    )
    if not eligible:
        return SafeZoneDecision(
            selected=None,
            reason_code=SAFE_ZONE_NOT_FOUND,
            reason='SAFE_ZONE_NOT_FOUND',
            eligible_ids=(),
        )
    return SafeZoneDecision(
        selected=eligible[0],
        reason_code=0,
        reason='',
        eligible_ids=tuple(item.candidate_id for item in eligible),
    )
