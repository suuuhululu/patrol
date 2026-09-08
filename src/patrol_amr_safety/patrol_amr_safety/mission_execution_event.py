"""Validate MissionExecutionEvent without coupling policy to a ROS callback."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import json

from patrol_amr import patrol_report


UINT8_MAX = 0xFF
UINT32_MAX = 0xFFFFFFFF
UINT64_MAX = 0xFFFFFFFFFFFFFFFF
ROBOT_IDS = ('robot1', 'robot6')


class EventType(IntEnum):
    ADMITTED = 1
    REJECTED = 2
    STARTED = 3
    NONTERMINAL_STORED = 4
    RESULT_STORED = 5


@dataclass(frozen=True)
class ExecutionEvent:
    command_id: str
    mission_id: str
    robot_id: str
    event_type: EventType
    source_session_id: str
    sequence: int
    mission_state: int
    reason_code: int
    reason: str
    report: patrol_report.PatrolReportRecord | None

    @property
    def report_id(self) -> str:
        return '' if self.report is None else self.report.report_id


def from_message(message) -> ExecutionEvent:
    """Validate IDs, scalar ranges, event/report shape, and report identity."""
    command_id = _nonempty(message.command_id, 'command_id')
    mission_id = _string(message.mission_id, 'mission_id')
    robot_id = _string(message.robot_id, 'robot_id')
    if robot_id not in ROBOT_IDS:
        raise ValueError(f'robot_id must be one of {ROBOT_IDS}')
    try:
        event_type = EventType(message.event_type)
    except (TypeError, ValueError) as error:
        raise ValueError('event_type must be a known MissionExecutionEvent') from error
    source_session_id = _nonempty(
        message.source_session_id, 'source_session_id')
    sequence = _uint(message.sequence, UINT64_MAX, 'sequence')
    mission_state = _uint(message.mission_state, UINT8_MAX, 'mission_state')
    reason_code = _uint(message.reason_code, UINT32_MAX, 'reason_code')
    reason = _string(message.reason, 'reason')

    has_report = message.has_report
    if not isinstance(has_report, bool):
        raise ValueError('has_report must be a bool')
    if event_type is EventType.RESULT_STORED and not has_report:
        raise ValueError('RESULT_STORED requires has_report=true')
    if event_type is not EventType.RESULT_STORED and has_report:
        raise ValueError('only RESULT_STORED may include a report')
    if event_type is EventType.REJECTED and (
        reason_code == 0 or not reason
    ):
        raise ValueError('REJECTED requires reason_code and reason')

    report = _report_from_message(message.report) if has_report else None
    if report is not None and (
        report.command_id != command_id
        or report.mission_id != mission_id
        or report.robot_id != robot_id
    ):
        raise ValueError('report identity must match execution event')

    return ExecutionEvent(
        command_id=command_id,
        mission_id=mission_id,
        robot_id=robot_id,
        event_type=event_type,
        source_session_id=source_session_id,
        sequence=sequence,
        mission_state=mission_state,
        reason_code=reason_code,
        reason=reason,
        report=report,
    )


def _report_from_message(message) -> patrol_report.PatrolReportRecord:
    payload = {
        'report_id': message.report_id,
        'robot_id': message.robot_id,
        'source_session_id': message.source_session_id,
        'command_id': message.command_id,
        'mission_id': message.mission_id,
        'result': message.result,
        'reason_code': message.reason_code,
        'reason': message.reason,
        'started_at': {
            'sec': message.started_at.sec,
            'nanosec': message.started_at.nanosec,
        },
        'finished_at': {
            'sec': message.finished_at.sec,
            'nanosec': message.finished_at.nanosec,
        },
        'final_waypoint_id': message.final_waypoint_id,
        'related_event_ids': list(message.related_event_ids),
    }
    return patrol_report.record_from_json(json.dumps(payload))


def _string(value, name) -> str:
    if not isinstance(value, str):
        raise ValueError(f'{name} must be a str')
    return value


def _nonempty(value, name) -> str:
    value = _string(value, name)
    if not value:
        raise ValueError(f'{name} must not be empty')
    return value


def _uint(value, maximum, name) -> int:
    if (
        isinstance(value, bool) or not isinstance(value, int)
        or not 0 <= value <= maximum
    ):
        raise ValueError(f'{name} is outside its unsigned integer range')
    return value
