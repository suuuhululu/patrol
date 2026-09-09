"""
Control-owned integration profile and vision input state.

The classes in this module deliberately have no ROS dependency so timing and
state transitions can be exercised with deterministic monotonic timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


NANOSECONDS_PER_SECOND = 1_000_000_000
PERMIT_TIMEOUT_NS = 5 * NANOSECONDS_PER_SECOND
PERMIT_RECOVERY_MAX_GAP_NS = NANOSECONDS_PER_SECOND // 2
PERMIT_RECOVERY_MIN_SPAN_NS = 3 * NANOSECONDS_PER_SECOND // 10
PERMIT_RECOVERY_SAMPLE_COUNT = 3

ROBOT_IDS = frozenset({'robot1', 'robot6'})
DETECTION_EVENT_TYPES = frozenset({1, 2, 3})


class IntegrationProfile(str, Enum):
    """Startup-only integration configurations for the control node."""

    VISION_INTEGRATION = 'vision_integration'
    FULL_SYSTEM = 'full_system'


@dataclass(frozen=True)
class ProfileCapabilities:
    """Features enabled by one integration profile."""

    vision_input: bool
    amr_input: bool
    amr_output: bool
    production_ready: bool


PROFILE_CAPABILITIES = {
    IntegrationProfile.VISION_INTEGRATION: ProfileCapabilities(
        vision_input=True,
        amr_input=False,
        amr_output=False,
        production_ready=True,
    ),
    IntegrationProfile.FULL_SYSTEM: ProfileCapabilities(
        vision_input=True,
        amr_input=True,
        amr_output=True,
        production_ready=False,
    ),
}


def parse_profile(value: str) -> IntegrationProfile:
    """Return a known profile or fail instead of silently choosing one."""
    try:
        return IntegrationProfile(value)
    except ValueError as exc:
        choices = ', '.join(profile.value for profile in IntegrationProfile)
        raise ValueError(
            f'integration_profile must be one of: {choices}'
        ) from exc


class PermitHealth(str, Enum):
    """Control-local health of the CCTV patrol permit stream."""

    WAITING = 'waiting'
    HEALTHY = 'healthy'
    TIMED_OUT = 'timed_out'
    RECOVERING = 'recovering'


@dataclass(frozen=True)
class PermitTransition:
    """Observable result of one permit message or timeout check."""

    health: PermitHealth
    patrol_allowed: bool
    value_changed: bool = False
    became_timed_out: bool = False
    recovered: bool = False


class PermitMonitor:
    """Track the Bool permit with the fixed timeout and recovery contract."""

    def __init__(self, started_at_ns: int) -> None:
        """Start with the contract default while waiting for the publisher."""
        if started_at_ns < 0:
            raise ValueError('started_at_ns must not be negative')
        self._started_at_ns = started_at_ns
        self._last_received_ns: int | None = None
        self._patrol_allowed = True
        self._health = PermitHealth.WAITING
        self._recovery_value: bool | None = None
        self._recovery_times: list[int] = []

    @property
    def patrol_allowed(self) -> bool:
        """Return the last committed permit value."""
        return self._patrol_allowed

    @property
    def health(self) -> PermitHealth:
        """Return current stream health."""
        return self._health

    @property
    def last_received_ns(self) -> int | None:
        """Return the latest local monotonic receive time."""
        return self._last_received_ns

    def check_timeout(self, now_ns: int) -> PermitTransition:
        """Enter TIMED_OUT once five seconds pass without a message."""
        self._validate_time(now_ns)
        reference_ns = (
            self._last_received_ns
            if self._last_received_ns is not None
            else self._started_at_ns
        )
        unhealthy = self._health in {
            PermitHealth.TIMED_OUT,
            PermitHealth.RECOVERING,
        }
        if now_ns - reference_ns < PERMIT_TIMEOUT_NS:
            return self._transition()
        if self._health is PermitHealth.TIMED_OUT:
            return self._transition()

        self._health = PermitHealth.TIMED_OUT
        self._reset_recovery()
        return self._transition(became_timed_out=not unhealthy)

    def observe(self, value: bool, now_ns: int) -> PermitTransition:
        """Apply a permit sample and enforce post-timeout recovery filtering."""
        if type(value) is not bool:
            raise ValueError('patrol_allowed must be bool')
        self._validate_time(now_ns)
        self.check_timeout(now_ns)
        self._last_received_ns = now_ns

        if self._health in {
            PermitHealth.TIMED_OUT,
            PermitHealth.RECOVERING,
        }:
            return self._observe_recovery(value, now_ns)

        changed = value != self._patrol_allowed
        self._patrol_allowed = value
        self._health = PermitHealth.HEALTHY
        return self._transition(value_changed=changed)

    def _observe_recovery(
        self, value: bool, now_ns: int
    ) -> PermitTransition:
        if (
            self._recovery_value is None
            or value != self._recovery_value
            or not self._recovery_times
            or now_ns - self._recovery_times[-1]
            > PERMIT_RECOVERY_MAX_GAP_NS
        ):
            self._recovery_value = value
            self._recovery_times = [now_ns]
            self._health = PermitHealth.RECOVERING
            return self._transition()

        self._recovery_times.append(now_ns)
        self._health = PermitHealth.RECOVERING
        if len(self._recovery_times) < PERMIT_RECOVERY_SAMPLE_COUNT:
            return self._transition()

        recovery_span = now_ns - self._recovery_times[0]
        if recovery_span < PERMIT_RECOVERY_MIN_SPAN_NS:
            self._recovery_times = [now_ns]
            return self._transition()

        changed = value != self._patrol_allowed
        self._patrol_allowed = value
        self._health = PermitHealth.HEALTHY
        self._reset_recovery()
        return self._transition(
            value_changed=changed,
            recovered=True,
        )

    def _validate_time(self, now_ns: int) -> None:
        if now_ns < self._started_at_ns:
            raise ValueError('monotonic time moved before startup')
        if (
            self._last_received_ns is not None
            and now_ns < self._last_received_ns
        ):
            raise ValueError('monotonic receive time moved backwards')

    def _reset_recovery(self) -> None:
        self._recovery_value = None
        self._recovery_times = []

    def _transition(self, **changes: bool) -> PermitTransition:
        return PermitTransition(
            health=self._health,
            patrol_allowed=self._patrol_allowed,
            **changes,
        )


class DetectionDisposition(str, Enum):
    """Result of validating a v1.1 DetectionEvent for control use."""

    ACCEPTED = 'accepted'
    DUPLICATE = 'duplicate'
    REJECTED = 'rejected'


@dataclass(frozen=True)
class DetectionTrackingResult:
    """Validation and de-duplication result for one event."""

    disposition: DetectionDisposition
    detail: str = ''


class DetectionEventTracker:
    """Validate v1.1 control-facing DetectionEvent identities and enum."""

    def __init__(self) -> None:
        self._event_robots: dict[str, str] = {}

    def observe(
        self,
        *,
        expected_robot_id: str,
        robot_id: str,
        message_id: str,
        event_id: str,
        event_type: int,
    ) -> DetectionTrackingResult:
        """Accept one valid event ID once for the current control session."""
        if expected_robot_id not in ROBOT_IDS:
            raise ValueError('expected_robot_id must be robot1 or robot6')
        if robot_id != expected_robot_id:
            return DetectionTrackingResult(
                DetectionDisposition.REJECTED,
                'topic robot and payload robot differ',
            )
        if not message_id or not event_id:
            return DetectionTrackingResult(
                DetectionDisposition.REJECTED,
                'message_id and event_id are required',
            )
        if event_type not in DETECTION_EVENT_TYPES:
            return DetectionTrackingResult(
                DetectionDisposition.REJECTED,
                'event_type must be FIRE, LEAK, or OBSTACLE',
            )

        known_robot = self._event_robots.get(event_id)
        if known_robot == robot_id:
            return DetectionTrackingResult(DetectionDisposition.DUPLICATE)
        if known_robot is not None:
            return DetectionTrackingResult(
                DetectionDisposition.REJECTED,
                'event_id is already bound to another robot',
            )

        self._event_robots[event_id] = robot_id
        return DetectionTrackingResult(DetectionDisposition.ACCEPTED)
