"""Control heartbeat freshness guard for AMR-20.

The wire message type is still TBD-IF-004, so this module has no ROS import.
It implements only the fixed payload semantics and Q-16 application timeout:
control session, increasing uint64 sequence, and more than one second without
an accepted heartbeat means local safety must stop.
"""

from enum import Enum
import math


UINT64_MAX = 0xFFFFFFFFFFFFFFFF
HEARTBEAT_TIMEOUT_SECONDS = 1.0


class HeartbeatVerdict(Enum):
    ACCEPTED = 'accepted'
    STALE_CONTROL_SESSION = 'stale_control_session'
    STALE_SEQUENCE = 'stale_sequence'


class HeartbeatState(Enum):
    MISSING = 'missing'
    HEALTHY = 'healthy'
    EXPIRED = 'expired'


class HeartbeatGuard:
    """Track accepted heartbeats using the AMR local monotonic clock."""

    def __init__(self):
        self._control_session_id = None
        self._retired_control_sessions = set()
        self._last_sequence = None
        self._last_received_at = None
        self._clock = None

    @property
    def control_session_id(self):
        return self._control_session_id

    @property
    def last_sequence(self):
        return self._last_sequence

    def observe(
        self,
        control_session_id: str,
        sequence: int,
        now: float,
    ) -> HeartbeatVerdict:
        _validate_session(control_session_id)
        _validate_sequence(sequence)
        self._advance_clock(now)

        if control_session_id in self._retired_control_sessions:
            return HeartbeatVerdict.STALE_CONTROL_SESSION

        if control_session_id != self._control_session_id:
            if self._control_session_id is not None:
                self._retired_control_sessions.add(
                    self._control_session_id
                )
            self._control_session_id = control_session_id
            self._last_sequence = None
            self._last_received_at = None

        if (
            self._last_sequence is not None
            and sequence <= self._last_sequence
        ):
            return HeartbeatVerdict.STALE_SEQUENCE

        self._last_sequence = sequence
        self._last_received_at = float(now)
        return HeartbeatVerdict.ACCEPTED

    def state(self, now: float) -> HeartbeatState:
        self._advance_clock(now)
        if self._last_received_at is None:
            return HeartbeatState.MISSING
        if now - self._last_received_at > HEARTBEAT_TIMEOUT_SECONDS:
            return HeartbeatState.EXPIRED
        return HeartbeatState.HEALTHY

    def healthy(self, now: float) -> bool:
        return self.state(now) is HeartbeatState.HEALTHY

    def age(self, now: float):
        self._advance_clock(now)
        if self._last_received_at is None:
            return None
        return float(now) - self._last_received_at

    def _advance_clock(self, now) -> None:
        _validate_time(now)
        if self._clock is not None and now < self._clock:
            raise ValueError('now must not move backwards')
        self._clock = float(now)


def _validate_session(value) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError('control_session_id must be a non-empty str')


def _validate_sequence(value) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError('sequence must be an int')
    if not 1 <= value <= UINT64_MAX:
        raise ValueError('sequence must be between 1 and uint64 max')


def _validate_time(value) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('now must be a real number')
    if not math.isfinite(value):
        raise ValueError('now must be finite')
