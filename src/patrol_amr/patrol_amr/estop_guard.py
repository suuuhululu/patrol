"""E-stop reflection for the AMR safety path (EStop.msg, Q-10).

Plain Python module, not a ROS node; local_safety_supervisor (6단계) will
subscribe to /control/estop and drive this guard. The message contract
states the AMR's role is reflection only: activation applies immediately,
and the 3-second continuous release condition is judged by the Safety
Arbiter, not timed locally here. amr.md forbids adding an arbitrary local
timeout, and heartbeat/staleness detection is a separate, still-undecided
mechanism (TBD-IF-004) -- this guard adds none of its own.

Unlike DriveTokenGuard, this guard takes no robot_id: EStop.msg has no
holder/robot field, and interfaces.md describes /control/estop as a single
broadcast to "AMR" (not "각 AMR" like drive_token), so one observation
applies identically to whichever robot's node holds this guard.
"""

from enum import Enum, IntEnum
import math


NANOSECONDS_PER_SECOND = 1_000_000_000
SEQUENCE_MAX = 0xFFFFFFFF
CAUSE_MAX = 0xFF

# amr.md 7절이 보존을 요구하는 기존 안전 로그 중, active 필드 하나의 전이만으로
# 모호함 없이 판정 가능한 두 가지 이름이다. observe() 는 이 이름을 반환하지
# 않는다; 호출자가 observe() 전후로 stopped 를 비교해 로그를 남긴다.
# release_condition_started_at 의 '설정 안 됨'을 뜻하는 값은 계약에 없어
# E_STOP_RELEASE_CONDITION_STARTED·_CANCELED 판정은 이 모듈이 추측하지
# 않는다 (TBD-IF-004).
EVENT_ACTIVATED = 'E_STOP_ACTIVATED'
EVENT_AUTO_RELEASED = 'E_STOP_AUTO_RELEASED'


class EStopCause(IntEnum):
    """EStop.msg CAUSE_* constants."""

    UNKNOWN = 0
    PHYSICAL_BUTTON = 1
    OPERATOR = 2
    COMM_LOST = 3
    TOKEN_INVALID = 4
    OBSTACLE = 5
    SENSOR_FAULT = 6


class EStopVerdict(Enum):
    """Outcome of one /control/estop observation."""

    ACCEPTED = 'accepted'
    STALE_SEQUENCE = 'stale_sequence'


def time_to_seconds(sec: int, nanosec: int) -> float:
    """Convert a builtin_interfaces/Time field pair to float seconds.

    A passive record of the Safety Arbiter's clock, never compared to a
    local clock: interfaces.md forbids comparing unsynchronised monotonic
    clocks, and this guard keeps no timer of its own (Q-10). Used for
    activated_at / release_condition_started_at before calling observe().
    """
    for name, value in (('sec', sec), ('nanosec', nanosec)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f'{name} must be an int')
    return sec + nanosec / NANOSECONDS_PER_SECOND


class EStopGuard:
    """Reflect the latest accepted /control/estop observation.

    AMR does not judge release; it reflects `active` as published. Q-10's
    physical-latch-until-manual-reset property is enforced by the Safety
    Arbiter upstream, per the message contract's own "AMR 의 역할은
    반영뿐이다". Whether AMR should also defensively latch a physical
    E-stop locally is open: EStop.msg defines no reset-request field, and
    TBD-IF-004 leaves the release request contract undecided, so this
    guard does not invent a local latch or a reset method.
    """

    def __init__(self):
        # 메시지를 받기 전에는 정지로 취급한다. battery_monitor 의 UNKNOWN,
        # DriveTokenGuard 의 MISSING과 같은 안전 기본값이다.
        self._active = True
        self._cause = EStopCause.UNKNOWN
        self._physical = False
        self._source = ''
        self._last_sequence = None
        self._activated_at_seconds = None
        self._release_condition_started_at_seconds = None

    @property
    def stopped(self) -> bool:
        """True while E-stop is active; local_safety_supervisor blocks motion on this alone."""
        return self._active

    @property
    def cause(self):
        """Last accepted CAUSE_*: an EStopCause for known values, else the raw int."""
        return self._cause

    @property
    def physical(self) -> bool:
        """Last accepted `physical` flag; False before any message is received."""
        return self._physical

    @property
    def source(self) -> str:
        """Last accepted `source`; '' before any message is received."""
        return self._source

    @property
    def last_sequence(self):
        """Highest accepted sequence, or None before any message is received."""
        return self._last_sequence

    @property
    def activated_at_seconds(self):
        """Arbiter-clock seconds from the last accepted message, or None."""
        return self._activated_at_seconds

    @property
    def release_condition_started_at_seconds(self):
        """Arbiter-clock seconds from the last accepted message, or None."""
        return self._release_condition_started_at_seconds

    def observe(
        self,
        active: bool,
        cause: int,
        physical: bool,
        source: str,
        sequence: int,
        activated_at_seconds: float,
        release_condition_started_at_seconds: float,
    ) -> EStopVerdict:
        """Apply one observation and report whether it was accepted.

        Compare `.stopped` before and after a call to detect
        EVENT_ACTIVATED / EVENT_AUTO_RELEASED for the safety log.
        """
        if not isinstance(active, bool):
            raise ValueError('active must be a bool')
        if isinstance(cause, bool) or not isinstance(cause, int):
            raise ValueError('cause must be an int')
        if not 0 <= cause <= CAUSE_MAX:
            raise ValueError('cause must fit in uint8')
        if not isinstance(physical, bool):
            raise ValueError('physical must be a bool')
        if not isinstance(source, str):
            raise ValueError('source must be a str')
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise ValueError('sequence must be an int')
        if not 0 <= sequence <= SEQUENCE_MAX:
            raise ValueError('sequence must fit in uint32')
        for name, value in (
            ('activated_at_seconds', activated_at_seconds),
            (
                'release_condition_started_at_seconds',
                release_condition_started_at_seconds,
            ),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f'{name} must be a real number')
            if not math.isfinite(value):
                raise ValueError(f'{name} must be finite')

        # 재수신·역순 메시지는 폐기한다 (sequence 필드 주석의 명시된 목적).
        # 최초 관측은 sequence 값과 무관하게 항상 수락한다.
        if self._last_sequence is not None and sequence <= self._last_sequence:
            return EStopVerdict.STALE_SEQUENCE

        self._last_sequence = sequence
        self._active = active
        try:
            self._cause = EStopCause(cause)
        except ValueError:
            # 미정의 원인 값(향후 확장 대비)도 active 반영을 막지 않는다.
            self._cause = cause
        self._physical = physical
        self._source = source
        self._activated_at_seconds = float(activated_at_seconds)
        self._release_condition_started_at_seconds = float(
            release_condition_started_at_seconds
        )
        return EStopVerdict.ACCEPTED
