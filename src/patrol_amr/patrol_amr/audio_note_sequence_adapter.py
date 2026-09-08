"""TurtleBot4 AudioNoteSequence Action adapter for a future event node."""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading
from typing import Iterable

from builtin_interfaces.msg import Duration
from irobot_create_msgs.action import AudioNoteSequence
from irobot_create_msgs.msg import AudioNote
from rclpy.action import ActionClient


@dataclass(frozen=True)
class AudioNoteSpec:
    """One transport-independent buzzer note."""

    frequency_hz: int
    duration_s: float


def build_infinite_audio_goal(
    note_specs: Iterable[AudioNoteSpec],
) -> AudioNoteSequence.Goal:
    """Build the Action goal used for ON-until-canceled buzzer behavior."""
    specs = tuple(note_specs)
    if not specs:
        raise ValueError('at least one audio note is required')
    goal = AudioNoteSequence.Goal()
    goal.iterations = AudioNoteSequence.Goal.INFINITE
    goal.note_sequence.append = False
    goal.note_sequence.notes = [_to_audio_note(spec) for spec in specs]
    return goal


def _to_audio_note(spec: AudioNoteSpec) -> AudioNote:
    frequency = int(spec.frequency_hz)
    duration_s = float(spec.duration_s)
    if frequency <= 0 or frequency > 65535:
        raise ValueError('frequency_hz must be between 1 and 65535')
    if not math.isfinite(duration_s) or duration_s <= 0.0:
        raise ValueError('duration_s must be positive and finite')
    sec = int(duration_s)
    nanosec = round((duration_s - sec) * 1_000_000_000)
    if nanosec == 1_000_000_000:
        sec += 1
        nanosec = 0
    note = AudioNote()
    note.frequency = frequency
    note.max_runtime = Duration(sec=sec, nanosec=nanosec)
    return note


class AudioNoteSequenceAdapter:
    """Start one infinite sequence and cancel it when the alarm turns off."""

    def __init__(
        self,
        node,
        server_timeout_s: float,
        action_client_factory=ActionClient,
    ) -> None:
        if server_timeout_s < 0.0:
            raise ValueError('server_timeout_s must be non-negative')
        self._client = action_client_factory(
            node, AudioNoteSequence, 'audio_note_sequence')
        self._server_timeout_s = server_timeout_s
        self._lock = threading.Lock()
        self._pending_future = None
        self._goal_handle = None
        self._stop_requested = False

    def start(self, note_specs: Iterable[AudioNoteSpec]) -> bool:
        """Send an infinite sequence unless one is pending or active."""
        goal = build_infinite_audio_goal(note_specs)
        with self._lock:
            if self._pending_future is not None or self._goal_handle is not None:
                return False
            if not self._client.wait_for_server(
                    timeout_sec=self._server_timeout_s):
                raise RuntimeError('audio_note_sequence action is unavailable')
            self._stop_requested = False
            future = self._client.send_goal_async(goal)
            self._pending_future = future
        future.add_done_callback(self._on_goal_response)
        return True

    def stop(self) -> bool:
        """Cancel a pending or active infinite sequence once."""
        with self._lock:
            if self._pending_future is not None:
                self._stop_requested = True
                return True
            if self._goal_handle is None:
                return False
            goal_handle = self._goal_handle
            self._goal_handle = None
        goal_handle.cancel_goal_async()
        return True

    def _on_goal_response(self, future) -> None:
        goal_handle = future.result()
        with self._lock:
            self._pending_future = None
            if not goal_handle.accepted:
                self._stop_requested = False
                return
            self._goal_handle = goal_handle
            stop_requested = self._stop_requested
            self._stop_requested = False
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda result: self._on_goal_result(goal_handle))
        if stop_requested:
            self.stop()

    def _on_goal_result(self, goal_handle) -> None:
        with self._lock:
            if self._goal_handle is goal_handle:
                self._goal_handle = None
