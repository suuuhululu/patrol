"""ROS-independent mission selection and scenario lifetime management."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable, Sequence

from patrol_amr.mission_command_store import CommandStore
from patrol_amr.mission_types import MissionRequest, MissionType, PoseTarget
from patrol_amr.navigation_types import NavigationResult, Waypoint
from patrol_amr.patrol_report_reason import navigation_result_reason
from patrol_amr.safe_zone_selector import select_safe_zone
from patrol_amr.scenarios.docking import dock
from patrol_amr.scenarios.interruption import interrupt_navigation
from patrol_amr.scenarios.patrol import PatrolScenario
from patrol_amr.scenarios.resume_patrol import resume_patrol
from patrol_amr.scenarios.safe_zone import move_to_safe_zone
from patrol_amr.scenarios.start_patrol import start_patrol


@dataclass(frozen=True)
class ExecutionResult:
    """Terminal command result before PatrolReport conversion."""

    outcome: str
    reason: str = ''
    reason_code: int = 0


class MissionController:
    """Select one scenario; scenario modules own their detailed steps."""

    def __init__(
        self,
        navigation,
        store: CommandStore,
        waypoints: Sequence[Waypoint],
        dwell_s: float,
        resume_policy: str,
        state_callback: Callable[[str, int], None],
        dock_timeout_s: float = 60.0,
        dock_sensor_stable_s: float = 2.0,
        safe_zone_candidates=lambda: (),
    ) -> None:
        if resume_policy not in {'disabled', 'next_waypoint', 'same_waypoint'}:
            raise ValueError(f'unsupported resume_policy: {resume_policy}')
        self._navigation = navigation
        self._store = store
        self._resume_policy = resume_policy
        self._state_callback = state_callback
        self._dock_timeout_s = dock_timeout_s
        self._dock_sensor_stable_s = dock_sensor_stable_s
        self._safe_zone_candidates = safe_zone_candidates
        self._patrol = PatrolScenario(
            navigation, store, waypoints, dwell_s, state_callback)

    def execute(
        self,
        request: MissionRequest,
        cancel_event: threading.Event,
    ) -> ExecutionResult:
        if request.command is MissionType.STOP:
            interrupt_navigation(self._navigation)
            return ExecutionResult('PAUSED')

        if request.command is MissionType.CANCEL:
            interrupt_navigation(self._navigation)
            self._store.clear_checkpoint(request.mission_id)
            return ExecutionResult('CANCELED', 'CONTROL_CANCELED', 100)

        patrol_id = request.mission_id
        if request.command is MissionType.START_PATROL:
            result, context = start_patrol(
                self._patrol,
                self._navigation,
                self._store,
                patrol_id,
                cancel_event,
                self._state_callback,
                self._dock_timeout_s,
                self._dock_sensor_stable_s,
            )
            return self._as_execution(result, context)

        if request.command is MissionType.RESUME_PATROL:
            result, context = resume_patrol(
                self._patrol,
                self._store,
                patrol_id,
                self._resume_policy,
                cancel_event,
            )
            if result is None:
                return ExecutionResult('REJECTED', context)
            return self._as_execution(result, context)

        if request.command is MissionType.MOVE_TO_SAFE_ZONE:
            decision = select_safe_zone(self._safe_zone_candidates())
            if decision.selected is None:
                return ExecutionResult(
                    'FAILED', decision.reason, decision.reason_code)
            selected = decision.selected
            self._state_callback('MISSION_MOVING_TO_SAFE_ZONE', -1)
            result = move_to_safe_zone(
                self._navigation,
                selected.candidate_id,
                PoseTarget(
                    selected.pose.frame_id,
                    selected.pose.x,
                    selected.pose.y,
                    selected.pose.yaw,
                ),
                cancel_event,
            )
            if result is NavigationResult.SUCCEEDED:
                self._state_callback('MISSION_WAITING_SAFE_ZONE', -1)
            return self._as_execution(result, 'SAFE_ZONE_NAVIGATION')

        if request.command is MissionType.DOCK:
            self._state_callback('MISSION_DOCKING', -1)
            return self._as_execution(
                dock(
                    self._navigation,
                    cancel_event,
                    self._dock_timeout_s,
                    self._dock_sensor_stable_s,
                ),
                'DOCKING',
            )
        return ExecutionResult('REJECTED', 'UNSUPPORTED_COMMAND')

    @staticmethod
    def _as_execution(
        result: NavigationResult,
        context: str,
    ) -> ExecutionResult:
        if result is NavigationResult.SUCCEEDED:
            return ExecutionResult('SUCCEEDED')
        if result is NavigationResult.CANCELED:
            reason = f'{context}_CANCELED'
            return ExecutionResult(
                'CANCELED', reason,
                navigation_result_reason('CANCELED', reason))
        if result is NavigationResult.REJECTED:
            reason = f'{context}_GOAL_REJECTED'
            return ExecutionResult(
                'FAILED', reason,
                navigation_result_reason('FAILED', reason))
        reason = f'{context}_{result.value}'
        return ExecutionResult(
            'FAILED', reason, navigation_result_reason('FAILED', reason))
