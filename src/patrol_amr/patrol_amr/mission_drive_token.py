"""Thread-safe mission adapter for the shared DriveToken safety model.

``local_safety_supervisor`` owns the final velocity gate.  The mission node
tracks the same token contract only so it can reject a new mission and cancel
an active Nav2 goal when authority disappears.  The validated ordering and
lease rules stay in :mod:`patrol_amr.drive_token_guard`; this adapter adds the
lock and snapshot shape needed by the mission worker thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time

from patrol_amr import drive_token_guard as safety_token


class DriveTokenDecision(Enum):
    """Mission-facing result of one DriveToken observation."""

    GRANTED = 'granted'
    REFRESHED = 'refreshed'
    REVOKED = 'revoked'
    HOLDER_CHANGED = 'holder_changed'
    IGNORED_STALE = 'ignored_stale'
    INVALID = 'invalid'


@dataclass(frozen=True)
class DriveTokenSnapshot:
    """Immutable authority view shared with mission admission and logging."""

    control_session_id: str
    token_id: str
    message_sequence: int
    valid: bool
    remaining_s: float
    blocking_reason: str


class MissionDriveTokenGuard:
    """Reuse the local-safety token contract across ROS and worker threads."""

    def __init__(self, robot_id: str, monotonic=time.monotonic) -> None:
        self._guard = safety_token.DriveTokenGuard(robot_id)
        self._monotonic = monotonic
        self._lock = threading.Lock()

    def update_message(self, message) -> DriveTokenDecision:
        """Validate one generated ``patrol_interfaces/DriveToken`` message."""
        with self._lock:
            previous_session = self._guard.control_session_id
            previous_token = self._guard.token_id
            try:
                lease_seconds = safety_token.duration_to_seconds(
                    int(message.lease_duration.sec),
                    int(message.lease_duration.nanosec),
                )
                verdict = self._guard.observe(
                    str(message.control_session_id),
                    str(message.token_id),
                    str(message.holder_robot_id),
                    lease_seconds,
                    int(message.message_sequence),
                    self._monotonic(),
                )
            except (TypeError, ValueError):
                return DriveTokenDecision.INVALID

            if verdict is safety_token.TokenVerdict.ACCEPTED:
                if (
                    previous_session == self._guard.control_session_id
                    and previous_token == self._guard.token_id
                ):
                    return DriveTokenDecision.REFRESHED
                return DriveTokenDecision.GRANTED
            if verdict is safety_token.TokenVerdict.REVOKED:
                return DriveTokenDecision.REVOKED
            if verdict is safety_token.TokenVerdict.HOLDER_CHANGED:
                return DriveTokenDecision.HOLDER_CHANGED
            if verdict in {
                safety_token.TokenVerdict.OTHER_HOLDER,
                safety_token.TokenVerdict.STALE_CONTROL_SESSION,
                safety_token.TokenVerdict.STALE_MESSAGE_SEQUENCE,
            }:
                return DriveTokenDecision.IGNORED_STALE
            return DriveTokenDecision.INVALID

    def snapshot(self) -> DriveTokenSnapshot:
        """Return the current token state using the local monotonic clock."""
        with self._lock:
            now = self._monotonic()
            authority = self._guard.authority(now)
            valid = authority is safety_token.DriveAuthority.GRANTED
            if authority is safety_token.DriveAuthority.EXPIRED:
                reason = 'DRIVE_TOKEN_EXPIRED'
            elif valid:
                reason = ''
            elif self._guard.revoked_last:
                reason = 'DRIVE_TOKEN_REVOKED'
            else:
                reason = 'DRIVE_TOKEN_MISSING'
            return DriveTokenSnapshot(
                control_session_id=self._guard.control_session_id or '',
                token_id=self._guard.token_id or '',
                message_sequence=self._guard.last_message_sequence or 0,
                valid=valid,
                remaining_s=self._guard.remaining_lease(now),
                blocking_reason=reason,
            )

    def valid(self) -> bool:
        """Return whether this robot currently owns a live drive lease."""
        return self.snapshot().valid
