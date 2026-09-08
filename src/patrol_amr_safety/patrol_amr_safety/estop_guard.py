"""Reflect the Safety Arbiter's representative E-stop reason for one AMR."""

from enum import Enum


ROBOT_IDS = ('robot1', 'robot6')
UINT8_MAX = 0xFF
UINT64_MAX = 0xFFFFFFFFFFFFFFFF
ALL_ROBOTS = 'all'
ESTOP_REASONS = frozenset(range(7))

EVENT_ACTIVATED = 'E_STOP_ACTIVATED'
EVENT_AUTO_RELEASED = 'E_STOP_AUTO_RELEASED'


class EStopVerdict(Enum):
    ACCEPTED = 'accepted'
    OTHER_TARGET = 'other_target'
    STALE_SEQUENCE = 'stale_sequence'


class EStopGuard:
    """Reflect the latest accepted E-stop state for one robot."""

    def __init__(self, robot_id: str):
        if robot_id not in ROBOT_IDS:
            raise ValueError(f'robot_id must be one of {ROBOT_IDS}')
        self._robot_id = robot_id
        self._active = True
        self._reason = None
        self._last_sequence = None

    @property
    def robot_id(self) -> str:
        return self._robot_id

    @property
    def stopped(self) -> bool:
        return self._active

    @property
    def reason(self):
        return self._reason

    @property
    def last_sequence(self):
        return self._last_sequence

    def observe(
        self,
        target_robot_id: str,
        active: bool,
        reason: int,
        sequence: int,
    ) -> EStopVerdict:
        """Apply a newer observation addressed exactly to this robot."""
        if not isinstance(target_robot_id, str) or not target_robot_id:
            raise ValueError('target_robot_id must be a non-empty str')
        if not isinstance(active, bool):
            raise ValueError('active must be a bool')
        if isinstance(reason, bool) or not isinstance(reason, int):
            raise ValueError('reason must be an int')
        if reason not in ESTOP_REASONS:
            raise ValueError('reason must be an ESTOP_REASON value from 0 to 6')
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise ValueError('sequence must be an int')
        if not 1 <= sequence <= UINT64_MAX:
            raise ValueError('sequence must be between 1 and uint64 max')

        if self._last_sequence is not None and sequence <= self._last_sequence:
            return EStopVerdict.STALE_SEQUENCE

        # A single arbiter sequence orders the common stream, including
        # observations addressed to the other robot.
        self._last_sequence = sequence
        if target_robot_id not in (self._robot_id, ALL_ROBOTS):
            return EStopVerdict.OTHER_TARGET

        self._active = active
        self._reason = reason
        return EStopVerdict.ACCEPTED
