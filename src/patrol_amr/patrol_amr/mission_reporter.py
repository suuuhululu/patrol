"""
ROS-independent terminal mission reporting domain rules.

The public PatrolReport fields are fixed. The internal-to-ROS delivery path,
persistent retry queue, and status reporter process boundary remain separate
integration work.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
from typing import Callable

from patrol_amr.mission_types import (
    MissionOutcome, MissionRequest, MissionType)


class ReportResult(Enum):
    """Result of one internal report submission."""

    PUBLISHED = 'published'
    DUPLICATE = 'duplicate'
    NOT_REPORTABLE = 'not_reportable'


class ReportPublishError(RuntimeError):
    """The configured report sink failed to accept a completion."""


@dataclass(frozen=True)
class MissionCompletion:
    """Stable mission result before conversion to a public ROS message."""

    command_id: str
    mission_id: str
    robot_id: str
    command: MissionType
    target_id: str
    outcome: MissionOutcome
    reason: str
    reason_code: int
    started_at_ns: int
    finished_at_ns: int
    final_waypoint_id: str
    related_event_ids: tuple[str, ...]


ReportSink = Callable[[MissionCompletion], None]


class MissionReporter:
    """Validate and publish at most one completion per command in a process."""

    def __init__(self, sink: ReportSink) -> None:
        """Create a reporter that forwards completions to ``sink``."""
        if not callable(sink):
            raise TypeError('report sink must be callable')
        self._sink = sink
        self._lock = threading.Lock()
        self._in_flight: set[str] = set()
        self._published: set[str] = set()

    def report(
        self,
        request: MissionRequest,
        outcome: str,
        reason: str = '',
        *,
        reason_code: int = 0,
        started_at_ns: int = 0,
        finished_at_ns: int = 0,
        final_waypoint_id: str = '',
        related_event_ids=(),
    ) -> ReportResult:
        """Validate and deliver one completion to a durable report sink."""
        completion = self._to_completion(
            request,
            outcome,
            reason,
            reason_code,
            started_at_ns,
            finished_at_ns,
            final_waypoint_id,
            related_event_ids,
        )
        if completion is None:
            return ReportResult.NOT_REPORTABLE

        command_id = completion.command_id
        with self._lock:
            if command_id in self._in_flight or command_id in self._published:
                return ReportResult.DUPLICATE
            self._in_flight.add(command_id)

        try:
            self._sink(completion)
        except Exception as exc:
            with self._lock:
                self._in_flight.discard(command_id)
            raise ReportPublishError(
                f'report sink failed for command {command_id}') from exc

        with self._lock:
            self._in_flight.discard(command_id)
            self._published.add(command_id)
        return ReportResult.PUBLISHED

    def was_published(self, command_id: str) -> bool:
        """Return whether this process successfully delivered the command."""
        with self._lock:
            return command_id in self._published

    @staticmethod
    def _to_completion(
        request: MissionRequest,
        outcome: str,
        reason: str,
        reason_code: int,
        started_at_ns: int,
        finished_at_ns: int,
        final_waypoint_id: str,
        related_event_ids,
    ) -> MissionCompletion | None:
        if not request.command_id:
            raise ValueError('command_id is required')
        if (
            outcome in {'REJECTED', 'SUPERSEDED'}
            or request.command is MissionType.STOP
            or (
                request.command is MissionType.MOVE_TO_SAFE_ZONE
                and outcome == 'SUCCEEDED'
            )
        ):
            return None
        if not request.mission_id:
            raise ValueError('mission_id is required')
        if request.robot_id not in {'robot1', 'robot6'}:
            raise ValueError(f'unsupported robot_id: {request.robot_id}')
        try:
            normalized_outcome = MissionOutcome[outcome]
        except KeyError as exc:
            raise ValueError(f'unsupported report outcome: {outcome}') from exc
        if not isinstance(reason, str):
            raise ValueError('reason must be a str')
        if normalized_outcome in {
            MissionOutcome.FAILED,
            MissionOutcome.CANCELED,
        } and not reason.strip():
            raise ValueError(f'{outcome} report requires a reason')
        if isinstance(reason_code, bool) or not isinstance(reason_code, int):
            raise ValueError('reason_code must be an int')
        if not 0 <= reason_code <= 0xFFFFFFFF:
            raise ValueError('reason_code must fit in uint32')
        if normalized_outcome is MissionOutcome.SUCCEEDED and reason_code != 0:
            raise ValueError('SUCCEEDED report reason_code must be NONE')
        if normalized_outcome is not MissionOutcome.SUCCEEDED and reason_code == 0:
            raise ValueError(f'{outcome} report requires a nonzero reason_code')
        for name, value in (
            ('started_at_ns', started_at_ns),
            ('finished_at_ns', finished_at_ns),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f'{name} must be a non-negative int')
        if finished_at_ns < started_at_ns:
            raise ValueError('finished_at_ns must not precede started_at_ns')
        if not isinstance(final_waypoint_id, str):
            raise ValueError('final_waypoint_id must be a str')
        try:
            event_ids = tuple(related_event_ids)
        except TypeError as exc:
            raise ValueError('related_event_ids must be iterable') from exc
        if any(not isinstance(event_id, str) for event_id in event_ids):
            raise ValueError('related_event_ids entries must be strings')
        return MissionCompletion(
            command_id=request.command_id,
            mission_id=request.mission_id,
            robot_id=request.robot_id,
            command=request.command,
            target_id=request.target_id,
            outcome=normalized_outcome,
            reason=reason,
            reason_code=reason_code,
            started_at_ns=started_at_ns,
            finished_at_ns=finished_at_ns,
            final_waypoint_id=final_waypoint_id,
            related_event_ids=event_ids,
        )
