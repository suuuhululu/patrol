"""Pure state model used to build RobotStatus snapshots in stage 8.

This module deliberately has no ROS dependency.  It keeps the state axes
whose numeric values are already fixed in interfaces.md and separates the
current pose validity from the last valid pose.

14단계 added the odometry axis: measured velocities and the ``motion_stopped``
judgment.  interfaces.md 3절 fixes every number it needs, so nothing here is
guessed.  Note that "stopped" is a statement about odometry, not about the
velocity local_safety_supervisor commanded -- a commanded zero says the gate
closed, not that the wheels have actually come to rest.

Not implemented here:

* Allowed/forbidden transitions between state-axis combinations
  (TBD-AMR-005).
* Scan/waypoint details (remaining TBD-IF-003).
* RobotStatus publication cadence, QoS, session ID, or wire-message mapping;
  those belong to the stage-8 status_reporter ROS node.

Pose timestamps, odometry timestamps and ``snapshot_at`` are caller-supplied
seconds from the same ROS clock.  They are not monotonic lease times and must
not be mixed with the local monotonic clocks used by the safety guards.
"""

from copy import deepcopy
from enum import IntEnum
import math
from typing import Any, NamedTuple, Optional


ROBOT_IDS = ('robot1', 'robot6')
UINT8_MAX = 0xFF
UINT32_MAX = 0xFFFFFFFF
_UNCHANGED = object()

# interfaces.md 3절 "실제 정지" 판정. 네 값 모두 문서에 확정돼 있어 이 파일이
# 정한 것이 아니다: 선속도 절댓값 ≤ 0.05 m/s, 각속도 절댓값 ≤ 0.1 rad/s가
# 0.5초 연속 유지되고 측정 age ≤ 0.5초일 때만 정지로 본다.
STOP_LINEAR_LIMIT = 0.05
STOP_ANGULAR_LIMIT = 0.1
STOP_HOLD_SECONDS = 0.5
ODOMETRY_MAX_AGE_SECONDS = 0.5


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


class SafetyState(IntEnum):
    SAFETY_UNKNOWN = 0
    SAFETY_NORMAL = 1
    SAFETY_STOPPING = 2
    SAFETY_STOPPED = 3
    SAFETY_ESTOPPED = 4
    SAFETY_ERROR = 5


class PoseSample(NamedTuple):
    """One pose observation; value contains the pose and covariance payload."""

    value: Any
    frame_id: str
    measured_at: float


class OdometrySample(NamedTuple):
    """One odometry observation reduced to the two axes RobotStatus carries."""

    linear: float
    angular: float
    measured_at: float


class RobotStatusSnapshot(NamedTuple):
    """Immutable view consumed later by status_reporter."""

    robot_id: str
    operational_state: OperationalState
    mission_state: MissionState
    docking_state: DockingState
    battery_state: BatteryState
    safety_state: Optional[int]
    active_command_id: str
    active_mission_id: str
    pose: Optional[PoseSample]
    pose_valid: bool
    last_valid_pose: Optional[PoseSample]
    last_valid_pose_age: Optional[float]
    linear_velocity: float
    angular_velocity: float
    motion_stopped: bool
    current_waypoint_id: str
    scan_state: str
    reason_code: int
    reason: str
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

        self._safety_state = SafetyState.SAFETY_UNKNOWN

        self._active_command_id = ''
        self._active_mission_id = ''
        self._current_waypoint_id = ''
        self._scan_state = ''
        self._reason_code = 0
        self._reason = ''

        self._pose = None
        self._pose_valid = False
        self._last_valid_pose = None

        self._odometry = None
        # 정지 조건을 만족하기 시작한 관측 시각. 조건이 깨지거나 관측이
        # 끊기면 None 으로 되돌려 연속 유지 창을 다시 연다.
        self._stop_held_since = None

        self._revision = 0

    @property
    def robot_id(self) -> str:
        return self._robot_id

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def pose_valid(self) -> bool:
        """Current localization validity without creating a snapshot."""
        return self._pose_valid

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
            updates['_safety_state'] = self._enum_value(
                SafetyState, safety_state, 'safety_state'
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

    def update_mission_context(
        self,
        *,
        active_command_id=_UNCHANGED,
        active_mission_id=_UNCHANGED,
        current_waypoint_id=_UNCHANGED,
        scan_state=_UNCHANGED,
        reason_code=_UNCHANGED,
        reason=_UNCHANGED,
    ) -> bool:
        """Atomically update mission-owned RobotStatus payload fields.

        Waypoint and scan semantics remain TBD-IF-003, so they are transported
        as opaque strings.  Cross-field state transition rules remain
        TBD-AMR-005 and are not invented here.
        """
        updates = {}
        for name, value in (
            ('active_command_id', active_command_id),
            ('active_mission_id', active_mission_id),
            ('current_waypoint_id', current_waypoint_id),
            ('scan_state', scan_state),
            ('reason', reason),
        ):
            if value is not _UNCHANGED:
                if not isinstance(value, str):
                    raise ValueError(f'{name} must be a str')
                updates[f'_{name}'] = value
        if reason_code is not _UNCHANGED:
            updates['_reason_code'] = self._uint32(
                reason_code, 'reason_code'
            )

        changed = any(
            getattr(self, name) != value for name, value in updates.items()
        )
        if changed:
            for name, value in updates.items():
                setattr(self, name, value)
            self._revision += 1
        return changed

    def observe_odometry(self, linear, angular, measured_at) -> bool:
        """Record one odometry observation; True if it changed the model.

        Only the two axes RobotStatus reports are kept. This does not decide
        ``motion_stopped`` on its own -- the freshness half of interfaces.md
        3절 depends on when the snapshot is taken, so the judgment is
        completed in snapshot().
        """
        for name, value in (
            ('linear', linear),
            ('angular', angular),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f'odometry {name} must be a real number')
            if not math.isfinite(value):
                raise ValueError(f'odometry {name} must be finite')
        self._finite_time(measured_at, 'measured_at')

        sample = OdometrySample(
            float(linear), float(angular), float(measured_at)
        )
        previous = self._odometry
        if previous is not None and sample.measured_at < previous.measured_at:
            raise ValueError('odometry measured_at must not go backwards')

        within_limits = (
            abs(sample.linear) <= STOP_LINEAR_LIMIT
            and abs(sample.angular) <= STOP_ANGULAR_LIMIT
        )
        if not within_limits:
            self._stop_held_since = None
        else:
            # 관측이 끊긴 구간은 "연속 유지"로 주장할 수 없다. 표본 간격이
            # 신선도 한도를 넘으면 창을 다시 연다. 정지 선언이 어려워지는
            # 방향이므로 관제가 근거 없이 새 token 을 발급하지 않는다.
            gap_too_large = (
                previous is None
                or sample.measured_at - previous.measured_at
                > ODOMETRY_MAX_AGE_SECONDS
            )
            if self._stop_held_since is None or gap_too_large:
                self._stop_held_since = sample.measured_at

        self._odometry = sample
        if sample == previous:
            return False
        self._revision += 1
        return True

    def _odometry_view(self, snapshot_at: float):
        """Return (linear, angular, motion_stopped) for one snapshot time.

        Unreceived or stale odometry reports NaN rather than zero, matching
        how battery SOC is handled: a missing measurement must not be read
        as "measured, and it was zero".
        """
        sample = self._odometry
        if sample is None:
            return float('nan'), float('nan'), False
        age = float(snapshot_at) - sample.measured_at
        if age > ODOMETRY_MAX_AGE_SECONDS:
            return float('nan'), float('nan'), False

        stopped = (
            self._stop_held_since is not None
            and abs(sample.linear) <= STOP_LINEAR_LIMIT
            and abs(sample.angular) <= STOP_ANGULAR_LIMIT
            and sample.measured_at - self._stop_held_since
            >= STOP_HOLD_SECONDS
        )
        return sample.linear, sample.angular, stopped

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

        linear_velocity, angular_velocity, motion_stopped = (
            self._odometry_view(snapshot_at)
        )

        return RobotStatusSnapshot(
            robot_id=self._robot_id,
            operational_state=self._operational_state,
            mission_state=self._mission_state,
            docking_state=self._docking_state,
            battery_state=self._battery_state,
            safety_state=self._safety_state,
            active_command_id=self._active_command_id,
            active_mission_id=self._active_mission_id,
            pose=deepcopy(self._pose),
            pose_valid=self._pose_valid,
            last_valid_pose=deepcopy(self._last_valid_pose),
            last_valid_pose_age=last_valid_age,
            linear_velocity=linear_velocity,
            angular_velocity=angular_velocity,
            motion_stopped=motion_stopped,
            current_waypoint_id=self._current_waypoint_id,
            scan_state=self._scan_state,
            reason_code=self._reason_code,
            reason=self._reason,
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
    def _uint32(value, name):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f'{name} must be an int')
        if not 0 <= value <= UINT32_MAX:
            raise ValueError(f'{name} must fit in uint32')
        return value

    @staticmethod
    def _finite_time(value, name):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'{name} must be a real number')
        if not math.isfinite(value):
            raise ValueError(f'{name} must be finite')
