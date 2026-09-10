"""ROS-independent state machine for the basic patrol control flow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, Iterable
from uuid import uuid4


class TaskState(IntEnum):
    """Patrol Feedback task states."""

    WAITING_FOR_TOKEN = 1
    UNDOCKING = 2
    INITIAL_POSE_READY = 3
    PATROLLING = 4
    MOVING_TO_SAFE_ZONE = 5
    DETECTION_PROCESSING = 6
    DETECTION_CONFIRMED = 7
    RESUMING = 8
    DOCKING = 9
    BLOCKED = 10
    WAYPOINT_REACHED = 11


class EventType(IntEnum):
    """Detection event values shared by Patrol and ReportDetection."""

    FIRE = 1
    LEAK = 2
    OBSTACLE = 3


class PatrolCommandType(IntEnum):
    """Control commands that adjust an active Patrol Action."""

    MOVE_TO_SAFE_ZONE = 1
    RESUME_PATROL = 2


@dataclass(frozen=True)
class GoalIntent:
    """Validated Patrol Goal payload."""

    command_id: str
    robot_id: str


@dataclass(frozen=True)
class CommandIntent:
    """PatrolCommand payload produced by a permit transition."""

    command_id: str
    robot_id: str
    command: PatrolCommandType


@dataclass(frozen=True)
class TokenFrame:
    """One robot-specific DriveToken publication."""

    robot_id: str
    token: str
    sequence: int


@dataclass(frozen=True)
class FeedbackEffect:
    """State changes caused by one Patrol Feedback sample."""

    accepted: bool
    token_granted: bool = False
    fire_hold_activated: bool = False


class ControlStateError(RuntimeError):
    """Raised when an operation violates the basic control state machine."""


class ControlCore:
    """Own exclusive mission, token, permit, and fire-hold state."""

    def __init__(
        self,
        robot_ids: Iterable[str],
        *,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        robots = tuple(robot_ids)
        if not robots or len(set(robots)) != len(robots):
            raise ValueError('robot_ids must be non-empty and unique')
        if any(not robot_id for robot_id in robots):
            raise ValueError('robot_ids cannot contain an empty value')

        self.robot_ids = robots
        self._token_factory = token_factory or (lambda: str(uuid4()))
        self._goal_sequence = 0
        self._command_sequence = 0
        self._token_sequences = {robot_id: 0 for robot_id in robots}

        self.patrol_allowed: bool | None = None
        self.active_robot_id: str | None = None
        self.goal_accepted = False
        self.drive_granted = False
        self.active_token = ''
        self.fire_hold = False
        self.fire_event_id = ''

    def prepare_goal(self, robot_id: str) -> GoalIntent:
        """Reserve the single active slot and create a Patrol Goal payload."""
        self._require_robot(robot_id)
        if self.active_robot_id is not None:
            raise ControlStateError(
                f'active patrol already exists for {self.active_robot_id}'
            )
        if self.patrol_allowed is not True:
            raise ControlStateError('patrol is not allowed by CCTV permit')
        if self.fire_hold:
            raise ControlStateError('fire hold is active')

        self._goal_sequence += 1
        self.active_robot_id = robot_id
        self.goal_accepted = False
        self.drive_granted = False
        self.active_token = ''
        return GoalIntent(
            command_id=f'cmd-{robot_id}-start-{self._goal_sequence:06d}',
            robot_id=robot_id,
        )

    def mark_goal_accepted(self, robot_id: str) -> None:
        """Record Action server acceptance without granting drive authority."""
        self._require_active(robot_id)
        self.goal_accepted = True

    def finish_goal(self, robot_id: str) -> None:
        """Release the active slot and revoke drive authority."""
        self._require_active(robot_id)
        self.active_robot_id = None
        self.goal_accepted = False
        self.drive_granted = False
        self.active_token = ''

    def revoke_drive(self, robot_id: str) -> None:
        """Revoke authority while an Action cancellation is in flight."""
        self._require_active(robot_id)
        self.drive_granted = False
        self.active_token = ''

    def observe_feedback(
        self,
        robot_id: str,
        *,
        task_state: int,
        event_type: int,
        event_id: str,
    ) -> FeedbackEffect:
        """Apply Feedback only for the accepted active Patrol Goal."""
        if robot_id != self.active_robot_id or not self.goal_accepted:
            return FeedbackEffect(accepted=False)
        try:
            state = TaskState(task_state)
        except ValueError:
            return FeedbackEffect(accepted=False)

        token_granted = False
        if (
            state is TaskState.WAITING_FOR_TOKEN
            and self.patrol_allowed is True
            and not self.drive_granted
        ):
            token = self._token_factory()
            if not token:
                raise ValueError('token_factory returned an empty token')
            self.active_token = token
            self.drive_granted = True
            token_granted = True

        fire_hold_activated = False
        if (
            state is TaskState.DETECTION_CONFIRMED
            and event_type == EventType.FIRE
            and event_id
            and not self.fire_hold
        ):
            self.fire_hold = True
            self.fire_event_id = event_id
            fire_hold_activated = True

        return FeedbackEffect(
            accepted=True,
            token_granted=token_granted,
            fire_hold_activated=fire_hold_activated,
        )

    def observe_permit(self, allowed: bool) -> tuple[CommandIntent, ...]:
        """Translate a permit edge into at most one active-mission command."""
        if not isinstance(allowed, bool):
            raise ValueError('allowed must be bool')
        if self.patrol_allowed is allowed:
            return ()
        self.patrol_allowed = allowed
        if self.active_robot_id is None or not self.goal_accepted:
            return ()

        command = (
            PatrolCommandType.RESUME_PATROL
            if allowed
            else PatrolCommandType.MOVE_TO_SAFE_ZONE
        )
        self._command_sequence += 1
        name = command.name.lower().replace('_', '-')
        return (
            CommandIntent(
                command_id=(
                    f'cmd-{self.active_robot_id}-{name}-'
                    f'{self._command_sequence:06d}'
                ),
                robot_id=self.active_robot_id,
                command=command,
            ),
        )

    def token_frames(self) -> tuple[TokenFrame, ...]:
        """Produce one monotonically sequenced frame for every robot."""
        frames = []
        for robot_id in self.robot_ids:
            self._token_sequences[robot_id] += 1
            token = (
                self.active_token
                if robot_id == self.active_robot_id and self.drive_granted
                else ''
            )
            frames.append(
                TokenFrame(
                    robot_id=robot_id,
                    token=token,
                    sequence=self._token_sequences[robot_id],
                )
            )
        return tuple(frames)

    def clear_fire_hold(self) -> None:
        """Explicitly clear the operator-owned fire hold."""
        self.fire_hold = False
        self.fire_event_id = ''

    def _require_robot(self, robot_id: str) -> None:
        if robot_id not in self.robot_ids:
            raise ValueError(f'unknown robot_id: {robot_id}')

    def _require_active(self, robot_id: str) -> None:
        self._require_robot(robot_id)
        if robot_id != self.active_robot_id:
            raise ControlStateError(f'{robot_id} is not the active patrol robot')
