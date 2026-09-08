"""Thread-safe admission and interruption rules for mission commands."""

from __future__ import annotations

from enum import Enum
from queue import Empty, Queue
import threading
from typing import Callable

from patrol_amr.mission_types import MissionRequest, MissionType


class SubmissionResult(Enum):
    """Reason returned to the ROS callback after non-blocking admission."""

    ACCEPTED = 'accepted'
    BUSY = 'busy'
    SAFETY_NOT_READY = 'safety_not_ready'
    SHUTTING_DOWN = 'shutting_down'


class MissionArbiter:
    """Keep callbacks non-blocking while one worker owns mission execution."""

    def __init__(self, motion_ready: bool | Callable[[], bool]) -> None:
        self._queue: Queue[MissionRequest | None] = Queue()
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._motion_ready = (
            motion_ready if callable(motion_ready) else lambda: motion_ready)
        self._motion_disabled = False
        self._motion_disabled_reason = ''
        self._external_stop = False
        self._motion_queued = False
        self._active_command_id = ''
        self._pending_interrupts = 0
        self._closed = False

    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel_event

    def submit(self, request: MissionRequest) -> SubmissionResult:
        """Admit one command without running navigation in the callback."""
        interrupt = request.command in {MissionType.STOP, MissionType.CANCEL}
        with self._lock:
            if self._closed:
                return SubmissionResult.SHUTTING_DOWN
            if interrupt:
                self._pending_interrupts += 1
                self._cancel_event.set()
                self._queue.put(request)
                return SubmissionResult.ACCEPTED
            if self._motion_disabled or not self._motion_ready():
                return SubmissionResult.SAFETY_NOT_READY
            if self._motion_queued or self._active_command_id:
                return SubmissionResult.BUSY
            self._motion_queued = True
            self._queue.put(request)
            return SubmissionResult.ACCEPTED

    def next_request(self, timeout_s: float) -> MissionRequest | None:
        """Return the next item or raise queue.Empty when idle."""
        return self._queue.get(timeout=timeout_s)

    def begin(self, request: MissionRequest) -> None:
        interrupt = request.command in {MissionType.STOP, MissionType.CANCEL}
        if interrupt:
            return
        with self._lock:
            self._motion_queued = False
            self._active_command_id = request.command_id

    def finish(self, request: MissionRequest) -> None:
        interrupt = request.command in {MissionType.STOP, MissionType.CANCEL}
        with self._lock:
            if interrupt:
                self._pending_interrupts = max(0, self._pending_interrupts - 1)
            elif self._active_command_id == request.command_id:
                self._active_command_id = ''
            self._clear_cancel_if_safe()

    def set_external_stop(self, active: bool) -> None:
        """Latch cancellation while an external safety condition is active."""
        with self._lock:
            self._external_stop = active
            if active:
                self._cancel_event.set()
            else:
                self._clear_cancel_if_safe()

    def _clear_cancel_if_safe(self) -> None:
        """Clear only after queued/active work has observed the stop."""
        if (not self._external_stop
                and not self._pending_interrupts
                and not self._motion_queued
                and not self._active_command_id
                and not self._motion_disabled
                and not self._closed):
            self._cancel_event.clear()

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
