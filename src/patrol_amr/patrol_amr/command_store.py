"""Persistent MissionCommand deduplication for AMR-05.

The store implements the fixed parts of interfaces.md Q-14:

* retain every command received in the last 24 hours;
* retain the newest 1,000 commands older than 24 hours;
* never execute the same command ID twice, including after process restart;
* treat changes to robot, command, target, target pose, or mission
  as a command-ID conflict;
* retain PENDING/admitted/executing/nonterminal/rejected/completed state;
* retain the completed report payload so the future ROS adapter can resend it.

Target pose is supplied as JSON-compatible data by the ROS adapter and is
canonicalized only for exact comparison. Legacy databases containing the
removed ``parameters_json`` column are migrated in one transaction.
"""

from dataclasses import dataclass
from enum import Enum, IntEnum
import json
import math
import sqlite3
from typing import Any, Optional


ROBOT_IDS = ('robot1', 'robot6')
RETENTION_SECONDS = 24.0 * 60.0 * 60.0
MIN_OLD_RECORDS = 1000


class MissionCommand(IntEnum):
    STOP = 0
    START_PATROL = 1
    MOVE_TO_SAFE_ZONE = 2
    RESUME_PATROL = 3
    DOCK = 4
    CANCEL = 5


class CommandState(Enum):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    EXECUTING = 'executing'
    NONTERMINAL = 'nonterminal'
    REJECTED = 'rejected'
    COMPLETED = 'completed'
    SUPERSEDED = 'superseded'


class RegisterVerdict(Enum):
    NEW = 'new'
    DUPLICATE_PENDING = 'duplicate_pending'
    DUPLICATE_ACCEPTED = 'duplicate_accepted'
    DUPLICATE_EXECUTING = 'duplicate_executing'
    DUPLICATE_NONTERMINAL = 'duplicate_nonterminal'
    DUPLICATE_REJECTED = 'duplicate_rejected'
    DUPLICATE_COMPLETED = 'duplicate_completed'
    DUPLICATE_SUPERSEDED = 'duplicate_superseded'
    COMMAND_ID_CONFLICT = 'command_id_conflict'


@dataclass(frozen=True)
class CommandObservation:
    verdict: RegisterVerdict
    state: Optional[CommandState]
    report_id: Optional[str] = None
    report_payload_json: Optional[str] = None
    received_at: float = 0.0
    reason_code: int = 0
    reason: str = ''


@dataclass(frozen=True)
class StoredCommand:
    """ROS-independent command payload retained for pending restart replay."""

    command_id: str
    mission_id: str
    robot_id: str
    command: int
    target_id: str
    target_pose: Any
    issued_by: str
    received_at: float


class CommandStore:
    """SQLite-backed command identity and terminal-report store."""

    def __init__(self, database_path: str, robot_id: str):
        if not isinstance(database_path, str) or not database_path:
            raise ValueError('database_path must be a non-empty str')
        if robot_id not in ROBOT_IDS:
            raise ValueError(f'robot_id must be one of {ROBOT_IDS}')
        self._robot_id = robot_id
        self._connection = sqlite3.connect(database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute('PRAGMA foreign_keys = ON')
        self._initialize_schema()
        self._connection.commit()

    def _initialize_schema(self) -> None:
        self._connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS mission_commands (
                command_id TEXT PRIMARY KEY,
                mission_id TEXT NOT NULL,
                robot_id TEXT NOT NULL,
                command INTEGER NOT NULL,
                target_id TEXT NOT NULL,
                target_pose_json TEXT NOT NULL,
                issued_by TEXT NOT NULL DEFAULT '',
                received_at REAL NOT NULL,
                state TEXT NOT NULL,
                report_id TEXT,
                report_payload_json TEXT,
                reason_code INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT ''
            )
            '''
        )
        columns = {
            row['name'] for row in self._connection.execute(
                'PRAGMA table_info(mission_commands)'
            ).fetchall()
        }
        if 'parameters_json' in columns:
            with self._connection:
                self._connection.execute(
                    'ALTER TABLE mission_commands RENAME TO mission_commands_v1'
                )
                self._connection.execute(
                    '''
                    CREATE TABLE mission_commands (
                        command_id TEXT PRIMARY KEY,
                        mission_id TEXT NOT NULL,
                        robot_id TEXT NOT NULL,
                        command INTEGER NOT NULL,
                        target_id TEXT NOT NULL,
                        target_pose_json TEXT NOT NULL,
                        issued_by TEXT NOT NULL DEFAULT '',
                        received_at REAL NOT NULL,
                        state TEXT NOT NULL,
                        report_id TEXT,
                        report_payload_json TEXT,
                        reason_code INTEGER NOT NULL DEFAULT 0,
                        reason TEXT NOT NULL DEFAULT ''
                    )
                    '''
                )
                self._connection.execute(
                    '''
                    INSERT INTO mission_commands (
                        command_id, mission_id, robot_id, command, target_id,
                        target_pose_json, received_at, state, report_id,
                        report_payload_json
                    )
                    SELECT command_id, mission_id, robot_id, command, target_id,
                           target_pose_json, received_at, state, report_id,
                           report_payload_json
                    FROM mission_commands_v1
                    '''
                )
                self._connection.execute('DROP TABLE mission_commands_v1')
        else:
            additions = {
                'issued_by': "TEXT NOT NULL DEFAULT ''",
                'reason_code': 'INTEGER NOT NULL DEFAULT 0',
                'reason': "TEXT NOT NULL DEFAULT ''",
            }
            with self._connection:
                for name, declaration in additions.items():
                    if name not in columns:
                        self._connection.execute(
                            f'ALTER TABLE mission_commands ADD COLUMN '
                            f'{name} {declaration}'
                        )

        self._connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS mission_execution_events (
                command_id TEXT NOT NULL,
                event_type INTEGER NOT NULL,
                report_id TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (command_id, event_type, report_id),
                FOREIGN KEY (command_id) REFERENCES mission_commands(command_id)
                    ON DELETE CASCADE
            )
            '''
        )

    def close(self) -> None:
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def register(
        self,
        *,
        command_id: str,
        mission_id: str,
        robot_id: str,
        command,
        target_id: str,
        target_pose: Any,
        received_at: float,
        issued_by: str = '',
    ) -> CommandObservation:
        """Persist a new command or classify a retry without executing it."""
        command_id = _nonempty_string(command_id, 'command_id')
        command = _command_value(command)
        if not isinstance(mission_id, str):
            raise ValueError('mission_id must be a str')
        if not mission_id and command is not MissionCommand.STOP:
            raise ValueError('mission_id may be empty only for STOP')
        if robot_id not in ROBOT_IDS:
            raise ValueError(f'robot_id must be one of {ROBOT_IDS}')
        if not isinstance(target_id, str):
            raise ValueError('target_id must be a str')
        if not isinstance(issued_by, str):
            raise ValueError('issued_by must be a str')
        target_pose_json = _canonical_json(target_pose, 'target_pose')
        received_at = _finite_nonnegative(received_at, 'received_at')

        existing = self._connection.execute(
            'SELECT * FROM mission_commands WHERE command_id = ?',
            (command_id,),
        ).fetchone()
        if existing is not None:
            return self._classify_existing(
                existing,
                mission_id=mission_id,
                robot_id=robot_id,
                command=command,
                target_id=target_id,
                target_pose_json=target_pose_json,
                issued_by=issued_by,
            )

        # A command addressed to the other robot is invalid input for this
        # store.  It is rejected before persistence so it cannot poison this
        # robot's command-ID retention set.
        if robot_id != self._robot_id:
            raise ValueError('robot_id does not match this CommandStore')

        with self._connection:
            self._connection.execute(
                '''
                INSERT INTO mission_commands (
                    command_id, mission_id, robot_id, command, target_id,
                    target_pose_json, issued_by, received_at, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    command_id,
                    mission_id,
                    robot_id,
                    int(command),
                    target_id,
                    target_pose_json,
                    issued_by,
                    received_at,
                    CommandState.PENDING.value,
                ),
            )
        return CommandObservation(
            RegisterVerdict.NEW, CommandState.PENDING,
            received_at=received_at,
        )

    def mark_accepted(self, command_id: str) -> CommandState:
        """Record mission admission; later states are never rolled back."""
        row = self._required(command_id)
        state = CommandState(row['state'])
        if state is CommandState.PENDING:
            self._set_state(command_id, CommandState.ACCEPTED)
            return CommandState.ACCEPTED
        if state in {
            CommandState.ACCEPTED, CommandState.EXECUTING,
            CommandState.NONTERMINAL, CommandState.COMPLETED,
        }:
            return state
        raise ValueError(f'{state.value} command cannot be accepted')

    def mark_rejected(
        self, command_id: str, *, reason_code: int, reason: str,
    ) -> CommandState:
        """Finish a pending admission without allowing later execution."""
        reason_code = _uint32(reason_code, 'reason_code')
        reason = _nonempty_string(reason, 'reason')
        row = self._required(command_id)
        state = CommandState(row['state'])
        if state is CommandState.REJECTED:
            if row['reason_code'] != reason_code or row['reason'] != reason:
                raise ValueError('rejected command already has another reason')
            return state
        if state is not CommandState.PENDING:
            raise ValueError(f'{state.value} command cannot be rejected')
        self._set_state(
            command_id, CommandState.REJECTED,
            reason_code=reason_code, reason=reason,
        )
        return CommandState.REJECTED

    def mark_executing(self, command_id: str) -> CommandState:
        """Move ACCEPTED to EXECUTING; exact retries are idempotent."""
        row = self._required(command_id)
        state = CommandState(row['state'])
        if state is CommandState.PENDING:
            self._set_state(command_id, CommandState.ACCEPTED)
            state = CommandState.ACCEPTED
        if state in {
            CommandState.NONTERMINAL, CommandState.REJECTED,
            CommandState.COMPLETED, CommandState.SUPERSEDED,
        }:
            raise ValueError(f'a {state.value} command cannot execute again')
        if state is CommandState.ACCEPTED:
            self._set_state(command_id, CommandState.EXECUTING)
        return CommandState.EXECUTING

    def mark_nonterminal(
        self, command_id: str, *, reason_code: int = 0, reason: str = '',
    ) -> CommandState:
        """Record PAUSED/WAITING completion without a PatrolReport."""
        reason_code = _uint32(reason_code, 'reason_code')
        if not isinstance(reason, str):
            raise ValueError('reason must be a str')
        row = self._required(command_id)
        state = CommandState(row['state'])
        if state is CommandState.NONTERMINAL:
            return state
        if state not in {
            CommandState.PENDING, CommandState.ACCEPTED,
            CommandState.EXECUTING,
        }:
            raise ValueError(f'{state.value} command cannot finish nonterminal')
        terminal_state = (
            CommandState.SUPERSEDED
            if reason_code == 101 else CommandState.NONTERMINAL
        )
        self._set_state(
            command_id, terminal_state,
            reason_code=reason_code, reason=reason,
        )
        return terminal_state

    def validate_identity(
        self,
        command_id: str,
        mission_id: str,
        robot_id: str,
    ) -> CommandState:
        """Return state only when an internal event matches the stored command."""
        row = self._required(command_id)
        if not isinstance(mission_id, str):
            raise ValueError('mission_id must be a str')
        if robot_id not in ROBOT_IDS:
            raise ValueError(f'robot_id must be one of {ROBOT_IDS}')
        if row['mission_id'] != mission_id or row['robot_id'] != robot_id:
            raise ValueError('lifecycle identity does not match stored command')
        return CommandState(row['state'])

    def complete(
        self,
        command_id: str,
        *,
        report_id: str,
        report_payload_json: str,
    ) -> CommandState:
        """Store the exact terminal report needed for duplicate retransmit."""
        report_id = _nonempty_string(report_id, 'report_id')
        report_payload_json = _json_text(
            report_payload_json, 'report_payload_json', allow_empty=False
        )
        row = self._required(command_id)
        state = CommandState(row['state'])
        if state is CommandState.COMPLETED:
            if (
                row['report_id'] == report_id
                and row['report_payload_json'] == report_payload_json
            ):
                return state
            raise ValueError(
                'completed command already has a different report'
            )

        if state in {
            CommandState.NONTERMINAL, CommandState.REJECTED,
            CommandState.SUPERSEDED,
        }:
            raise ValueError(f'a {state.value} command cannot store a report')
        with self._connection:
            self._connection.execute(
                '''
                UPDATE mission_commands
                SET state = ?, report_id = ?, report_payload_json = ?
                WHERE command_id = ?
                ''',
                (
                    CommandState.COMPLETED.value,
                    report_id,
                    report_payload_json,
                    command_id,
                ),
            )
        return CommandState.COMPLETED

    def complete_report(self, command_id: str, record) -> CommandState:
        """Persist a validated PatrolReportRecord for exact replay."""
        from patrol_amr import patrol_report

        if not isinstance(record, patrol_report.PatrolReportRecord):
            raise ValueError('record must be a PatrolReportRecord')
        if record.command_id != command_id:
            raise ValueError('record command_id must match command_id')
        if record.robot_id != self._robot_id:
            raise ValueError('record robot_id must match this CommandStore')
        self.validate_identity(
            command_id, record.mission_id, record.robot_id)
        return self.complete(
            command_id,
            report_id=record.report_id,
            report_payload_json=patrol_report.record_to_json(record),
        )

    def completed_report(self, command_id: str):
        """Restore the terminal report, or None before completion."""
        from patrol_amr import patrol_report

        row = self._required(command_id)
        if CommandState(row['state']) is not CommandState.COMPLETED:
            return None
        return patrol_report.record_from_json(row['report_payload_json'])

    def completed_reports(self):
        """Restore every retained terminal report in receive order.

        The store deliberately does not mark a report as acknowledged: the
        shared contract has no report ACK yet.  Callers may therefore replay
        these immutable records after a transport reconnection, and receivers
        deduplicate them by report ID as required by interfaces.md section 5.
        """
        from patrol_amr import patrol_report

        rows = self._connection.execute(
            '''
            SELECT report_payload_json
            FROM mission_commands
            WHERE state = ?
            ORDER BY received_at ASC, rowid ASC
            ''',
            (CommandState.COMPLETED.value,),
        ).fetchall()
        return tuple(
            patrol_report.record_from_json(row['report_payload_json'])
            for row in rows
        )

    def pending_commands(self) -> tuple[StoredCommand, ...]:
        """Return pending commands in original receive order for restart."""
        rows = self._connection.execute(
            '''
            SELECT * FROM mission_commands
            WHERE state = ?
            ORDER BY received_at ASC, rowid ASC
            ''',
            (CommandState.PENDING.value,),
        ).fetchall()
        return tuple(_stored_command(row) for row in rows)

    def record_event(
        self, command_id: str, event_type: int, report_id: str = '',
    ) -> bool:
        """Persist the contract idempotency key; return false on duplicate."""
        self._required(command_id)
        if isinstance(event_type, bool) or not isinstance(event_type, int):
            raise ValueError('event_type must be an int')
        if not 1 <= event_type <= 5:
            raise ValueError('event_type must be a known execution event')
        if not isinstance(report_id, str):
            raise ValueError('report_id must be a str')
        with self._connection:
            cursor = self._connection.execute(
                '''
                INSERT OR IGNORE INTO mission_execution_events (
                    command_id, event_type, report_id
                ) VALUES (?, ?, ?)
                ''',
                (command_id, event_type, report_id),
            )
        return cursor.rowcount == 1

    def observation(self, command_id: str) -> CommandObservation:
        row = self._required(command_id)
        return _observation_for_row(row)

    def prune(self, now: float) -> int:
        """Apply Q-14 and return the number of deleted old records."""
        now = _finite_nonnegative(now, 'now')
        cutoff = now - RETENTION_SECONDS
        before = self.count()
        with self._connection:
            self._connection.execute(
                '''
                DELETE FROM mission_commands
                WHERE received_at < ?
                  AND command_id NOT IN (
                    SELECT command_id
                    FROM mission_commands
                    WHERE received_at < ?
                    ORDER BY received_at DESC, rowid DESC
                    LIMIT ?
                  )
                ''',
                (cutoff, cutoff, MIN_OLD_RECORDS),
            )
        return before - self.count()

    def count(self) -> int:
        return int(
            self._connection.execute(
                'SELECT COUNT(*) FROM mission_commands'
            ).fetchone()[0]
        )

    def _required(self, command_id: str):
        command_id = _nonempty_string(command_id, 'command_id')
        row = self._connection.execute(
            'SELECT * FROM mission_commands WHERE command_id = ?',
            (command_id,),
        ).fetchone()
        if row is None:
            raise KeyError(command_id)
        return row

    def _set_state(
        self,
        command_id: str,
        state: CommandState,
        *,
        reason_code: int = 0,
        reason: str = '',
    ) -> None:
        if not isinstance(state, CommandState):
            raise ValueError('state must be a CommandState')
        with self._connection:
            self._connection.execute(
                '''
                UPDATE mission_commands
                SET state = ?, reason_code = ?, reason = ?
                WHERE command_id = ?
                ''',
                (state.value, reason_code, reason, command_id),
            )

    @staticmethod
    def _classify_existing(
        row,
        *,
        mission_id,
        robot_id,
        command,
        target_id,
        target_pose_json,
        issued_by,
    ) -> CommandObservation:
        fingerprint = (
            mission_id,
            robot_id,
            int(command),
            target_id,
            target_pose_json,
            issued_by,
        )
        stored = (
            row['mission_id'],
            row['robot_id'],
            row['command'],
            row['target_id'],
            row['target_pose_json'],
            row['issued_by'],
        )
        if fingerprint != stored:
            return CommandObservation(
                RegisterVerdict.COMMAND_ID_CONFLICT, None
            )
        return _observation_for_row(row)


def _observation_for_row(row) -> CommandObservation:
    state = CommandState(row['state'])
    verdict = {
        CommandState.PENDING: RegisterVerdict.DUPLICATE_PENDING,
        CommandState.ACCEPTED: RegisterVerdict.DUPLICATE_ACCEPTED,
        CommandState.EXECUTING: RegisterVerdict.DUPLICATE_EXECUTING,
        CommandState.NONTERMINAL: RegisterVerdict.DUPLICATE_NONTERMINAL,
        CommandState.REJECTED: RegisterVerdict.DUPLICATE_REJECTED,
        CommandState.COMPLETED: RegisterVerdict.DUPLICATE_COMPLETED,
        CommandState.SUPERSEDED: RegisterVerdict.DUPLICATE_SUPERSEDED,
    }[state]
    return CommandObservation(
        verdict,
        state,
        row['report_id'],
        row['report_payload_json'],
        float(row['received_at']),
        int(row['reason_code']),
        str(row['reason']),
    )


def _stored_command(row) -> StoredCommand:
    return StoredCommand(
        command_id=row['command_id'],
        mission_id=row['mission_id'],
        robot_id=row['robot_id'],
        command=int(row['command']),
        target_id=row['target_id'],
        target_pose=json.loads(row['target_pose_json']),
        issued_by=row['issued_by'],
        received_at=float(row['received_at']),
    )


def _uint32(value, name) -> int:
    if (
        isinstance(value, bool) or not isinstance(value, int)
        or not 0 <= value <= 0xFFFFFFFF
    ):
        raise ValueError(f'{name} must be in uint32 range')
    return value


def _command_value(value) -> MissionCommand:
    if isinstance(value, bool):
        raise ValueError('command must be a valid MissionCommand')
    try:
        return MissionCommand(value)
    except (TypeError, ValueError) as error:
        raise ValueError('command must be a valid MissionCommand') from error


def _canonical_json(value, name) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f'{name} must be JSON-compatible') from error


def _json_text(value, name, *, allow_empty) -> str:
    if not isinstance(value, str):
        raise ValueError(f'{name} must be a str')
    if not value and allow_empty:
        return value
    try:
        json.loads(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{name} must contain valid JSON') from error
    return value


def _nonempty_string(value, name) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f'{name} must be a non-empty str')
    return value


def _finite_nonnegative(value, name) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a real number')
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f'{name} must be finite and non-negative')
    return float(value)
