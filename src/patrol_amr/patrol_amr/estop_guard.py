"""E-stop reflection using interfaces.md section 3.1 field names.

The reason numbers and the system-wide ``target_robot_id`` value remain
TBD-IF-004. Therefore this guard stores ``reason`` as an opaque uint8 and
only applies messages whose target exactly matches its own robot ID.
"""

from enum import Enum


ROBOT_IDS = ('robot1', 'robot6')
UINT8_MAX = 0xFF
UINT64_MAX = 0xFFFFFFFFFFFFFFFF

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
        self._latched = False
        self._last_sequence = None

    @property
    def robot_id(self) -> str:
        return self._robot_id

    @property
    def stopped(self) -> bool:
        return self._active or self._latched

    @property
    def reason(self):
        return self._reason

    @property
    def latched(self) -> bool:
        return self._latched

    @property
    def last_sequence(self):
        return self._last_sequence

    def observe(
        self,
        target_robot_id: str,
        active: bool,
        reason: int,
        latched: bool,
        sequence: int,
    ) -> EStopVerdict:
        """Apply a newer observation addressed exactly to this robot."""
        if not isinstance(target_robot_id, str) or not target_robot_id:
            raise ValueError('target_robot_id must be a non-empty str')
        if not isinstance(active, bool):
            raise ValueError('active must be a bool')
        if isinstance(reason, bool) or not isinstance(reason, int):
            raise ValueError('reason must be an int')
        if not 0 <= reason <= UINT8_MAX:
            raise ValueError('reason must fit in uint8')
        if not isinstance(latched, bool):
            raise ValueError('latched must be a bool')
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise ValueError('sequence must be an int')
        if not 1 <= sequence <= UINT64_MAX:
            raise ValueError('sequence must be between 1 and uint64 max')

        if self._last_sequence is not None and sequence <= self._last_sequence:
            return EStopVerdict.STALE_SEQUENCE

        # A single arbiter sequence orders the common stream, including
        # observations addressed to the other robot.
        self._last_sequence = sequence
        if target_robot_id != self._robot_id:
            return EStopVerdict.OTHER_TARGET

        self._active = active
        self._reason = reason
        self._latched = latched
        return EStopVerdict.ACCEPTED
