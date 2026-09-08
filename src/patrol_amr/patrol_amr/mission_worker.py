"""Single mission worker that owns all navigation side effects."""

from __future__ import annotations

from queue import Empty
import threading
import time

from patrol_amr.mission_command_store import (
    ClaimResult, CommandStore, StoreError)
from patrol_amr.mission_arbiter import MissionArbiter
from patrol_amr.mission_config import MissionConfig
from patrol_amr.mission_controller import MissionController
from patrol_amr.mission_reporter import MissionReporter, ReportPublishError
from patrol_amr.mission_state import MissionStateTracker
from patrol_amr.mission_types import MissionRequest, MissionType
from patrol_amr.navigation_adapter import NavigationAdapter
from patrol_amr.patrol_report_reason import INTERNAL_ERROR


class MissionWorker:
    """Claim, execute, and finish commands outside ROS callbacks."""

    def __init__(
        self,
        config: MissionConfig,
        namespace: str,
        store: CommandStore,
        arbiter: MissionArbiter,
        state: MissionStateTracker,
        logger,
        keep_running,
        motion_ready=lambda: True,
        navigation_factory=NavigationAdapter,
        reporter: MissionReporter | None = None,
        state_sink=None,
        now_ns=time.time_ns,
    ) -> None:
        self._config = config
        self._namespace = namespace
        self._store = store
        self._arbiter = arbiter
        self._state = state
        self._logger = logger
        self._keep_running = keep_running
        self._motion_ready = motion_ready
        self._navigation_factory = navigation_factory
        self._reporter = reporter
        self._state_sink = state_sink
        self._now_ns = now_ns
        self._navigation = None
        self._controller = None
        self._thread = threading.Thread(
            target=self._run,
            name=f'{config.robot_id}-mission-worker',
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        self._initialize_navigation()
        while self._keep_running():
            try:
                request = self._arbiter.next_request(0.2)
            except Empty:
                continue
            if request is None:
                return
            self._arbiter.begin(request)
            try:
                self._execute(request)
            finally:
                self._arbiter.finish(request)

    def _initialize_navigation(self) -> None:
        if not self._config.initialize_navigation:
            return
        try:
            self._navigation = self._navigation_factory(
                self._namespace, self._motion_ready)
            self._navigation.wait_until_active()
            self._controller = MissionController(
                self._navigation,
                self._store,
                self._config.waypoints,
                self._config.waypoint_dwell_s,
                self._config.resume_policy,
                self._on_state_change,
                self._config.dock_timeout_s,
                self._config.dock_sensor_stable_s,
            )
            self._logger.info('navigation initialized; mission worker ready')
        except Exception as exc:  # initialization failure must fail closed
            self._arbiter.disable_motion('NAVIGATION_INITIALIZATION_FAILED')
            self._logger.fatal(
                f'navigation initialization failed; motion disabled: {exc!r}')

    def _execute(self, request: MissionRequest) -> None:
        interrupt = request.command in {MissionType.STOP, MissionType.CANCEL}
        try:
            claim = self._store.claim(
                request.command_id, request.fingerprint())
            if claim.result is ClaimResult.DUPLICATE:
                self._logger.info(
                    f'duplicate command ignored: {request.command_id}')
                return
            if claim.result is ClaimResult.CONFLICT:
                self._logger.error(
                    f'command ID content conflict: {request.command_id}')
                return
        except StoreError as exc:
            self._arbiter.disable_motion('COMMAND_DURABILITY_FAILED')
            self._logger.fatal(
                f'command durability failed; motion disabled: {exc}')
            return

        started_at_ns = self._now_ns()
        try:
            if not interrupt:
                self._state.command_started(
                    request.command_id, request.mission_id)
                self._persist_state()

            if self._controller is None:
                outcome, reason, reason_code = (
                    'REJECTED', 'SAFETY_PATH_NOT_READY', 0)
            else:
                result = self._controller.execute(
                    request, self._arbiter.cancel_event)
                outcome, reason, reason_code = (
                    result.outcome, result.reason, result.reason_code)
        except Exception as exc:
            self._arbiter.disable_motion('COMMAND_EXECUTION_FAILED')
            outcome = 'FAILED'
            reason = f'INTERNAL_ERROR:{type(exc).__name__}'
            reason_code = INTERNAL_ERROR
            self._logger.fatal(
                f'command execution failed; motion disabled: {exc!r}')

        finished_at_ns = self._now_ns()
        report_error = self._report_completion(
            request,
            outcome,
            reason,
            reason_code,
            started_at_ns,
            finished_at_ns,
            self._final_waypoint_id(),
        )
        command_store_error = None
        try:
            self._store.finish(request.command_id, outcome, reason)
        except StoreError as exc:
            command_store_error = exc
            self._arbiter.disable_motion('COMMAND_DURABILITY_FAILED')
            self._logger.fatal(
                f'command durability failed; motion disabled: {exc}')

        state_store_error = None
        if not interrupt:
            self._state.command_finished(outcome, reason, reason_code)
            try:
                self._persist_state()
            except Exception as exc:
                state_store_error = exc
                self._arbiter.disable_motion('STATUS_DURABILITY_FAILED')
                self._logger.fatal(
                    'mission status durability failed; motion disabled: '
                    f'{exc}')

        if report_error is not None:
            self._arbiter.disable_motion('REPORT_DURABILITY_FAILED')
            self._logger.fatal(
                'PatrolReport durability failed; motion disabled: '
                f'{report_error}')

        log = (self._logger.info if outcome == 'SUCCEEDED'
               else self._logger.error)
        log(f'command {request.command_id}: {outcome} {reason}')
        if command_store_error is not None or state_store_error is not None:
            return

    def _on_state_change(self, mission: str, waypoint_index: int) -> None:
        self._state.transition(mission, waypoint_index)
        self._persist_state()
        waypoint = '' if waypoint_index < 0 else f' W{waypoint_index + 1}'
        self._logger.info(f'{mission}{waypoint}')

    def _persist_state(self) -> None:
        if self._state_sink is not None:
            self._state_sink(self._state.snapshot())

    def _final_waypoint_id(self) -> str:
        index = self._state.snapshot().last_waypoint_index
        return '' if index < 0 else f'W{index + 1}'

    def _report_completion(
        self,
        request,
        outcome,
        reason,
        reason_code,
        started_at_ns,
        finished_at_ns,
        final_waypoint_id,
    ):
        if self._reporter is None:
            return None
        try:
            self._reporter.report(
                request,
                outcome,
                reason,
                reason_code=reason_code,
                started_at_ns=started_at_ns,
                finished_at_ns=finished_at_ns,
                final_waypoint_id=final_waypoint_id,
            )
        except (ReportPublishError, ValueError, TypeError) as exc:
            return exc
        return None

    def close(self) -> None:
        self._arbiter.close()
        self._thread.join(timeout=2.0)
        if self._thread.is_alive():
            self._logger.error(
                'mission worker did not stop before shutdown timeout')
        elif self._navigation is not None:
            self._navigation.destroy()
