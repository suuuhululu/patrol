"""Build CommandCheck messages using the 2026-09-08 wire contract."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from patrol_amr.patrol_report import ReportTime, _validate_source_session


ROBOT_IDS = ('robot1', 'robot6')
UINT8_MAX = 0xFF
UINT32_MAX = 0xFFFFFFFF
UINT64_MAX = 0xFFFFFFFFFFFFFFFF
COMMAND_CHECK_QOS_DEPTH = 10
CHECK_UNKNOWN = 0
CHECK_ACCEPTED = 1
CHECK_EXECUTING = 2
CHECK_REJECTED = 3


class CheckMeaning(Enum):
    ACCEPTED = 'accepted'
    EXECUTING = 'executing'
    REJECTED = 'rejected'


@dataclass(frozen=True)
class CheckStateMapping:
    accepted: int = CHECK_ACCEPTED
    executing: int = CHECK_EXECUTING
    rejected: int = CHECK_REJECTED

    def __post_init__(self):
        values = (self.accepted, self.executing, self.rejected)
        for value in values:
            _uint(value, UINT8_MAX, 'check_state')
        if len(set(values)) != len(values):
            raise ValueError('check_state values must be distinct')

    def wire_value(self, meaning) -> int:
        try:
            meaning = CheckMeaning(meaning)
        except (TypeError, ValueError) as error:
            raise ValueError('meaning must be a valid CheckMeaning') from error
        return {
            CheckMeaning.ACCEPTED: self.accepted,
            CheckMeaning.EXECUTING: self.executing,
            CheckMeaning.REJECTED: self.rejected,
        }[meaning]


@dataclass(frozen=True)
class CommandCheckRecord:
    command_id: str
    mission_id: str
    robot_id: str
    meaning: CheckMeaning
    check_state: int
    reason_code: int
    reason: str
    source_session_id: str
    sequence: int


class CommandCheckFactory:
    def __init__(
        self,
        robot_id: str,
        source_session_id: str,
        mapping: CheckStateMapping,
        *,
        next_sequence: int = 1,
    ):
        if robot_id not in ROBOT_IDS:
            raise ValueError(f'robot_id must be one of {ROBOT_IDS}')
        _validate_source_session(source_session_id, robot_id=robot_id)
        if not isinstance(mapping, CheckStateMapping):
            raise ValueError('mapping must be a CheckStateMapping')
        _uint(next_sequence, UINT64_MAX, 'next_sequence', minimum=1)
        self._robot_id = robot_id
        self._source_session_id = source_session_id
        self._mapping = mapping
        self._next_sequence = next_sequence

    @property
    def next_sequence(self) -> int:
        return self._next_sequence

    def create(
        self,
        *,
        command_id: str,
        mission_id: str,
        meaning,
        reason_code: int = 0,
        reason: str = '',
    ) -> CommandCheckRecord:
        if not isinstance(command_id, str):
            raise ValueError('command_id must be a str')
        if not isinstance(mission_id, str):
            raise ValueError('mission_id must be a str')
        try:
            meaning = CheckMeaning(meaning)
        except (TypeError, ValueError) as error:
            raise ValueError('meaning must be a valid CheckMeaning') from error
        _uint(reason_code, UINT32_MAX, 'reason_code')
        if not isinstance(reason, str):
            raise ValueError('reason must be a str')
        record = CommandCheckRecord(
            command_id=command_id,
            mission_id=mission_id,
            robot_id=self._robot_id,
            meaning=meaning,
            check_state=self._mapping.wire_value(meaning),
            reason_code=reason_code,
            reason=reason,
            source_session_id=self._source_session_id,
            sequence=self._next_sequence,
        )
        if self._next_sequence == UINT64_MAX:
            raise OverflowError('CommandCheck sequence exhausted')
        self._next_sequence += 1
        return record


def populate_message(message, record, published_at: ReportTime):
    if not isinstance(record, CommandCheckRecord):
        raise ValueError('record must be a CommandCheckRecord')
    if not isinstance(published_at, ReportTime):
        raise ValueError('published_at must be a ReportTime')
    message.header.stamp.sec = published_at.sec
    message.header.stamp.nanosec = published_at.nanosec
    message.command_id = record.command_id
    message.mission_id = record.mission_id
    message.robot_id = record.robot_id
    message.check_state = record.check_state
    message.reason_code = record.reason_code
    message.reason = record.reason
    message.source_session_id = record.source_session_id
    message.sequence = record.sequence
    return message


def publish_record(publisher, message_type, record, published_at: ReportTime):
    if not hasattr(publisher, 'publish'):
        raise ValueError('publisher must provide publish(message)')
    if not callable(message_type):
        raise ValueError('message_type must be callable')
    message = populate_message(message_type(), record, published_at)
    publisher.publish(message)
    return message


def command_check_qos():
    try:
        from rclpy.qos import (
            DurabilityPolicy,
            HistoryPolicy,
            QoSProfile,
            ReliabilityPolicy,
        )
    except ImportError as error:
        raise RuntimeError('rclpy is required to build CommandCheck QoS') from error
    return QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=COMMAND_CHECK_QOS_DEPTH,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )


def _uint(value, maximum, name, *, minimum=0):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f'{name} must be in [{minimum}, {maximum}]')
    return value
