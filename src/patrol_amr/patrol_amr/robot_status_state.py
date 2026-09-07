"""Pure state model used to build RobotStatus snapshots in stage 8.

This module deliberately has no ROS dependency.  It keeps the state axes
whose numeric values are already fixed in interfaces.md and separates the
current pose validity from the last valid pose.

Not implemented here:

* Allowed/forbidden transitions between state-axis combinations
  (TBD-AMR-005).
* A SafetyState enum or scan/waypoint details (remaining TBD-IF-003).
* RobotStatus publication cadence, QoS, session ID, or wire-message mapping;
  those belong to the stage-8 status_reporter ROS node.

Pose timestamps and ``snapshot_at`` are caller-supplied seconds from the
same ROS clock.  They are not monotonic lease times and must not be mixed
with the local monotonic clocks used by the safety guards.
"""

from copy import deepcopy
from enum import IntEnum
import math
from typing import Any, NamedTuple, Optional


ROBOT_IDS = ('robot1', 'robot6')
UINT8_MAX = 0xFF
_UNCHANGED = object()


class OperationalState(IntEnum):
    OP_UNKNOWN = 0
    OP_INITIALIZING = 1
    OP_READY = 2
    OP_MOVING = 3
    OP_STOPPED_SAFETY = 4
    OP_CHARGING = 5
    OP_ERROR = 6


class MissionState(IntEnum):
    MISSION_NONE = 0
    MISSION_UNDOCKING = 1
    MISSION_PATROLLING = 2
    MISSION_MOVING_TO_SAFE_ZONE = 3
    MISSION_WAITING_SAFE_ZONE = 4
    MISSION_RETURNING_TO_DOCK = 5
    MISSION_DOCKING = 6
    MISSION_PAUSED = 7
    MISSION_COMPLETED = 8
    MISSION_FAILED = 9
    MISSION_CANCELED = 10


class DockingState(IntEnum):
    DOCK_UNKNOWN = 0
    DOCK_UNDOCKED = 1
    DOCK_UNDOCKING = 2
    DOCK_DOCKING = 3
    DOCK_DOCKED = 4
    DOCK_FAILED = 5


class BatteryState(IntEnum):
    UNKNOWN = 0
    CRITICAL = 1
    LOW = 2
    NORMAL = 3
    CHARGING = 4
    PATROL_READY = 5
    FULL = 6


class PoseSample(NamedTuple):
    """One pose observation; value contains the pose and covariance payload."""

    value: Any
    frame_id: str
    measured_at: float


class RobotStatusSnapshot(NamedTuple):
    """Immutable view consumed later by status_reporter."""

    robot_id: str
    operational_state: OperationalState
    mission_state: MissionState
    docking_state: DockingState
    battery_state: BatteryState
    safety_state: Optional[int]
    pose: Optional[PoseSample]
    pose_valid: bool
    last_valid_pose: Optional[PoseSample]
    last_valid_pose_age: Optional[float]
    revision: int


class RobotStatusState:
    """Keep independent RobotStatus axes and current/last-valid pose state.

    ``revision`` is only a local change counter for stage-8 publication
    decisions.  It is not the public ``status_sequence`` field, whose session
    and restart semantics belong to the reporter.
    """

    def __init__(self, robot_id: str):
        if robot_id not in ROBOT_IDS:
            raise ValueError(f'robot_id must be one of {ROBOT_IDS}')
        self._robot_id = robot_id
        self._operational_state = OperationalState.OP_UNKNOWN
        self._mission_state = MissionState.MISSION_NONE
        self._docking_state = DockingState.DOCK_UNKNOWN
        self._battery_state = BatteryState.UNKNOWN

        # The field exists, but its enum numbers are still TBD-IF-003.  None
        # means "not supplied by an agreed mapping"; zero is not guessed here.
        self._safety_state = None

        self._pose = None
        self._pose_valid = False
        self._last_valid_pose = None
        self._revision = 0

    @property
    def robot_id(self) -> str:
        return self._robot_id

    @property
    def revision(self) -> int:
        return self._revision

    def update_states(
        self,
        *,
        operational_state=_UNCHANGED,
        mission_state=_UNCHANGED,
        docking_state=_UNCHANGED,
        battery_state=_UNCHANGED,
        safety_state=_UNCHANGED,
    ) -> bool:
        """Apply supplied axes independently and return whether anything changed.

        No cross-axis transition policy is enforced because the detailed
        transition table is still TBD-AMR-005.  Enum/range checks prevent an
        invalid value from partially changing the model.
        """
        updates = {}
        if operational_state is not _UNCHANGED:
            updates['_operational_state'] = self._enum_value(
                OperationalState, operational_state, 'operational_state'
            )
        if mission_state is not _UNCHANGED:
            updates['_mission_state'] = self._enum_value(
                MissionState, mission_state, 'mission_state'
            )
        if docking_state is not _UNCHANGED:
            updates['_docking_state'] = self._enum_value(
                DockingState, docking_state, 'docking_state'
            )
        if battery_state is not _UNCHANGED:
            updates['_battery_state'] = self._enum_value(
                BatteryState, battery_state, 'battery_state'
            )
        if safety_state is not _UNCHANGED:
            updates['_safety_state'] = self._uint8(
                safety_state, 'safety_state'
            )

        changed = any(
            getattr(self, name) != value for name, value in updates.items()
        )
        if changed:
            for name, value in updates.items():
                setattr(self, name, value)
            self._revision += 1
        return changed

    def observe_pose(
        self,
        value,
        pose_valid: bool,
        measured_at=None,
        frame_id=None,
    ) -> bool:
        """Record a current pose observation while preserving last valid pose.

        A valid pose must carry a payload, ``map`` frame, and finite measurement
        timestamp.  An invalid observation may have no pose at all.  If an
        invalid payload is supplied for diagnostics, it must still identify its
        measurement time and map frame; it never replaces ``last_valid_pose``.
        """
        if not isinstance(pose_valid, bool):
            raise ValueError('pose_valid must be a bool')

        if value is None:
            if pose_valid:
                raise ValueError('a valid pose must have a value')
            if measured_at is not None or frame_id is not None:
                raise ValueError(
                    'an absent pose must not have measured_at or frame_id'
                )
            sample = None
        else:
            if frame_id != 'map':
                raise ValueError("pose frame_id must be 'map'")
            self._finite_time(measured_at, 'measured_at')
            sample = PoseSample(deepcopy(value), frame_id, float(measured_at))

        changed = sample != self._pose or pose_valid != self._pose_valid
        if not changed:
            return False

        self._pose = sample
        self._pose_valid = pose_valid
        if pose_valid:
            self._last_valid_pose = deepcopy(sample)
        self._revision += 1
        return True

    def snapshot(self, snapshot_at: float) -> RobotStatusSnapshot:
        """Return an immutable copy and compute age from the same ROS clock."""
        self._finite_time(snapshot_at, 'snapshot_at')
        if self._last_valid_pose is None:
            last_valid_age = None
        else:
            last_valid_age = (
                float(snapshot_at) - self._last_valid_pose.measured_at
            )
            if last_valid_age < 0.0:
                raise ValueError(
                    'snapshot_at must not precede the last valid pose timestamp'
                )

        return RobotStatusSnapshot(
            robot_id=self._robot_id,
            operational_state=self._operational_state,
            mission_state=self._mission_state,
            docking_state=self._docking_state,
            battery_state=self._battery_state,
            safety_state=self._safety_state,
            pose=deepcopy(self._pose),
            pose_valid=self._pose_valid,
            last_valid_pose=deepcopy(self._last_valid_pose),
            last_valid_pose_age=last_valid_age,
            revision=self._revision,
        )

    @staticmethod
    def _enum_value(enum_type, value, name):
        if isinstance(value, bool):
            raise ValueError(f'{name} must be a valid {enum_type.__name__}')
        try:
            return enum_type(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f'{name} must be a valid {enum_type.__name__}'
            ) from error

    @staticmethod
    def _uint8(value, name):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f'{name} must be an int')
        if not 0 <= value <= UINT8_MAX:
            raise ValueError(f'{name} must fit in uint8')
        return value

    @staticmethod
    def _finite_time(value, name):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'{name} must be a real number')
        if not math.isfinite(value):
            raise ValueError(f'{name} must be finite')
