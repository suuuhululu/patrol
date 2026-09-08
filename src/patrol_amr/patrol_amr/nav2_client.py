"""Shared Nav2 NavigateToPose client and the AMR-16 retry policy.

The control server never calls Nav2 directly.  A future mission supervisor
owns this client, supplies measured map goals and spins the ROS node.  No
server or result timeout is invented here: those values remain contract
inputs.  A failed goal gets three retries (four attempts in total).
"""

from dataclasses import dataclass
from enum import Enum
import math
from typing import Callable, Optional

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient


MAX_GOAL_RETRIES = 3


class FailureDecision(str, Enum):
    RETRY = 'retry'
    SKIP_WAYPOINT = 'skip_waypoint'
    FAIL_ROUTE = 'fail_route'


class GoalDisposition(str, Enum):
    SUCCEEDED = 'succeeded'
    SKIPPED = 'skipped'
    FAILED = 'failed'
    CANCELED = 'canceled'


@dataclass(frozen=True)
class NavigationGoal:
    goal_id: str
    x: float
    y: float
    yaw_deg: float
    is_final: bool = False
    frame_id: str = 'map'

    def __post_init__(self):
        if not isinstance(self.goal_id, str) or not self.goal_id:
            raise ValueError('goal_id must be a non-empty str')
        if self.frame_id != 'map':
            raise ValueError('Nav2 patrol goals must use the map frame')
        for name, value in (
            ('x', self.x), ('y', self.y), ('yaw_deg', self.yaw_deg)
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f'{name} must be a finite number')
            if not math.isfinite(value):
                raise ValueError(f'{name} must be a finite number')
        if not 0.0 <= self.yaw_deg < 360.0:
            raise ValueError('yaw_deg must be in [0, 360)')
        if not isinstance(self.is_final, bool):
            raise ValueError('is_final must be bool')


@dataclass(frozen=True)
class NavigationFeedback:
    goal_id: str
    attempt: int
    distance_remaining: float
    navigation_time_seconds: float
    estimated_time_remaining_seconds: float
    number_of_recoveries: int


@dataclass(frozen=True)
class NavigationCompletion:
    goal_id: str
    disposition: GoalDisposition
    attempts: int
    action_status: int
    error_code: int = 0
    error_message: str = ''


def failure_decision(
    attempts_started: int,
    is_final: bool,
    max_retries: int = MAX_GOAL_RETRIES,
) -> FailureDecision:
    """Return the action after a failed attempt.

    ``max_retries=3`` means attempts 1, 2 and 3 may each cause another
    attempt.  Failure of attempt 4 is terminal.
    """
    if (
        isinstance(attempts_started, bool)
        or not isinstance(attempts_started, int)
        or attempts_started < 1
    ):
        raise ValueError('attempts_started must be a positive int')
    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise ValueError('max_retries must be a non-negative int')
    if max_retries < 0:
        raise ValueError('max_retries must be a non-negative int')
    if not isinstance(is_final, bool):
        raise ValueError('is_final must be bool')
    if attempts_started <= max_retries:
        return FailureDecision.RETRY
    if is_final:
        return FailureDecision.FAIL_ROUTE
    return FailureDecision.SKIP_WAYPOINT


def pose_stamped(goal: NavigationGoal, stamp) -> PoseStamped:
    """Convert a validated map goal to the standard Nav2 pose message."""
    if not isinstance(goal, NavigationGoal):
        raise ValueError('goal must be a NavigationGoal')
    half_yaw = math.radians(goal.yaw_deg) / 2.0
    message = PoseStamped()
    message.header.frame_id = goal.frame_id
    message.header.stamp = stamp
    message.pose.position.x = float(goal.x)
    message.pose.position.y = float(goal.y)
    message.pose.orientation.z = math.sin(half_yaw)
    message.pose.orientation.w = math.cos(half_yaw)
    return message


class Nav2Client:
    """One-active-goal asynchronous Nav2 client with deterministic retries."""

    def __init__(self, node, action_name='navigate_to_pose', action_client=None):
        if not isinstance(action_name, str) or not action_name:
            raise ValueError('action_name must be a non-empty str')
        self._node = node
        self._action_client = action_client or ActionClient(
            node, NavigateToPose, action_name
        )
        self._goal: Optional[NavigationGoal] = None
        self._goal_handle = None
        self._attempts_started = 0
        self._feedback_callback = None
        self._completion_callback = None
        self._cancel_requested = False
        self._generation = 0

    @property
    def active(self):
        return self._goal is not None

    @property
    def attempts_started(self):
        return self._attempts_started

    def server_is_ready(self):
        return self._action_client.server_is_ready()

    def wait_for_server(self, timeout_sec):
        """Wait only for a caller-supplied duration; no default is guessed."""
        if isinstance(timeout_sec, bool) or not isinstance(
            timeout_sec, (int, float)
        ):
            raise ValueError('timeout_sec must be a non-negative number')
        if not math.isfinite(timeout_sec) or timeout_sec < 0.0:
            raise ValueError('timeout_sec must be a non-negative number')
        return self._action_client.wait_for_server(timeout_sec=float(timeout_sec))

    def execute(
        self,
        goal: NavigationGoal,
        completion_callback: Callable[[NavigationCompletion], None],
        feedback_callback: Optional[Callable[[NavigationFeedback], None]] = None,
    ):
        if not isinstance(goal, NavigationGoal):
            raise ValueError('goal must be a NavigationGoal')
        if not callable(completion_callback):
            raise ValueError('completion_callback must be callable')
        if feedback_callback is not None and not callable(feedback_callback):
            raise ValueError('feedback_callback must be callable or None')
        if self.active:
            raise RuntimeError('a Nav2 goal is already active')
        if not self.server_is_ready():
            raise RuntimeError('NavigateToPose action server is not ready')

        self._generation += 1
        self._goal = goal
        self._goal_handle = None
        self._attempts_started = 0
        self._completion_callback = completion_callback
        self._feedback_callback = feedback_callback
        self._cancel_requested = False
        self._send_attempt(self._generation)

    def cancel_active(self):
        """Request cancellation; cancellation never enters the retry path."""
        if not self.active:
            return None
        self._cancel_requested = True
        if self._goal_handle is None:
            return None
        return self._goal_handle.cancel_goal_async()

    def _send_attempt(self, generation):
        if generation != self._generation or not self.active:
            return
        self._attempts_started += 1
        self._goal_handle = None
        action_goal = NavigateToPose.Goal()
        action_goal.pose = pose_stamped(
            self._goal, self._node.get_clock().now().to_msg()
        )
        future = self._action_client.send_goal_async(
            action_goal,
            feedback_callback=lambda message: self._on_feedback(
                generation, message
            ),
        )
        future.add_done_callback(
            lambda completed: self._on_goal_response(generation, completed)
        )

    def _on_goal_response(self, generation, future):
        if generation != self._generation or not self.active:
            return
        try:
            handle = future.result()
        except Exception as error:  # rclpy future transports its exception here
            self._failed(generation, GoalStatus.STATUS_UNKNOWN, 0, str(error))
            return
        if not handle.accepted:
            self._failed(
                generation,
                GoalStatus.STATUS_UNKNOWN,
                0,
                'NavigateToPose goal rejected',
            )
            return
        self._goal_handle = handle
        result_future = handle.get_result_async()
        result_future.add_done_callback(
            lambda completed: self._on_result(generation, completed)
        )
        if self._cancel_requested:
            handle.cancel_goal_async()

    def _on_feedback(self, generation, wrapped_feedback):
        if (
            generation != self._generation
            or not self.active
            or self._feedback_callback is None
        ):
            return
        feedback = wrapped_feedback.feedback
        self._feedback_callback(NavigationFeedback(
            goal_id=self._goal.goal_id,
            attempt=self._attempts_started,
            distance_remaining=float(feedback.distance_remaining),
            navigation_time_seconds=_duration_seconds(feedback.navigation_time),
            estimated_time_remaining_seconds=_duration_seconds(
                feedback.estimated_time_remaining
            ),
            number_of_recoveries=int(feedback.number_of_recoveries),
        ))

    def _on_result(self, generation, future):
        if generation != self._generation or not self.active:
            return
        try:
            wrapped = future.result()
            status = int(wrapped.status)
            result = wrapped.result
            error_code = int(getattr(result, 'error_code', 0))
            error_message = str(getattr(result, 'error_msg', ''))
        except Exception as error:
            self._failed(generation, GoalStatus.STATUS_UNKNOWN, 0, str(error))
            return

        if status == GoalStatus.STATUS_SUCCEEDED:
            self._finish(
                GoalDisposition.SUCCEEDED, status, error_code, error_message
            )
            return
        if status == GoalStatus.STATUS_CANCELED or self._cancel_requested:
            self._finish(
                GoalDisposition.CANCELED, status, error_code, error_message
            )
            return
        self._failed(generation, status, error_code, error_message)

    def _failed(self, generation, status, error_code, error_message):
        if self._cancel_requested:
            self._finish(
                GoalDisposition.CANCELED, status, error_code, error_message
            )
            return
        decision = failure_decision(
            self._attempts_started, self._goal.is_final
        )
        if decision is FailureDecision.RETRY:
            self._send_attempt(generation)
            return
        disposition = (
            GoalDisposition.FAILED
            if decision is FailureDecision.FAIL_ROUTE
            else GoalDisposition.SKIPPED
        )
        self._finish(disposition, status, error_code, error_message)

    def _finish(self, disposition, status, error_code, error_message):
        completion = NavigationCompletion(
            goal_id=self._goal.goal_id,
            disposition=disposition,
            attempts=self._attempts_started,
            action_status=status,
            error_code=error_code,
            error_message=error_message,
        )
        callback = self._completion_callback
        self._goal = None
        self._goal_handle = None
        self._feedback_callback = None
        self._completion_callback = None
        self._cancel_requested = False
        callback(completion)


def _duration_seconds(duration):
    return float(duration.sec) + float(duration.nanosec) / 1_000_000_000.0
