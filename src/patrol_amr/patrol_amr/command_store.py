"""Persistent MissionCommand deduplication for AMR-05.

The store implements the fixed parts of interfaces.md Q-14 without guessing
the remaining command-specific target or ``parameters_json`` schemas:

* retain every command received in the last 24 hours;
* retain the newest 1,000 commands older than 24 hours;
* never execute the same command ID twice, including after process restart;
* treat changes to robot, command, target, target pose, parameters, or mission
  as a command-ID conflict;
* return the existing accepted/executing/completed state for an exact retry;
* retain the completed report payload so the future ROS adapter can resend it.

Target pose is supplied as JSON-compatible data by the future ROS adapter.  It
is canonicalized only for exact comparison.  ``parameters_json`` is checked
for valid JSON when non-empty, but its keys and value types remain TBD-IF-001
and are deliberately not interpreted here.
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
    ACCEPTED = 'accepted'
    EXECUTING = 'executing'
    COMPLETED = 'completed'


class RegisterVerdict(Enum):
    NEW = 'new'
    DUPLICATE_ACCEPTED = 'duplicate_accepted'
    DUPLICATE_EXECUTING = 'duplicate_executing'
    DUPLICATE_COMPLETED = 'duplicate_completed'
    COMMAND_ID_CONFLICT = 'command_id_conflict'


@dataclass(frozen=True)
class CommandObservation:
    verdict: RegisterVerdict
    state: Optional[CommandState]
    report_id: Optional[str] = None
    report_payload_json: Optional[str] = None


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
        self._connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS mission_commands (
                command_id TEXT PRIMARY KEY,
                mission_id TEXT NOT NULL,
                robot_id TEXT NOT NULL,
                command INTEGER NOT NULL,
                target_id TEXT NOT NULL,
                target_pose_json TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                received_at REAL NOT NULL,
                state TEXT NOT NULL,
                report_id TEXT,
                report_payload_json TEXT
            )
            '''
        )
        self._connection.commit()

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
        parameters_json: str,
        received_at: float,
    ) -> CommandObservation:
        """Persist a new command or classify a retry without executing it."""
        command_id = _nonempty_string(command_id, 'command_id')
        mission_id = _nonempty_string(mission_id, 'mission_id')
        if robot_id not in ROBOT_IDS:
            raise ValueError(f'robot_id must be one of {ROBOT_IDS}')
        command = _command_value(command)
        if not isinstance(target_id, str):
            raise ValueError('target_id must be a str')
        target_pose_json = _canonical_json(target_pose, 'target_pose')
        parameters_json = _parameters_json(parameters_json)
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
                parameters_json=parameters_json,
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
                    target_pose_json, parameters_json, received_at, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    command_id,
                    mission_id,
                    robot_id,
                    int(command),
                    target_id,
                    target_pose_json,
                    parameters_json,
                    received_at,
                    CommandState.ACCEPTED.value,
                ),
            )
        return CommandObservation(
            RegisterVerdict.NEW, CommandState.ACCEPTED
        )

    def mark_executing(self, command_id: str) -> CommandState:
        """Move ACCEPTED to EXECUTING; exact retries are idempotent."""
        row = self._required(command_id)
        state = CommandState(row['state'])
        if state is CommandState.COMPLETED:
            raise ValueError('a completed command cannot execute again')
        if state is CommandState.ACCEPTED:
            with self._connection:
                self._connection.execute(
                    'UPDATE mission_commands SET state = ? '
                    'WHERE command_id = ?',
                    (CommandState.EXECUTING.value, command_id),
                )
        return CommandState.EXECUTING

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

    @staticmethod
    def _classify_existing(
        row,
        *,
        mission_id,
        robot_id,
        command,
        target_id,
        target_pose_json,
        parameters_json,
    ) -> CommandObservation:
        fingerprint = (
            mission_id,
            robot_id,
            int(command),
            target_id,
            target_pose_json,
            parameters_json,
        )
        stored = (
            row['mission_id'],
            row['robot_id'],
            row['command'],
            row['target_id'],
            row['target_pose_json'],
            row['parameters_json'],
        )
        if fingerprint != stored:
            return CommandObservation(
                RegisterVerdict.COMMAND_ID_CONFLICT, None
            )
        return _observation_for_row(row)


def _observation_for_row(row) -> CommandObservation:
    state = CommandState(row['state'])
    verdict = {
        CommandState.ACCEPTED: RegisterVerdict.DUPLICATE_ACCEPTED,
        CommandState.EXECUTING: RegisterVerdict.DUPLICATE_EXECUTING,
        CommandState.COMPLETED: RegisterVerdict.DUPLICATE_COMPLETED,
    }[state]
    return CommandObservation(
        verdict,
        state,
        row['report_id'],
        row['report_payload_json'],
    )


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


def _parameters_json(value: str) -> str:
    return _json_text(value, 'parameters_json', allow_empty=True)


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
