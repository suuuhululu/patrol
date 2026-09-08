"""Final motion gate combining independent local-safety verdicts.

Plain Python module, not a ROS node; local_safety_supervisor (6단계)
combines DriveTokenGuard.authority() and EStopGuard.stopped (and any
future guard) through this gate before publishing the final per-robot
velocity output. interfaces.md 7절: "local_safety_supervisor는 로봇별
최종 속도 출력의 유일한 발행자다."

Two gates live here and they answer different questions:

- blocked_reasons() is the *permission* gate -- token and E-stop only.
  6단계's motion_allowed signal uses it, and it needs no candidate.
- evaluate() is the *output* gate -- the permission gate plus whether a
  usable candidate actually exists right now (Q-17). Whether Nav2 is
  currently producing candidates says nothing about whether motion is
  permitted, so the two are kept apart rather than merged.

Out of scope for this module, and not guessed at:

- Choosing between Nav2 and yaw-alignment drive candidates
  (TBD-AMR-001 "주행 중재"). evaluate() takes one already-arbitrated
  candidate.
- Deceleration profile, allowed stopping distance, obstacle detection, and
  sensor-failure judgment (TBD-AMR-006). These depend on real robot
  dynamics and sensor specs this repository does not have; picking numbers
  without them would not be safe, only look implemented.
- ROS message types. TBD-IF-009 fixed the wire contract on 2026-09-08
  (candidates TwistStamped on cmd_vel_safe/cmd_vel_yaw, final output Twist
  on /robotN/cmd_vel), but this module stays ROS-free: a candidate is a
  plain (linear, angular) float pair and its age is plain seconds. 12단계
  local_safety_supervisor does the conversion.

What IS already decided and implemented here: amr.md 3절 states an invalid
drive token forces "안전 정지" and an active E-stop is "즉시 반영"한다.
Both are unconditional stop requirements independent of any candidate, so
this guard ANDs them: either blocks the output to a full stop, or passes
the (already-arbitrated) candidate through unchanged.
"""

from enum import Enum
import math


STOP = (0.0, 0.0)

# Q-17 후보 신선도 (TBD-IF-009, 2026-09-08 AMR 확정). 구동부
# diffdrive_controller 의 cmd_vel_timeout 과 같은 값이다 -- 새 숫자를
# 만들지 않고 로봇이 이미 쓰는 값에 맞췄다. 이보다 오래된 후보는 최종
# 출력으로 내보내지 않는다. 관제 회신 전까지 AMR 측 확정값이다.
CANDIDATE_MAX_AGE_SECONDS = 0.5


class MotionBlockReason(Enum):
    """Independent reasons the final output was forced to STOP.

    More than one can apply to the same observation. evaluate() reports
    every reason that applies rather than picking one, because no document
    defines a priority between them -- the output (STOP) does not depend
    on which reason is reported.
    """

    DRIVE_TOKEN_NOT_GRANTED = 'drive_token_not_granted'
    ESTOP_ACTIVE = 'estop_active'
    CANDIDATE_MISSING = 'candidate_missing'
    CANDIDATE_STALE = 'candidate_stale'


class MotionGuard:
    """Pass a velocity candidate through, or replace it with STOP.

    Stateless: every call is independent. local_safety_supervisor supplies
    the current DriveTokenGuard.authority()/EStopGuard.stopped verdicts
    each control cycle; this guard keeps no time or history of its own.
    Candidate age is likewise measured by the caller and passed in, so the
    Q-17 comparison here needs no clock.
    """

    def evaluate(
        self,
        drive_token_granted: bool,
        estop_active: bool,
        candidate,
        candidate_age,
    ):
        """Return (output, blocked_reasons).

        `candidate` is a (linear, angular) float pair, already arbitrated
        upstream (TBD-AMR-001) -- this guard does not choose between
        drive candidates and does not clamp or shape a permitted one --
        or None when no candidate has been received yet.

        `candidate_age` is seconds elapsed since that candidate's stamp,
        measured by the caller, and must be None exactly when `candidate`
        is None. The two are passed together so a caller cannot ask about
        a candidate's freshness without saying which candidate it means.
        """
        permitted = None
        if candidate is not None:
            permitted = self._validate_candidate(candidate)
        reasons = set(self.blocked_reasons(drive_token_granted, estop_active))
        reasons |= self._candidate_reasons(candidate, candidate_age)
        if reasons:
            return STOP, frozenset(reasons)
        return permitted, frozenset(reasons)

    def blocked_reasons(self, drive_token_granted: bool, estop_active: bool):
        """Reasons motion is not *permitted*, independent of any candidate.

        6단계 local_safety_supervisor의 신선도 재확인 타이머가 이 메서드를
        쓴다: 새 메시지 없이도(예: drive_token lease 만료) 매 주기 이 값을
        다시 물어봐 변화가 있으면 다시 로그·발행한다. candidate 가 필요
        없으므로 아직 실제 속도 후보가 없는 시점에도 호출할 수 있다.

        후보 신선도(Q-17)는 여기 들어가지 않는다. 후보가 끊긴 것은 주행
        권한이 없다는 뜻이 아니라 내보낼 값이 없다는 뜻이라, motion_allowed
        가 후보 유무에 따라 흔들리지 않도록 evaluate() 쪽에만 둔다.
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
    def _candidate_reasons(candidate, candidate_age):
        """Q-17 판정. 후보 없음과 후보 낡음을 사유로 구분해 보고한다.

        Nav2 가 아직 뜨지 않은 것과 떠 있는데 늦는 것은 운영자가 볼 때
        원인이 다르므로 하나로 합치지 않았다. 출력은 두 경우 모두 STOP 이다.
        """
        if candidate is None:
            if candidate_age is not None:
                raise ValueError(
                    'candidate_age must be None when candidate is None'
                )
            return {MotionBlockReason.CANDIDATE_MISSING}
        if candidate_age is None:
            raise ValueError('candidate_age is required with a candidate')
        if (
            isinstance(candidate_age, bool)
            or not isinstance(candidate_age, (int, float))
        ):
            raise ValueError('candidate_age must be a real number of seconds')
        if not math.isfinite(candidate_age):
            raise ValueError('candidate_age must be finite')
        # 음수 age(후보 stamp 가 미래)는 낡음으로 보지 않는다. 후보와 이
        # 게이트는 같은 AMR PC 의 같은 시계를 쓰므로 정상 상태에서는 0 근처
        # 이고, 허용 가능한 시계 역행 폭을 정한 문서가 없어 임의 임계값을
        # 만들지 않았다. 다중 PC 시계 결합은 TBD-IF-002 잔여 항목이다.
        if candidate_age > CANDIDATE_MAX_AGE_SECONDS:
            return {MotionBlockReason.CANDIDATE_STALE}
        return set()

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
