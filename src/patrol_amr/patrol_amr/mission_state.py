"""Thread-safe internal mission state for the teammate-owned status reporter."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time


@dataclass(frozen=True)
class MissionStateSnapshot:
    """Current internal mission state; this is not a public ROS contract."""

    mission: str = 'MISSION_NONE'
    waypoint_index: int = -1
    last_waypoint_index: int = -1
    command_id: str = ''
    mission_id: str = ''
    outcome: str = ''
    reason_code: int = 0
    reason: str = ''
    updated_monotonic_s: float = 0.0
    revision: int = 0


class MissionStateTracker:
    """Own mission progress until TBD-IF-003 defines RobotStatus fields."""

    def __init__(self, *, starting_revision: int = 0) -> None:
        if (
            isinstance(starting_revision, bool)
            or not isinstance(starting_revision, int)
            or starting_revision < 0
        ):
            raise ValueError('starting_revision must be a non-negative int')
        self._lock = threading.Lock()
        self._snapshot = MissionStateSnapshot(
            updated_monotonic_s=time.monotonic(),
            revision=starting_revision,
        )

    def command_started(self, command_id: str, mission_id: str) -> None:
        with self._lock:
            self._replace(
                mission='MISSION_NONE',
                waypoint_index=-1,
                last_waypoint_index=-1,
                command_id=command_id,
                mission_id=mission_id,
                outcome='',
                reason_code=0,
                reason='',
            )

    def transition(self, mission: str, waypoint_index: int = -1) -> None:
        with self._lock:
            changes = {'mission': mission, 'waypoint_index': waypoint_index}
            if waypoint_index >= 0:
                changes['last_waypoint_index'] = waypoint_index
            self._replace(**changes)

    def pause(self) -> None:
        """Preserve mission identity and progress while reporting STOP."""
        with self._lock:
            self._replace(
                mission='MISSION_PAUSED',
                waypoint_index=-1,
                outcome='PAUSED',
                reason_code=0,
                reason='',
            )

    def command_finished(
        self,
        outcome: str,
        reason: str = '',
        reason_code: int = 0,
    ) -> None:
        with self._lock:
            terminal = {
                'SUCCEEDED': 'MISSION_COMPLETED',
                'FAILED': 'MISSION_FAILED',
                'CANCELED': 'MISSION_CANCELED',
            }.get(outcome, self._snapshot.mission)
            self._replace(
                mission=terminal,
                waypoint_index=-1,
                command_id='',
                mission_id='',
                outcome=outcome,
                reason_code=reason_code,
                reason=reason,
            )

    def snapshot(self) -> MissionStateSnapshot:
        with self._lock:
            return self._snapshot

    def _replace(self, **changes) -> None:
        values = self._snapshot.__dict__.copy()
        values.update(changes)
        values['updated_monotonic_s'] = time.monotonic()
        values['revision'] = self._snapshot.revision + 1
        self._snapshot = MissionStateSnapshot(**values)
