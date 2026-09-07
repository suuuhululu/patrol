"""Drive token acceptance and Q-01 local lease for the AMR safety path.

Implements the interfaces.md section 3 acceptance rules. This is a plain
Python module, not a ROS node; local_safety_supervisor consumes it and owns
the final velocity output. Elapsed time is measured with caller-supplied
local monotonic seconds only, because interfaces.md forbids comparing
unsynchronised clocks across senders.
"""

from enum import Enum
import math


ROBOT_IDS = ('robot1', 'robot6')

NANOSECONDS_PER_SECOND = 1_000_000_000

SEQUENCE_MAX = 0xFFFFFFFF


class TokenVerdict(Enum):
    """Outcome of one /control/drive_token observation."""

    ACCEPTED = 'accepted'
    REVOKED = 'revoked'
    HOLDER_CHANGED = 'holder_changed'
    OTHER_HOLDER = 'other_holder'
    STALE_SEQUENCE = 'stale_sequence'
    INVALID_LEASE = 'invalid_lease'


class DriveAuthority(Enum):
    """Local drive permission derived from the accepted token and its lease.

    MISSING and EXPIRED correspond to the interfaces.md diagnostic codes 600
    DRIVE_TOKEN_MISSING and 601 DRIVE_TOKEN_EXPIRED. Revocation reports
    MISSING because the shared code list has no separate revoked value; the
    AMR-side DRIVE_TOKEN_REVOKED log is selected with revoked_last instead.
    """

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
    """Track the accepted drive token and its Q-01 lease for one robot.

    Only an accepted observation refreshes the lease. interfaces.md section 3
    forbids extending it on callback arrival alone, so discarded messages
    never move the expiry. The guard reports permission; it never starts
    motion, because a new token alone must not resume a mission.
    """

    def __init__(self, robot_id: str):
        if robot_id not in ROBOT_IDS:
            raise ValueError(f'robot_id must be one of {ROBOT_IDS}')
        self._robot_id = robot_id
        self._token = None
        self._sequence_token = None
        self._last_sequence = None
        self._lease_expires_at = None
        self._revoked_last = False
        self._clock = None

    @property
    def robot_id(self) -> str:
        return self._robot_id

    @property
    def token(self):
        """Currently accepted token string, or None when no token is held."""
        return self._token

    @property
    def last_sequence(self):
        """Sequence floor, scoped to sequence_token (TBD-IF-002 decision)."""
        return self._last_sequence

    @property
    def sequence_token(self):
        """Token string the current sequence floor belongs to."""
        return self._sequence_token

    @property
    def revoked_last(self) -> bool:
        """True when the last state change was a control-side revocation."""
        return self._revoked_last

    def observe(
        self,
        token: str,
        holder_robot_id: str,
        lease_seconds: float,
        sequence: int,
        now: float,
    ) -> TokenVerdict:
        """Apply one observation and return why it was accepted or discarded."""
        self._advance_clock(now)
        if not isinstance(token, str) or not isinstance(holder_robot_id, str):
            raise ValueError('token and holder_robot_id must be str')
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise ValueError('sequence must be an int')
        if not 0 <= sequence <= SEQUENCE_MAX:
            raise ValueError('sequence must fit in uint32')
        if isinstance(lease_seconds, bool) or not isinstance(
            lease_seconds, (int, float)
        ):
            raise ValueError('lease_seconds must be a real number')

        # sequence 하한은 token 문자열 epoch 단위다 (TBD-IF-002 결정,
        # 2026-09-07). 같은 token 의 역행·중복은 폐기하고, token 이 바뀌면
        # 관제 재시작이나 권한 이동이므로 하한을 새로 잡는다. 하한을 영구
        # 고정하면 관제 재시작 뒤 주행을 영영 되찾지 못한다. 재생 위험은
        # drive_token 의 lifespan 500 ms 가 전송 계층에서 제한한다.
        if token == self._sequence_token and sequence <= self._last_sequence:
            return (
                TokenVerdict.OTHER_HOLDER
                if holder_robot_id != self._robot_id
                else TokenVerdict.STALE_SEQUENCE
            )

        self._sequence_token = token
        self._last_sequence = sequence

        # 공통 토픽의 권한 보유자는 하나다. 앞선 sequence 로 다른 holder 가
        # 지명되면 관제가 권한을 넘긴 것이므로 lease 만료를 기다리지 않고
        # 즉시 끊는다 (TBD-IF-002 결정, 2026-09-07).
        if holder_robot_id != self._robot_id:
            self._invalidate(revoked=False)
            return TokenVerdict.HOLDER_CHANGED

        if token == '':
            self._invalidate(revoked=True)
            return TokenVerdict.REVOKED

        # token 문자열이 바뀌면 기존 token 을 즉시 무효화한다.
        if self._token is not None and token != self._token:
            self._invalidate(revoked=False)

        if not math.isfinite(lease_seconds) or lease_seconds <= 0.0:
            return TokenVerdict.INVALID_LEASE

        self._token = token
        self._lease_expires_at = now + float(lease_seconds)
        self._revoked_last = False
        return TokenVerdict.ACCEPTED

    def authority(self, now: float) -> DriveAuthority:
        """Report drive permission at the caller-supplied monotonic time."""
        self._check_time(now)
        if self._token is None:
            return DriveAuthority.MISSING
        if now >= self._lease_expires_at:
            return DriveAuthority.EXPIRED
        return DriveAuthority.GRANTED

    def drive_allowed(self, now: float) -> bool:
        """True only while a valid token is held and its lease has not run out."""
        return self.authority(now) is DriveAuthority.GRANTED

    def remaining_lease(self, now: float) -> float:
        """Seconds left on the lease; 0.0 when no token is held or it expired."""
        self._check_time(now)
        if self._lease_expires_at is None:
            return 0.0
        return max(0.0, self._lease_expires_at - now)

    def _invalidate(self, revoked: bool) -> None:
        """Drop the held token; the sequence floor is left to the caller."""
        self._token = None
        self._lease_expires_at = None
        self._revoked_last = revoked

    def _check_time(self, now: float) -> None:
        """Validate a caller-supplied monotonic time without consuming it.

        Queries are side-effect free so the supervisor may ask about the same
        instant repeatedly and in any order within one control cycle.
        """
        if isinstance(now, bool) or not isinstance(now, (int, float)):
            raise ValueError('now must be a real number')
        if not math.isfinite(now):
            raise ValueError('now must be finite')

    def _advance_clock(self, now: float) -> None:
        """Validate and record an observation time; it must not move back."""
        self._check_time(now)
        if self._clock is not None and now < self._clock:
            raise ValueError('now must not move backwards')
        self._clock = now
