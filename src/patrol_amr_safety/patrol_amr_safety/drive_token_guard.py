"""DriveToken acceptance and Q-01 local lease for the AMR safety path.

The public names follow interfaces.md section 3:
``control_session_id``, ``token_id``, and ``message_sequence``. This is a
plain Python model; local_safety_supervisor owns the ROS subscription.
"""

from enum import Enum
import math


ROBOT_IDS = ('robot1', 'robot6')
UINT64_MAX = 0xFFFFFFFFFFFFFFFF
NANOSECONDS_PER_SECOND = 1_000_000_000


class TokenVerdict(Enum):
    ACCEPTED = 'accepted'
    REVOKED = 'revoked'
    HOLDER_CHANGED = 'holder_changed'
    OTHER_HOLDER = 'other_holder'
    STALE_CONTROL_SESSION = 'stale_control_session'
    STALE_MESSAGE_SEQUENCE = 'stale_message_sequence'
    INVALID_LEASE = 'invalid_lease'


class DriveAuthority(Enum):
    GRANTED = 'granted'
    MISSING = 'missing'
    EXPIRED = 'expired'


def duration_to_seconds(sec: int, nanosec: int) -> float:
    """Convert a builtin_interfaces/Duration field pair to float seconds."""
    for name, value in (('sec', sec), ('nanosec', nanosec)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f'{name} must be an int')
    return sec + nanosec / NANOSECONDS_PER_SECOND


class DriveTokenGuard:
    """Track one robot's accepted token and caller-clock lease.

    ``message_sequence`` is compared within ``control_session_id``. A new
    control session invalidates the previous token and starts a new sequence
    floor. Changing only ``token_id`` does not reset that floor.
    """

    def __init__(self, robot_id: str):
        if robot_id not in ROBOT_IDS:
            raise ValueError(f'robot_id must be one of {ROBOT_IDS}')
        self._robot_id = robot_id
        self._control_session_id = None
        self._retired_control_sessions = set()
        self._token_id = None
        self._last_message_sequence = None
        self._lease_expires_at = None
        self._revoked_last = False
        self._clock = None

    @property
    def robot_id(self) -> str:
        return self._robot_id

    @property
    def control_session_id(self):
        return self._control_session_id

    @property
    def token_id(self):
        return self._token_id

    @property
    def last_message_sequence(self):
        return self._last_message_sequence

    @property
    def revoked_last(self) -> bool:
        return self._revoked_last

    def observe(
        self,
        control_session_id: str,
        token_id: str,
        holder_robot_id: str,
        lease_seconds: float,
        message_sequence: int,
        now: float,
    ) -> TokenVerdict:
        """Apply one observation and return why it was accepted or discarded."""
        self._validate_observation(
            control_session_id,
            token_id,
            holder_robot_id,
            lease_seconds,
            message_sequence,
            now,
        )
        self._advance_clock(now)

        if control_session_id in self._retired_control_sessions:
            return TokenVerdict.STALE_CONTROL_SESSION

        if control_session_id != self._control_session_id:
            if self._control_session_id is not None:
                self._retired_control_sessions.add(self._control_session_id)
            self._invalidate(revoked=False)
            self._control_session_id = control_session_id
            self._last_message_sequence = None

        if (
            self._last_message_sequence is not None
            and message_sequence <= self._last_message_sequence
        ):
            return (
                TokenVerdict.OTHER_HOLDER
                if holder_robot_id != self._robot_id
                else TokenVerdict.STALE_MESSAGE_SEQUENCE
            )

        self._last_message_sequence = message_sequence

        if holder_robot_id != self._robot_id:
            self._invalidate(revoked=False)
            return TokenVerdict.HOLDER_CHANGED

        if token_id == '':
            self._invalidate(revoked=True)
            return TokenVerdict.REVOKED

        if self._token_id is not None and token_id != self._token_id:
            self._invalidate(revoked=False)

        if not math.isfinite(lease_seconds) or lease_seconds <= 0.0:
            return TokenVerdict.INVALID_LEASE

        self._token_id = token_id
        self._lease_expires_at = float(now) + float(lease_seconds)
        self._revoked_last = False
        return TokenVerdict.ACCEPTED

    def authority(self, now: float) -> DriveAuthority:
        self._check_time(now)
        if self._token_id is None:
            return DriveAuthority.MISSING
        if now >= self._lease_expires_at:
            return DriveAuthority.EXPIRED
        return DriveAuthority.GRANTED

    def drive_allowed(self, now: float) -> bool:
        return self.authority(now) is DriveAuthority.GRANTED

    def remaining_lease(self, now: float) -> float:
        self._check_time(now)
        if self._lease_expires_at is None:
            return 0.0
        return max(0.0, self._lease_expires_at - now)

    def _validate_observation(
        self,
        control_session_id,
        token_id,
        holder_robot_id,
        lease_seconds,
        message_sequence,
        now,
    ):
        if not isinstance(control_session_id, str) or not control_session_id:
            raise ValueError('control_session_id must be a non-empty str')
        if not isinstance(token_id, str):
            raise ValueError('token_id must be a str')
        if holder_robot_id not in ROBOT_IDS:
            raise ValueError(f'holder_robot_id must be one of {ROBOT_IDS}')
        if isinstance(lease_seconds, bool) or not isinstance(
            lease_seconds, (int, float)
        ):
            raise ValueError('lease_seconds must be a real number')
        if isinstance(message_sequence, bool) or not isinstance(
            message_sequence, int
        ):
            raise ValueError('message_sequence must be an int')
        if not 1 <= message_sequence <= UINT64_MAX:
            raise ValueError('message_sequence must be between 1 and uint64 max')
        self._check_time(now)

    def _invalidate(self, revoked: bool):
        self._token_id = None
        self._lease_expires_at = None
        self._revoked_last = revoked

    @staticmethod
    def _check_time(now):
        if isinstance(now, bool) or not isinstance(now, (int, float)):
            raise ValueError('now must be a real number')
        if not math.isfinite(now):
            raise ValueError('now must be finite')

    def _advance_clock(self, now):
        if self._clock is not None and now < self._clock:
            raise ValueError('now must not move backwards')
        self._clock = float(now)
