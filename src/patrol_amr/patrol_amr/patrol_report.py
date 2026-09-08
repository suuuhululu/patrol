"""Build immutable PatrolReport records from terminal mission results.

Stage 18 intentionally stops at a ROS-independent module.  The mission and
checkpoint owner has not been merged yet, so there is no trustworthy source
for command completion callbacks or timestamps and therefore no ROS publisher
is wired here.

The contracts implemented here are already fixed in ``interfaces.md``:

* one terminal report per command;
* ``rpt-<robot_session>-<report_sequence>`` IDs, with a sequence padded to at
  least four digits;
* command and mission IDs are echoed without parsing;
* FAILED and CANCELED reports require a non-NONE reason code and detail;
* retransmission reuses the same report ID.

The local persistent outbox required for reconnect/restart recovery remains an
integration responsibility.  ``next_sequence`` can be restored by that future
owner, but this module does not invent a storage path, acknowledgement, or
deletion policy.
"""

from dataclasses import dataclass
from enum import IntEnum
import json
import re
from typing import Iterable, Optional, Tuple


ROBOT_IDS = ('robot1', 'robot6')
UINT64_MAX = 0xFFFFFFFFFFFFFFFF
PATROL_REPORT_QOS_DEPTH = 20
_SOURCE_SESSION_RE = re.compile(
    r'^(robot1|robot6)-[0-9]{8}T[0-9]{6}(?:-[a-z0-9]+)*$'
)
# 노드가 parameter 단계에서 같은 규칙으로 먼저 거절할 수 있도록 공개한다.
SOURCE_SESSION_PATTERN = _SOURCE_SESSION_RE


class PatrolResult(IntEnum):
    SUCCEEDED = 0
    FAILED = 1
    CANCELED = 2


class ReasonCode(IntEnum):
    NONE = 0
    CONTROL_CANCELED = 100
    COMMAND_SUPERSEDED = 101
    SAFETY_POLICY_CANCELED = 102
    INVALID_COMMAND = 200
    INVALID_TARGET = 201
    UNSUPPORTED_COMMAND = 202
    COMMAND_ID_CONFLICT = 203
    INVALID_MISSION = 204
    INVALID_PARAMETERS = 205
    INVALID_STATE = 206
    NAV_NO_PATH = 300
    NAV_TIMEOUT = 301
    NAV_GOAL_REJECTED = 302
    NAV_GOAL_ABORTED = 303
    SAFE_ZONE_NOT_FOUND = 400
    KEEPOUT_APPLY_FAILED = 401
    KEEPOUT_ROLLBACK_FAILED = 402
    LOCALIZATION_INVALID = 500
    POSE_STALE = 501
    LIDAR_VERIFICATION_FAILED = 502
    DRIVE_TOKEN_MISSING = 600
    DRIVE_TOKEN_EXPIRED = 601
    COMMUNICATION_LOST = 602
    E_STOP_ACTIVE = 700
    OBSTACLE_BLOCKED = 701
    FIRE_DETECTED = 702
    BATTERY_LOW = 800
    BATTERY_CRITICAL = 801
    DOCKING_TIMEOUT = 900
    ROLE_HANDOFF = 901
    SENSOR_ERROR = 1000
    INTERNAL_ERROR = 1001


@dataclass(frozen=True, order=True)
class ReportTime:
    """Exact ``builtin_interfaces/Time`` value without importing ROS."""

    sec: int
    nanosec: int = 0

    def __post_init__(self):
        if isinstance(self.sec, bool) or not isinstance(self.sec, int):
            raise ValueError('time sec must be an int')
        if self.sec < 0:
            raise ValueError('time sec must not be negative')
        if isinstance(self.nanosec, bool) or not isinstance(
            self.nanosec, int
        ):
            raise ValueError('time nanosec must be an int')
        if not 0 <= self.nanosec < 1_000_000_000:
            raise ValueError('time nanosec must be in [0, 1000000000)')


@dataclass(frozen=True)
class PatrolReportRecord:
    """Validated immutable content for one terminal command report."""

    report_id: str
    robot_id: str
    source_session_id: str
    command_id: str
    mission_id: str
    result: PatrolResult
    reason_code: ReasonCode
    reason: str
    started_at: ReportTime
    finished_at: ReportTime
    final_waypoint_id: str
    related_event_ids: Tuple[str, ...]


def format_report_id(source_session_id: str, sequence: int) -> str:
    """Return the contract ID without making consumers parse it."""
    _validate_source_session(source_session_id)
    _validate_sequence(sequence)
    return f'rpt-{source_session_id}-{sequence:04d}'


def populate_message(
    message,
    record: PatrolReportRecord,
    published_at: ReportTime,
):
    """Populate a PatrolReport-compatible message without importing ROS.

    ``published_at`` is explicit because the contract does not say that the
    header stamp is identical to either terminal timestamp.  The ROS owner
    supplies its current clock value for first publication or retransmission.
    """
    if not isinstance(record, PatrolReportRecord):
        raise ValueError('record must be a PatrolReportRecord')
    if not isinstance(published_at, ReportTime):
        raise ValueError('published_at must be a ReportTime')

    message.header.stamp.sec = published_at.sec
    message.header.stamp.nanosec = published_at.nanosec
    message.report_id = record.report_id
    message.robot_id = record.robot_id
    message.source_session_id = record.source_session_id
    message.command_id = record.command_id
    message.mission_id = record.mission_id
    message.result = int(record.result)
    message.reason_code = int(record.reason_code)
    message.reason = record.reason
    message.started_at.sec = record.started_at.sec
    message.started_at.nanosec = record.started_at.nanosec
    message.finished_at.sec = record.finished_at.sec
    message.finished_at.nanosec = record.finished_at.nanosec
    message.final_waypoint_id = record.final_waypoint_id
    message.related_event_ids = list(record.related_event_ids)
    return message


def publish_record(
    publisher,
    message_type,
    record: PatrolReportRecord,
    published_at: ReportTime,
):
    """Create and publish one message through a caller-owned ROS publisher."""
    if not callable(message_type):
        raise ValueError('message_type must be callable')
    if not hasattr(publisher, 'publish') or not callable(publisher.publish):
        raise ValueError('publisher must provide publish(message)')
    message = populate_message(message_type(), record, published_at)
    publisher.publish(message)
    return message


def patrol_report_qos():
    """Return the fixed RELIABLE/VOLATILE/KEEP_LAST(20) ROS QoS profile."""
    from rclpy.qos import (
        DurabilityPolicy,
        HistoryPolicy,
        QoSProfile,
        ReliabilityPolicy,
    )

    return QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=PATROL_REPORT_QOS_DEPTH,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )


def record_to_json(record: PatrolReportRecord) -> str:
    """Serialize the immutable terminal payload for persistent replay."""
    if not isinstance(record, PatrolReportRecord):
        raise ValueError('record must be a PatrolReportRecord')
    return json.dumps(
        {
            'report_id': record.report_id,
            'robot_id': record.robot_id,
            'source_session_id': record.source_session_id,
            'command_id': record.command_id,
            'mission_id': record.mission_id,
            'result': int(record.result),
            'reason_code': int(record.reason_code),
            'reason': record.reason,
            'started_at': {
                'sec': record.started_at.sec,
                'nanosec': record.started_at.nanosec,
            },
            'finished_at': {
                'sec': record.finished_at.sec,
                'nanosec': record.finished_at.nanosec,
            },
            'final_waypoint_id': record.final_waypoint_id,
            'related_event_ids': list(record.related_event_ids),
        },
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
        allow_nan=False,
    )


def record_from_json(value: str) -> PatrolReportRecord:
    """Validate and restore one payload written by ``record_to_json``."""
    if not isinstance(value, str) or not value:
        raise ValueError('record JSON must be a non-empty str')
    try:
        payload = json.loads(value)
        if not isinstance(payload, dict):
            raise ValueError
        report_id = payload['report_id']
        robot_id = payload['robot_id']
        source_session_id = payload['source_session_id']
        prefix = f'rpt-{source_session_id}-'
        if not isinstance(report_id, str) or not report_id.startswith(prefix):
            raise ValueError
        sequence_text = report_id[len(prefix):]
        if len(sequence_text) < 4 or not sequence_text.isdigit():
            raise ValueError
        sequence = int(sequence_text)
        factory = PatrolReportFactory(
            robot_id, source_session_id, next_sequence=sequence
        )
        restored = factory.create(
            command_id=payload['command_id'],
            mission_id=payload['mission_id'],
            result=payload['result'],
            reason_code=payload['reason_code'],
            reason=payload['reason'],
            started_at=_time_from_json(payload['started_at']),
            finished_at=_time_from_json(payload['finished_at']),
            final_waypoint_id=payload['final_waypoint_id'],
            related_event_ids=payload['related_event_ids'],
        )
        if restored.report_id != report_id:
            raise ValueError
        return restored
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError('invalid PatrolReportRecord JSON') from error


class PatrolReportFactory:
    """Create one immutable report per command within one robot session.

    Repeating the exact same terminal result returns the original record.  A
    different result for the same command is rejected, preventing a retry from
    silently changing the report while retaining its command identity.
    """

    def __init__(
        self,
        robot_id: str,
        source_session_id: str,
        *,
        next_sequence: int = 1,
    ):
        if robot_id not in ROBOT_IDS:
            raise ValueError(f'robot_id must be one of {ROBOT_IDS}')
        _validate_source_session(source_session_id, robot_id=robot_id)
        _validate_sequence(next_sequence)
        self._robot_id = robot_id
        self._source_session_id = source_session_id
        self._next_sequence = next_sequence
        self._by_command = {}

    @property
    def next_sequence(self) -> int:
        """Sequence a persistent owner must store before the next restart."""
        return self._next_sequence

    def find(self, command_id: str) -> Optional[PatrolReportRecord]:
        _nonempty_string(command_id, 'command_id')
        return self._by_command.get(command_id)

    def create(
        self,
        *,
        command_id: str,
        mission_id: str,
        result,
        reason_code,
        reason: str,
        started_at: ReportTime,
        finished_at: ReportTime,
        final_waypoint_id: str = '',
        related_event_ids: Iterable[str] = (),
    ) -> PatrolReportRecord:
        """Validate a terminal result and allocate its report ID atomically."""
        command_id = _nonempty_string(command_id, 'command_id')
        mission_id = _nonempty_string(mission_id, 'mission_id')
        result = _enum_value(PatrolResult, result, 'result')
        reason_code = _enum_value(ReasonCode, reason_code, 'reason_code')
        if not isinstance(reason, str):
            raise ValueError('reason must be a str')
        if result in (PatrolResult.FAILED, PatrolResult.CANCELED):
            if reason_code is ReasonCode.NONE:
                raise ValueError(
                    'FAILED and CANCELED require a non-NONE reason_code'
                )
            if not reason:
                raise ValueError(
                    'FAILED and CANCELED require a non-empty reason'
                )
        if not isinstance(started_at, ReportTime):
            raise ValueError('started_at must be a ReportTime')
        if not isinstance(finished_at, ReportTime):
            raise ValueError('finished_at must be a ReportTime')
        if finished_at < started_at:
            raise ValueError('finished_at must not precede started_at')
        if not isinstance(final_waypoint_id, str):
            raise ValueError('final_waypoint_id must be a str')
        event_ids = _event_ids(related_event_ids)

        existing = self._by_command.get(command_id)
        report_id = (
            existing.report_id
            if existing is not None
            else format_report_id(
                self._source_session_id, self._next_sequence
            )
        )
        candidate = PatrolReportRecord(
            report_id=report_id,
            robot_id=self._robot_id,
            source_session_id=self._source_session_id,
            command_id=command_id,
            mission_id=mission_id,
            result=result,
            reason_code=reason_code,
            reason=reason,
            started_at=started_at,
            finished_at=finished_at,
            final_waypoint_id=final_waypoint_id,
            related_event_ids=event_ids,
        )

        if existing is not None:
            if candidate != existing:
                raise ValueError(
                    'command_id already has a different terminal report'
                )
            return existing

        self._by_command[command_id] = candidate
        self._next_sequence += 1
        return candidate


def _validate_source_session(
    source_session_id: str, *, robot_id: Optional[str] = None
) -> None:
    if not isinstance(source_session_id, str):
        raise ValueError('source_session_id must be a str')
    match = _SOURCE_SESSION_RE.fullmatch(source_session_id)
    if match is None:
        raise ValueError(
            'source_session_id must match '
            '<robot_id>-<YYYYMMDDTHHMMSS>[-<restart_sequence>]'
        )
    if robot_id is not None and match.group(1) != robot_id:
        raise ValueError('source_session_id must belong to robot_id')


def _validate_sequence(sequence: int) -> None:
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise ValueError('report sequence must be an int')
    if not 1 <= sequence <= UINT64_MAX:
        raise ValueError('report sequence must be in uint64 range [1, max]')


def _enum_value(enum_type, value, name):
    if isinstance(value, bool):
        raise ValueError(f'{name} must be a valid {enum_type.__name__}')
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f'{name} must be a valid {enum_type.__name__}'
        ) from error


def _nonempty_string(value, name) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f'{name} must be a non-empty str')
    return value


def _event_ids(values) -> Tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError('related_event_ids must be an iterable of strings')
    try:
        values = tuple(values)
    except TypeError as error:
        raise ValueError(
            'related_event_ids must be an iterable of strings'
        ) from error
    for value in values:
        _nonempty_string(value, 'related_event_id')
    return values


def _time_from_json(value) -> ReportTime:
    if not isinstance(value, dict) or set(value) != {'sec', 'nanosec'}:
        raise ValueError
    return ReportTime(value['sec'], value['nanosec'])
