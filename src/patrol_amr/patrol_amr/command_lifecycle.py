"""Validated internal lifecycle events from mission to command gateway."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json

from patrol_amr import patrol_report


SCHEMA_VERSION = 1


class LifecycleKind(Enum):
    """The two mission facts needed by the 2A gateway owner."""

    EXECUTING = 'executing'
    COMPLETED = 'completed'


@dataclass(frozen=True)
class CommandLifecycleEvent:
    """One idempotent internal event transported as a std_msgs/String."""

    kind: LifecycleKind
    command_id: str
    mission_id: str
    robot_id: str
    report: patrol_report.PatrolReportRecord | None = None


def executing(request) -> CommandLifecycleEvent:
    """Build an event at the point where the mission worker starts work."""
    return _validated_event(CommandLifecycleEvent(
        kind=LifecycleKind.EXECUTING,
        command_id=getattr(request, 'command_id', None),
        mission_id=getattr(request, 'mission_id', None),
        robot_id=getattr(request, 'robot_id', None),
    ))


def completed(report) -> CommandLifecycleEvent:
    """Build an event only after a terminal report has durable storage."""
    if not isinstance(report, patrol_report.PatrolReportRecord):
        raise ValueError('report must be a PatrolReportRecord')
    return _validated_event(CommandLifecycleEvent(
        kind=LifecycleKind.COMPLETED,
        command_id=report.command_id,
        mission_id=report.mission_id,
        robot_id=report.robot_id,
        report=report,
    ))


def to_json(event: CommandLifecycleEvent) -> str:
    """Serialize one event using a versioned canonical JSON envelope."""
    event = _validated_event(event)
    return json.dumps(
        {
            'schema_version': SCHEMA_VERSION,
            'kind': event.kind.value,
            'command_id': event.command_id,
            'mission_id': event.mission_id,
            'robot_id': event.robot_id,
            'report': (
                None if event.report is None
                else json.loads(patrol_report.record_to_json(event.report))
            ),
        },
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
        allow_nan=False,
    )


def from_json(value: str) -> CommandLifecycleEvent:
    """Restore and fully validate an event received from the mission node."""
    if not isinstance(value, str) or not value:
        raise ValueError('lifecycle event must be non-empty JSON text')
    try:
        payload = json.loads(value)
        if not isinstance(payload, dict) or set(payload) != {
            'schema_version', 'kind', 'command_id', 'mission_id',
            'robot_id', 'report',
        }:
            raise ValueError
        if payload['schema_version'] != SCHEMA_VERSION:
            raise ValueError
        report_payload = payload['report']
        report = (
            None if report_payload is None
            else patrol_report.record_from_json(json.dumps(
                report_payload,
                sort_keys=True,
                separators=(',', ':'),
                ensure_ascii=False,
                allow_nan=False,
            ))
        )
        return _validated_event(CommandLifecycleEvent(
            kind=LifecycleKind(payload['kind']),
            command_id=payload['command_id'],
            mission_id=payload['mission_id'],
            robot_id=payload['robot_id'],
            report=report,
        ))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError('invalid command lifecycle event') from exc


def _validated_event(event: CommandLifecycleEvent) -> CommandLifecycleEvent:
    if not isinstance(event, CommandLifecycleEvent):
        raise ValueError('event must be a CommandLifecycleEvent')
    if not isinstance(event.kind, LifecycleKind):
        raise ValueError('kind must be a LifecycleKind')
    for name, value in (
        ('command_id', event.command_id),
        ('robot_id', event.robot_id),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f'{name} must be a non-empty str')
    if not isinstance(event.mission_id, str):
        raise ValueError('mission_id must be a str')
    if event.robot_id not in {'robot1', 'robot6'}:
        raise ValueError('robot_id must be robot1 or robot6')
    if event.kind is LifecycleKind.EXECUTING:
        if event.report is not None:
            raise ValueError('EXECUTING must not contain a report')
        return event
    if not isinstance(event.report, patrol_report.PatrolReportRecord):
        raise ValueError('COMPLETED requires a report')
    if (
        event.report.command_id != event.command_id
        or event.report.mission_id != event.mission_id
        or event.report.robot_id != event.robot_id
    ):
        raise ValueError('report identity does not match lifecycle identity')
    return event
