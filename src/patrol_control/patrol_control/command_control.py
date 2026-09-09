"""
Mission command validation, identifiers, tracking, and retry policy.

This module intentionally has no ROS dependency.  The ROS node adapts messages
to these domain values, while all state transitions remain unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum
from typing import Iterable


ROBOT_IDS = frozenset({'robot1', 'robot6'})
DOCK_BY_ROBOT = {'robot1': 'dock_1', 'robot6': 'dock_6'}
PATROL_PLAN_BY_ROBOT = {
    'robot1': 'robot1_default',
    'robot6': 'robot6_default',
}
CHECK_TIMEOUT_NS = 5_000_000_000
MAX_RETRANSMISSIONS = 2


class CommandType(IntEnum):
    """MissionCommand command values from the shared contract."""

    STOP = 0
    START_PATROL = 1
    MOVE_TO_SAFE_ZONE = 2
    RESUME_PATROL = 3
    DOCK = 4
    CANCEL = 5


COMMAND_ID_NAME = {
    CommandType.STOP: 'stop',
    CommandType.START_PATROL: 'start',
    CommandType.MOVE_TO_SAFE_ZONE: 'evacuate',
    CommandType.RESUME_PATROL: 'resume',
    CommandType.DOCK: 'dock',
    CommandType.CANCEL: 'cancel',
}


class CheckState(IntEnum):
    """CommandCheck wire values."""

    UNKNOWN = 0
    ACCEPTED = 1
    EXECUTING = 2
    REJECTED = 3


class ReasonCode(IntEnum):
    """Command validation and conflict reason codes."""

    NONE = 0
    INVALID_COMMAND = 200
    INVALID_TARGET = 201
    UNSUPPORTED_COMMAND = 202
    COMMAND_ID_CONFLICT = 203
    INVALID_MISSION = 204
    INVALID_PARAMETERS = 205
    INVALID_STATE = 206


class CommandLifecycle(Enum):
    """Control-local lifecycle; WAITING is not a wire CheckState."""

    WAITING = 'waiting'
    ACCEPTED = 'accepted'
    EXECUTING = 'executing'
    REJECTED = 'rejected'
    COMPLETED = 'completed'


class TrackingDisposition(Enum):
    """Whether an incoming message changed command state."""

    APPLIED = 'applied'
    DUPLICATE = 'duplicate'
    DISCARDED = 'discarded'


class RetryActionType(Enum):
    """Timer actions emitted by the command tracker."""

    RETRANSMIT = 'retransmit'
    TIMEOUT = 'timeout'


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating one outgoing mission command."""

    accepted: bool
    reason_code: ReasonCode = ReasonCode.NONE
    detail: str = ''


@dataclass(frozen=True)
class CommandEnvelope:
    """Stable command payload used for initial publish and retransmission."""

    command_id: str
    mission_id: str
    robot_id: str
    command: CommandType
    target_id: str
    issued_by: str
    issued_at_ns: int


@dataclass
class CommandRecord:
    """Mutable control-local state for one command ID."""

    envelope: CommandEnvelope
    lifecycle: CommandLifecycle = CommandLifecycle.WAITING
    last_sent_ns: int = 0
    retransmissions: int = 0
    timeout_reported: bool = False
    report_id: str = ''
    accepted_missing: bool = False
    check_reason_code: int = 0
    check_reason: str = ''
    report_result: int | None = None
    report_reason_code: int = 0
    report_reason: str = ''


@dataclass(frozen=True)
class TrackingResult:
    """Outcome of applying one CommandCheck or PatrolReport."""

    disposition: TrackingDisposition
    lifecycle: CommandLifecycle
    warnings: tuple[str, ...] = ()
    detail: str = ''


@dataclass(frozen=True)
class RetryAction:
    """A command retransmission or terminal check-timeout notification."""

    action: RetryActionType
    envelope: CommandEnvelope
    retransmission: int


class CommandValidationError(ValueError):
    """Raised when control tries to create an invalid command."""

    def __init__(self, result: ValidationResult) -> None:
        """Preserve the structured validation result."""
        super().__init__(result.detail)
        self.result = result


def _require_empty(value: str, field_name: str) -> ValidationResult:
    if value:
        return ValidationResult(
            False,
            ReasonCode.INVALID_PARAMETERS,
            f'{field_name} must be empty for this command',
        )
    return ValidationResult(True)


def validate_command(envelope: CommandEnvelope) -> ValidationResult:
    """Validate the fixed mission/target matrix without guessing AMR TBDs."""
    if not envelope.command_id:
        return ValidationResult(
            False, ReasonCode.INVALID_PARAMETERS, 'command_id is required'
        )
    if envelope.robot_id not in ROBOT_IDS:
        return ValidationResult(
            False,
            ReasonCode.INVALID_TARGET,
            'robot_id must be robot1 or robot6',
        )
    if not envelope.issued_by:
        return ValidationResult(
            False, ReasonCode.INVALID_PARAMETERS, 'issued_by is required'
        )

    try:
        command = CommandType(envelope.command)
    except ValueError:
        return ValidationResult(
            False, ReasonCode.UNSUPPORTED_COMMAND, 'unsupported command value'
        )

    if command is CommandType.STOP:
        return _require_empty(envelope.target_id, 'target_id')

    if not envelope.mission_id:
        return ValidationResult(
            False, ReasonCode.INVALID_MISSION, 'mission_id is required'
        )

    if command is CommandType.START_PATROL:
        expected = PATROL_PLAN_BY_ROBOT[envelope.robot_id]
        if envelope.target_id != expected:
            return ValidationResult(
                False,
                ReasonCode.INVALID_TARGET,
                f'START_PATROL target_id must be {expected}',
            )
        return ValidationResult(True)

    if command is CommandType.DOCK:
        expected = DOCK_BY_ROBOT[envelope.robot_id]
        if envelope.target_id != expected:
            return ValidationResult(
                False,
                ReasonCode.INVALID_TARGET,
                f'DOCK target_id must be {expected}',
            )
        return ValidationResult(True)

    return _require_empty(envelope.target_id, 'target_id')


class CommandIdFactory:
    """Generate control session, mission, and command identifiers."""

    def __init__(self, control_session_id: str) -> None:
        """Initialize independent mission and command sequences."""
        if not control_session_id.startswith('ctrl-'):
            raise ValueError("control_session_id must start with 'ctrl-'")
        self.control_session_id = control_session_id
        self._mission_sequence = 0
        self._command_sequence = 0

    @classmethod
    def new_session(cls, now: datetime | None = None) -> 'CommandIdFactory':
        """Create a factory with a timestamp-based control session ID."""
        current = now or datetime.now().astimezone()
        session_id = 'ctrl-' + current.strftime('%Y%m%dT%H%M%S')
        return cls(session_id)

    def new_mission_id(self, robot_id: str) -> str:
        """Return the next control-wide mission identifier."""
        self._validate_robot(robot_id)
        self._mission_sequence += 1
        return (
            f'msn-{self.control_session_id}-{robot_id}-'
            f'{self._mission_sequence:04d}'
        )

    def new_command_id(self, robot_id: str, command: CommandType) -> str:
        """Return the next control-wide command identifier."""
        self._validate_robot(robot_id)
        command = CommandType(command)
        self._command_sequence += 1
        return (
            f'cmd-{self.control_session_id}-{robot_id}-'
            f'{COMMAND_ID_NAME[command]}-{self._command_sequence:04d}'
        )

    @staticmethod
    def _validate_robot(robot_id: str) -> None:
        if robot_id not in ROBOT_IDS:
            raise ValueError('robot_id must be robot1 or robot6')


class CommandControl:
    """Create outgoing commands and track their acknowledgement lifecycle."""

    def __init__(
        self,
        id_factory: CommandIdFactory,
        *,
        timeout_ns: int = CHECK_TIMEOUT_NS,
        max_retransmissions: int = MAX_RETRANSMISSIONS,
    ) -> None:
        """Configure command tracking and bounded Check retries."""
        if timeout_ns <= 0:
            raise ValueError('timeout_ns must be positive')
        if max_retransmissions < 0:
            raise ValueError('max_retransmissions must not be negative')
        self.id_factory = id_factory
        self.timeout_ns = timeout_ns
        self.max_retransmissions = max_retransmissions
        self._records: dict[str, CommandRecord] = {}
        self._report_commands: dict[str, str] = {}

    def create_command(
        self,
        *,
        robot_id: str,
        command: CommandType,
        now_ns: int,
        mission_id: str = '',
        target_id: str = '',
        issued_by: str = 'control',
    ) -> CommandEnvelope:
        """Create, validate, and register one command as initially sent."""
        try:
            command = CommandType(command)
        except ValueError as exc:
            raise CommandValidationError(
                ValidationResult(
                    False,
                    ReasonCode.UNSUPPORTED_COMMAND,
                    'unsupported command value',
                )
            ) from exc
        if robot_id not in ROBOT_IDS:
            raise CommandValidationError(
                ValidationResult(
                    False,
                    ReasonCode.INVALID_TARGET,
                    'robot_id must be robot1 or robot6',
                )
            )
        if command is CommandType.START_PATROL:
            if mission_id:
                raise CommandValidationError(
                    ValidationResult(
                        False,
                        ReasonCode.INVALID_MISSION,
                        'START_PATROL mission_id is generated by control',
                    )
                )
            mission_id = self.id_factory.new_mission_id(robot_id)
        if command is CommandType.DOCK and not mission_id:
            mission_id = self.id_factory.new_mission_id(robot_id)

        envelope = CommandEnvelope(
            command_id=self.id_factory.new_command_id(robot_id, command),
            mission_id=mission_id,
            robot_id=robot_id,
            command=command,
            target_id=target_id,
            issued_by=issued_by,
            issued_at_ns=now_ns,
        )
        result = validate_command(envelope)
        if not result.accepted:
            raise CommandValidationError(result)

        self._records[envelope.command_id] = CommandRecord(
            envelope=envelope,
            last_sent_ns=now_ns,
        )
        return envelope

    def get_record(self, command_id: str) -> CommandRecord | None:
        """Return a command record for read-only orchestration inspection."""
        return self._records.get(command_id)

    def handle_check(
        self,
        *,
        command_id: str,
        mission_id: str,
        robot_id: str,
        check_state: int,
        reason_code: int = 0,
        reason: str = '',
    ) -> TrackingResult | None:
        """
        Apply CommandCheck.

        Invalid identity and lifecycle transitions are discarded.
        """
        record = self._records.get(command_id)
        if record is None:
            return None
        mismatch = self._identity_mismatch(record, mission_id, robot_id)
        if mismatch:
            return TrackingResult(
                TrackingDisposition.DISCARDED,
                record.lifecycle,
                detail=mismatch,
            )
        try:
            incoming = CheckState(check_state)
        except ValueError:
            return TrackingResult(
                TrackingDisposition.DISCARDED,
                record.lifecycle,
                detail='undefined check_state',
            )
        if incoming is CheckState.UNKNOWN:
            return TrackingResult(
                TrackingDisposition.DISCARDED,
                record.lifecycle,
                detail='CHECK_UNKNOWN is not a valid response',
            )

        current = record.lifecycle
        if current is CommandLifecycle.WAITING:
            if incoming is CheckState.ACCEPTED:
                record.lifecycle = CommandLifecycle.ACCEPTED
                return self._applied(record)
            if incoming is CheckState.EXECUTING:
                record.lifecycle = CommandLifecycle.EXECUTING
                record.accepted_missing = True
                return self._applied(record, warnings=('ACCEPTED_MISSING',))
            record.lifecycle = CommandLifecycle.REJECTED
            record.check_reason_code = reason_code
            record.check_reason = reason
            return self._applied(record)

        expected_duplicate = {
            CommandLifecycle.ACCEPTED: CheckState.ACCEPTED,
            CommandLifecycle.EXECUTING: CheckState.EXECUTING,
            CommandLifecycle.REJECTED: CheckState.REJECTED,
        }
        if expected_duplicate.get(current) is incoming:
            return TrackingResult(
                TrackingDisposition.DUPLICATE,
                current,
            )
        if (
            current is CommandLifecycle.ACCEPTED
            and incoming is CheckState.EXECUTING
        ):
            record.lifecycle = CommandLifecycle.EXECUTING
            return self._applied(record)

        return TrackingResult(
            TrackingDisposition.DISCARDED,
            current,
            detail='backward or terminal CommandCheck transition',
        )

    def handle_report(
        self,
        *,
        report_id: str,
        command_id: str,
        mission_id: str,
        robot_id: str,
        result: int = 0,
        reason_code: int = 0,
        reason: str = '',
    ) -> TrackingResult | None:
        """
        Accept a valid final report.

        Intermediate CommandCheck loss only produces a warning.
        """
        record = self._records.get(command_id)
        if record is None:
            return None
        mismatch = self._identity_mismatch(record, mission_id, robot_id)
        if mismatch:
            return TrackingResult(
                TrackingDisposition.DISCARDED,
                record.lifecycle,
                detail=mismatch,
            )
        if not report_id:
            return TrackingResult(
                TrackingDisposition.DISCARDED,
                record.lifecycle,
                detail='report_id is required',
            )

        known_command = self._report_commands.get(report_id)
        if known_command is not None:
            if known_command == command_id:
                return TrackingResult(
                    TrackingDisposition.DUPLICATE,
                    record.lifecycle,
                )
            return TrackingResult(
                TrackingDisposition.DISCARDED,
                record.lifecycle,
                detail='report_id is already bound to another command',
            )
        if record.lifecycle is CommandLifecycle.COMPLETED:
            return TrackingResult(
                TrackingDisposition.DISCARDED,
                record.lifecycle,
                detail='command already has a different final report',
            )

        warnings: tuple[str, ...] = ()
        if record.lifecycle is not CommandLifecycle.EXECUTING:
            warnings = ('INTERMEDIATE_COMMAND_CHECK_MISSING',)
        record.lifecycle = CommandLifecycle.COMPLETED
        record.report_id = report_id
        record.report_result = result
        record.report_reason_code = reason_code
        record.report_reason = reason
        record.timeout_reported = True
        self._report_commands[report_id] = command_id
        return self._applied(record, warnings=warnings)

    def poll_retries(self, now_ns: int) -> tuple[RetryAction, ...]:
        """Return due retries and timeout without creating new IDs."""
        actions: list[RetryAction] = []
        for record in self._records.values():
            if record.lifecycle is not CommandLifecycle.WAITING:
                continue
            if record.timeout_reported:
                continue
            if now_ns - record.last_sent_ns < self.timeout_ns:
                continue
            if record.retransmissions < self.max_retransmissions:
                record.retransmissions += 1
                record.last_sent_ns = now_ns
                actions.append(
                    RetryAction(
                        RetryActionType.RETRANSMIT,
                        record.envelope,
                        record.retransmissions,
                    )
                )
                continue
            record.timeout_reported = True
            actions.append(
                RetryAction(
                    RetryActionType.TIMEOUT,
                    record.envelope,
                    record.retransmissions,
                )
            )
        return tuple(actions)

    def records(self) -> Iterable[CommandRecord]:
        """Iterate current records for diagnostics."""
        return tuple(self._records.values())

    @staticmethod
    def _identity_mismatch(
        record: CommandRecord, mission_id: str, robot_id: str
    ) -> str:
        if record.envelope.mission_id != mission_id:
            return 'mission_id does not match the sent command'
        if record.envelope.robot_id != robot_id:
            return 'robot_id does not match the sent command'
        return ''

    @staticmethod
    def _applied(
        record: CommandRecord, *, warnings: tuple[str, ...] = ()
    ) -> TrackingResult:
        return TrackingResult(
            TrackingDisposition.APPLIED,
            record.lifecycle,
            warnings=warnings,
        )
