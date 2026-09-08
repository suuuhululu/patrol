"""Common ordered waypoint execution on top of :mod:`nav2_client`.

This module owns only route order.  It does not decide mission state,
waypoint scan policy, STOP/CANCEL persistence, or PatrolReport contents;
those remain inputs from the future mission supervisor and TBD-AMR-005.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Sequence, Tuple

from action_msgs.msg import GoalStatus

from patrol_amr.nav2_client import (
    GoalDisposition,
    NavigationCompletion,
    NavigationFeedback,
    NavigationGoal,
)
from patrol_amr.waypoint_catalog import WaypointCatalog


class RouteDisposition(str, Enum):
    COMPLETED = 'completed'
    COMPLETED_WITH_SKIPS = 'completed_with_skips'
    FAILED = 'failed'
    CANCELED = 'canceled'


@dataclass(frozen=True)
class RouteCompletion:
    disposition: RouteDisposition
    outcomes: Tuple[NavigationCompletion, ...]

    @property
    def succeeded_goal_ids(self):
        return tuple(
            outcome.goal_id
            for outcome in self.outcomes
            if outcome.disposition is GoalDisposition.SUCCEEDED
        )

    @property
    def skipped_goal_ids(self):
        return tuple(
            outcome.goal_id
            for outcome in self.outcomes
            if outcome.disposition is GoalDisposition.SKIPPED
        )

    @property
    def terminal_goal_id(self):
        if not self.outcomes:
            return ''
        return self.outcomes[-1].goal_id


def navigation_goals(catalog: WaypointCatalog) -> Tuple[NavigationGoal, ...]:
    """Convert a measured catalog to route goals and mark only the last final."""
    if not isinstance(catalog, WaypointCatalog):
        raise ValueError('catalog must be a WaypointCatalog')
    if catalog.frame_id != 'map' or not catalog.waypoints:
        raise ValueError('catalog must contain map-frame waypoints')

    goals = []
    final_index = len(catalog.waypoints) - 1
    for index, waypoint in enumerate(catalog.waypoints):
        goals.append(NavigationGoal(
            goal_id=waypoint.waypoint_id,
            x=waypoint.x,
            y=waypoint.y,
            yaw_deg=waypoint.yaw_deg,
            is_final=index == final_index,
            frame_id=catalog.frame_id,
        ))
    return tuple(goals)


class WaypointRouteExecutor:
    """Run one ordered route and advance only from completed callbacks."""

    def __init__(self, nav2_client):
        for name in ('execute', 'cancel_active'):
            if not callable(getattr(nav2_client, name, None)):
                raise ValueError(
                    f'nav2_client must provide callable {name}()'
                )
        self._nav2_client = nav2_client
        self._goals = ()
        self._index = 0
        self._outcomes = []
        self._completion_callback = None
        self._feedback_callback = None
        self._generation = 0

    @property
    def active(self):
        return self._completion_callback is not None

    @property
    def current_goal(self):
        if not self.active:
            return None
        return self._goals[self._index]

    @property
    def outcomes(self):
        return tuple(self._outcomes)

    def start(
        self,
        goals: Sequence[NavigationGoal],
        completion_callback: Callable[[RouteCompletion], None],
        feedback_callback: Optional[Callable[[NavigationFeedback], None]] = None,
    ):
        if self.active:
            raise RuntimeError('a waypoint route is already active')
        normalized = _normalize_goals(goals)
        if not callable(completion_callback):
            raise ValueError('completion_callback must be callable')
        if feedback_callback is not None and not callable(feedback_callback):
            raise ValueError('feedback_callback must be callable or None')

        self._generation += 1
        self._goals = normalized
        self._index = 0
        self._outcomes = []
        self._completion_callback = completion_callback
        self._feedback_callback = feedback_callback
        self._dispatch_current(self._generation)

    def cancel(self):
        """Cancel the active Nav2 goal; completion arrives asynchronously."""
        if not self.active:
            return None
        return self._nav2_client.cancel_active()

    def _dispatch_current(self, generation):
        goal = self._goals[self._index]
        index = self._index
        try:
            self._nav2_client.execute(
                goal,
                lambda completion: self._on_goal_completed(
                    generation, index, completion
                ),
                self._feedback_callback,
            )
        except Exception as error:
            self._outcomes.append(NavigationCompletion(
                goal_id=goal.goal_id,
                disposition=GoalDisposition.FAILED,
                attempts=0,
                action_status=GoalStatus.STATUS_UNKNOWN,
                error_message=str(error),
            ))
            self._finish(RouteDisposition.FAILED)

    def _on_goal_completed(self, generation, index, completion):
        if (
            generation != self._generation
            or not self.active
            or index != self._index
        ):
            return
        goal = self._goals[index]
        if (
            not isinstance(completion, NavigationCompletion)
            or completion.goal_id != goal.goal_id
        ):
            self._outcomes.append(NavigationCompletion(
                goal_id=goal.goal_id,
                disposition=GoalDisposition.FAILED,
                attempts=0,
                action_status=GoalStatus.STATUS_UNKNOWN,
                error_message='Nav2 completion did not match the active goal',
            ))
            self._finish(RouteDisposition.FAILED)
            return

        self._outcomes.append(completion)
        if completion.disposition is GoalDisposition.CANCELED:
            self._finish(RouteDisposition.CANCELED)
            return
        if completion.disposition is GoalDisposition.FAILED:
            self._finish(RouteDisposition.FAILED)
            return

        final = index == len(self._goals) - 1
        if final:
            if completion.disposition is not GoalDisposition.SUCCEEDED:
                self._finish(RouteDisposition.FAILED)
                return
            disposition = (
                RouteDisposition.COMPLETED_WITH_SKIPS
                if any(
                    outcome.disposition is GoalDisposition.SKIPPED
                    for outcome in self._outcomes
                )
                else RouteDisposition.COMPLETED
            )
            self._finish(disposition)
            return

        if completion.disposition not in (
            GoalDisposition.SUCCEEDED,
            GoalDisposition.SKIPPED,
        ):
            self._finish(RouteDisposition.FAILED)
            return
        self._index += 1
        self._dispatch_current(generation)

    def _finish(self, disposition):
        completion = RouteCompletion(disposition, tuple(self._outcomes))
        callback = self._completion_callback
        self._goals = ()
        self._index = 0
        self._outcomes = []
        self._completion_callback = None
        self._feedback_callback = None
        callback(completion)


def _normalize_goals(goals):
    if isinstance(goals, (str, bytes)):
        raise ValueError('goals must be a non-empty sequence')
    try:
        supplied = tuple(goals)
    except TypeError as error:
        raise ValueError('goals must be a non-empty sequence') from error
    if not supplied:
        raise ValueError('goals must be a non-empty sequence')
    if any(not isinstance(goal, NavigationGoal) for goal in supplied):
        raise ValueError('every route goal must be a NavigationGoal')
    identifiers = tuple(goal.goal_id for goal in supplied)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('route goal IDs must be unique')

    final_index = len(supplied) - 1
    return tuple(
        NavigationGoal(
            goal_id=goal.goal_id,
            x=goal.x,
            y=goal.y,
            yaw_deg=goal.yaw_deg,
            is_final=index == final_index,
            frame_id=goal.frame_id,
        )
        for index, goal in enumerate(supplied)
    )
