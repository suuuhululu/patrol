"""Thread-safe admission and interruption rules for mission commands."""

from __future__ import annotations

from enum import Enum
from queue import Empty, Queue
import threading
from typing import Callable

from patrol_amr.mission_types import MissionRequest, MissionType


_COMMAND_PRIORITY = {
    MissionType.STOP: 60,
    MissionType.MOVE_TO_SAFE_ZONE: 50,
    MissionType.DOCK: 40,
    MissionType.CANCEL: 30,
    MissionType.RESUME_PATROL: 20,
    MissionType.START_PATROL: 10,
}


class SubmissionResult(Enum):
    """Reason returned to the ROS callback after non-blocking admission."""

    ACCEPTED = 'accepted'
    INVALID_STATE = 'invalid_state'
    BUSY = 'invalid_state'  # compatibility alias
    DUPLICATE = 'duplicate'
    COMMAND_ID_CONFLICT = 'command_id_conflict'
    SAFETY_NOT_READY = 'safety_not_ready'
    SHUTTING_DOWN = 'shutting_down'


class MissionArbiter:
    """Keep callbacks non-blocking while one worker owns mission execution."""

    def __init__(
        self,
        motion_ready: bool | Callable[[], bool],
        mission_snapshot: Callable[[], object] | None = None,
    ) -> None:
        self._queue: Queue[MissionRequest | None] = Queue()
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._motion_ready = (
            motion_ready if callable(motion_ready) else lambda: motion_ready)
        self._mission_snapshot = mission_snapshot
        self._motion_disabled = False
        self._motion_disabled_reason = ''
        self._external_stop = False
        self._external_stop_latched = False
        self._queued_request: MissionRequest | None = None
        self._active_request: MissionRequest | None = None
        self._superseded_command_ids: set[str] = set()
        self._preempting_command_ids: set[str] = set()
        self._live_requests: dict[str, MissionRequest] = {}
        self._closed = False

    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel_event

    def submit(self, request: MissionRequest) -> SubmissionResult:
        """Admit one command without running navigation in the callback."""
        with self._lock:
            if self._closed:
                return SubmissionResult.SHUTTING_DOWN

            duplicate = self._duplicate_result(request)
            if duplicate is not None:
                return duplicate
            if not self._admission_valid(request):
                return SubmissionResult.INVALID_STATE

            no_motion_required = request.command in {
                MissionType.STOP,
                MissionType.CANCEL,
            }
            if (
                not no_motion_required
                and (self._motion_disabled or not self._motion_ready())
            ):
                return SubmissionResult.SAFETY_NOT_READY

            incumbent = self._queued_request or self._active_request
            if incumbent is not None:
                if self.priority(request.command) <= self.priority(
                    incumbent.command
                ):
                    return SubmissionResult.INVALID_STATE
                self._superseded_command_ids.add(incumbent.command_id)
                if self._active_request is not None:
                    self._superseded_command_ids.add(
                        self._active_request.command_id)
                    self._preempting_command_ids.add(request.command_id)
                    self._cancel_event.set()

            self._queued_request = request
            self._live_requests[request.command_id] = request
            self._queue.put(request)
            return SubmissionResult.ACCEPTED

    @staticmethod
    def priority(command: MissionType) -> int:
        """Return the 2026-09-09 command-contract priority."""
        return _COMMAND_PRIORITY[command]

    def _duplicate_result(
        self,
        request: MissionRequest,
    ) -> SubmissionResult | None:
        existing = self._live_requests.get(request.command_id)
        if existing is None:
            return None
        if existing.fingerprint() == request.fingerprint():
            return SubmissionResult.DUPLICATE
        return SubmissionResult.COMMAND_ID_CONFLICT

    def _admission_valid(self, request: MissionRequest) -> bool:
        """Validate mission lifetime rules when a state provider is wired."""
        if request.command is MissionType.STOP:
            return True
        if self._mission_snapshot is None:
            return True

        snapshot = self._mission_snapshot()
        mission_id = str(getattr(snapshot, 'mission_id', ''))
        mission_state = str(getattr(snapshot, 'mission', 'MISSION_NONE'))
        if not mission_id:
            for existing in (self._queued_request, self._active_request):
                if existing is not None and existing.mission_id:
                    mission_id = existing.mission_id
                    break

        if request.command is MissionType.START_PATROL:
            return not mission_id
        if request.command is MissionType.DOCK:
            return not mission_id or request.mission_id == mission_id
        if request.command in {
            MissionType.MOVE_TO_SAFE_ZONE,
            MissionType.CANCEL,
        }:
            return bool(mission_id) and request.mission_id == mission_id
        if request.command is MissionType.RESUME_PATROL:
            return (
                request.mission_id == mission_id
                and mission_state in {
                    'MISSION_PAUSED',
                    'MISSION_WAITING_SAFE_ZONE',
                }
            )
        return False

    def next_request(self, timeout_s: float) -> MissionRequest | None:
        """Return the next item or raise queue.Empty when idle."""
        return self._queue.get(timeout=timeout_s)

    def begin(self, request: MissionRequest) -> bool:
        """Activate the winning queued request; skip stale superseded items."""
        with self._lock:
            if (
                self._queued_request is None
                or self._queued_request.command_id != request.command_id
            ):
                self._superseded_command_ids.discard(request.command_id)
                self._live_requests.pop(request.command_id, None)
                return False
            self._queued_request = None
            self._active_request = request
            if request.command_id in self._preempting_command_ids:
                self._preempting_command_ids.discard(request.command_id)
                if (
                    not self._external_stop
                    and not self._motion_disabled
                    and not self._closed
                ):
                    self._cancel_event.clear()
                    self._external_stop_latched = False
            return True

    def finish(self, request: MissionRequest) -> None:
        with self._lock:
            if (
                self._active_request is not None
                and self._active_request.command_id == request.command_id
            ):
                self._active_request = None
            self._superseded_command_ids.discard(request.command_id)
            self._preempting_command_ids.discard(request.command_id)
            self._live_requests.pop(request.command_id, None)
            self._clear_cancel_if_safe()

    def was_superseded(self, request: MissionRequest) -> bool:
        """Return whether a higher-priority command replaced this request."""
        with self._lock:
            return request.command_id in self._superseded_command_ids

    def set_external_stop(self, active: bool) -> None:
        """Latch cancellation while an external safety condition is active."""
        with self._lock:
            self._external_stop = active
            if active:
                self._external_stop_latched = True
                self._cancel_event.set()
            else:
                self._clear_cancel_if_safe()

    @property
    def external_stop_triggered(self) -> bool:
        """Return whether local safety canceled the current work item."""
        with self._lock:
            return self._external_stop_latched

    def _clear_cancel_if_safe(self) -> None:
        """Clear only after queued/active work has observed the stop."""
        if (not self._external_stop
                and self._queued_request is None
                and self._active_request is None
                and not self._motion_disabled
                and not self._closed):
            self._cancel_event.clear()
            self._external_stop_latched = False

    @property
    def motion_disabled_reason(self) -> str:
        """Return the permanent worker failure that closed motion admission."""
        with self._lock:
            return self._motion_disabled_reason

    def disable_motion(self, reason: str = 'MOTION_DISABLED') -> None:
        """Fail closed after durability or worker initialization failure."""
        with self._lock:
            self._motion_disabled = True
            self._motion_disabled_reason = reason
            self._cancel_event.set()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._cancel_event.set()
            self._queue.put(None)


__all__ = ['Empty', 'MissionArbiter', 'SubmissionResult']
