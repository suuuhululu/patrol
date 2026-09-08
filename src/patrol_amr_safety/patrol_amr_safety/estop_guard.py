"""E-stop reflection using interfaces.md section 3.1 field names.

The reason numbers and the system-wide ``target_robot_id`` value remain
TBD-IF-004. Therefore this guard stores ``reason`` as an opaque uint8 and
only applies messages whose target exactly matches its own robot ID.

15단계 added the local defensive latch. Q-10 and interfaces.md 3.1절 both
state it plainly: "물리 E-stop은 수동 reset까지 latch". Mirroring the
arbiter's ``latched`` field is not enough for that -- if the arbiter later
publishes ``latched=false``, or stops publishing at all, a mirror would let
the robot move again without anyone having touched the button.

So an accepted ``latched=true`` engages a latch this guard owns, and no
incoming message clears it. Only ``reset_local_latch()`` does.

What is deliberately NOT here: the path that calls that reset. TBD-IF-004
still owes the manual reset request contract (topic or service, who may
send it, what acknowledges it), and inventing one would put a way to
release a physical E-stop into the system on a guess. Until it is agreed,
the reset exists as a method with no ROS caller, and the consequence is
recorded in amr.md 3.2절: a latched robot stays stopped until the node is
restarted. That is the fail-safe direction and it is the argument for
closing TBD-IF-004, not a reason to guess at it.
"""

from enum import Enum


ROBOT_IDS = ('robot1', 'robot6')
UINT8_MAX = 0xFF
UINT64_MAX = 0xFFFFFFFFFFFFFFFF

EVENT_ACTIVATED = 'E_STOP_ACTIVATED'
EVENT_AUTO_RELEASED = 'E_STOP_AUTO_RELEASED'
EVENT_LATCH_ENGAGED = 'E_STOP_LOCAL_LATCH_ENGAGED'
EVENT_LATCH_RESET = 'E_STOP_LOCAL_LATCH_RESET'


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
        # 관제가 보낸 latched 를 그대로 비추는 _latched 와 달리, 이 값은
        # 한 번 서면 들어오는 메시지로는 내려가지 않는다. reset_local_latch()
        # 만 내린다.
        self._local_latch = False
        self._last_sequence = None

    @property
    def robot_id(self) -> str:
        return self._robot_id

    @property
    def stopped(self) -> bool:
        return self._active or self._latched or self._local_latch

    @property
    def reason(self):
        return self._reason

    @property
    def latched(self) -> bool:
        """The arbiter's latched flag as last observed."""
        return self._latched

    @property
    def local_latch(self) -> bool:
        """This guard's own latch; only reset_local_latch() clears it."""
        return self._local_latch

    def reset_local_latch(self) -> bool:
        """Clear the local latch; True if it had been engaged.

        No ROS caller exists yet: the manual reset request path is the open
        half of TBD-IF-004. This is the seam that path will attach to, kept
        deliberately small so agreeing the contract is the only work left.
        """
        if not self._local_latch:
            return False
        self._local_latch = False
        return True

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
        if latched:
            self._local_latch = True
        return EStopVerdict.ACCEPTED
