"""Final motion gate combining independent local-safety verdicts.

Plain Python module, not a ROS node; local_safety_supervisor (6단계)
combines DriveTokenGuard.authority() and EStopGuard.stopped (and any
future guard) through this gate before publishing the final per-robot
velocity output. interfaces.md 7절: "local_safety_supervisor는 로봇별
최종 속도 출력의 유일한 발행자다."

Out of scope for this module, and not guessed at:

- Choosing between Nav2 and yaw-alignment drive candidates
  (TBD-AMR-001 "주행 중재").
- Deceleration profile, allowed stopping distance, obstacle detection, and
  sensor-failure judgment (TBD-AMR-006). These depend on real robot
  dynamics and sensor specs this repository does not have; picking numbers
  without them would not be safe, only look implemented.
- The final velocity message type/topic (TBD-IF-009). A candidate here is
  a plain (linear, angular) float pair, not a ROS message.

What IS already decided and implemented here: amr.md 3절 states an invalid
drive token forces "안전 정지" and an active E-stop is "즉시 반영"한다.
Both are unconditional stop requirements independent of any candidate, so
this guard ANDs them: either blocks the output to a full stop, or passes
the (already-arbitrated) candidate through unchanged.
"""

from enum import Enum
import math


STOP = (0.0, 0.0)


class MotionBlockReason(Enum):
    """Independent reasons the final output was forced to STOP.

    More than one can apply to the same observation. evaluate() reports
    every reason that applies rather than picking one, because no document
    defines a priority between them -- the output (STOP) does not depend
    on which reason is reported.
    """

    DRIVE_TOKEN_NOT_GRANTED = 'drive_token_not_granted'
    ESTOP_ACTIVE = 'estop_active'


class MotionGuard:
    """Pass a velocity candidate through, or replace it with STOP.

    Stateless: every call is independent. local_safety_supervisor supplies
    the current DriveTokenGuard.authority()/EStopGuard.stopped verdicts
    each control cycle; this guard keeps no time or history of its own.
    """

    def evaluate(self, drive_token_granted: bool, estop_active: bool, candidate):
        """Return (output, blocked_reasons).

        `candidate` is a (linear, angular) float pair, already arbitrated
        upstream (TBD-AMR-001) -- this guard does not choose between
        drive candidates and does not clamp or shape a permitted one.
        """
        linear, angular = self._validate_candidate(candidate)
        reasons = self.blocked_reasons(drive_token_granted, estop_active)
        if reasons:
            return STOP, reasons
        return (linear, angular), reasons

    def blocked_reasons(self, drive_token_granted: bool, estop_active: bool):
        """Reasons motion would be blocked, independent of any candidate.

        6단계 local_safety_supervisor의 신선도 재확인 타이머가 이 메서드를
        쓴다: 새 메시지 없이도(예: drive_token lease 만료) 매 주기 이 값을
        다시 물어봐 변화가 있으면 다시 로그·발행한다. candidate 가 필요
        없으므로 아직 실제 속도 후보가 없는 시점에도 호출할 수 있다.
        """
        if not isinstance(drive_token_granted, bool):
            raise ValueError('drive_token_granted must be a bool')
        if not isinstance(estop_active, bool):
            raise ValueError('estop_active must be a bool')
        reasons = set()
        if not drive_token_granted:
            reasons.add(MotionBlockReason.DRIVE_TOKEN_NOT_GRANTED)
        if estop_active:
            reasons.add(MotionBlockReason.ESTOP_ACTIVE)
        return frozenset(reasons)

    @staticmethod
    def _validate_candidate(candidate):
        if not isinstance(candidate, tuple) or len(candidate) != 2:
            raise ValueError('candidate must be a (linear, angular) tuple')
        linear, angular = candidate
        for name, value in (('linear', linear), ('angular', angular)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f'candidate {name} must be a real number')
            if not math.isfinite(value):
                raise ValueError(f'candidate {name} must be finite')
        return float(linear), float(angular)
