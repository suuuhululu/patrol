"""Persistent PatrolReport outbox shared by mission and status processes."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import json
import os
from pathlib import Path
import tempfile

from patrol_amr.mission_reporter import MissionCompletion


SCHEMA_VERSION = 1


class PatrolReportOutboxError(RuntimeError):
    """The report queue could not preserve its delivery state."""


@dataclass(frozen=True)
class PendingPatrolReport:
    report_id: str
    report_sequence: int
    robot_id: str
    source_session_id: str
    command_id: str
    mission_id: str
    result: int
    reason_code: int
    reason: str
    started_at_ns: int
    finished_at_ns: int
    final_waypoint_id: str
    related_event_ids: tuple[str, ...]


def to_patrol_report_record(record: PendingPatrolReport):
    """Convert a durable outbox record to the canonical gateway payload."""
    if not isinstance(record, PendingPatrolReport):
        raise ValueError('record must be a PendingPatrolReport')
    from patrol_amr import patrol_report

    started_sec, started_nanosec = divmod(record.started_at_ns, 1_000_000_000)
    finished_sec, finished_nanosec = divmod(
        record.finished_at_ns, 1_000_000_000)
    factory = patrol_report.PatrolReportFactory(
        record.robot_id,
        record.source_session_id,
        next_sequence=record.report_sequence,
    )
    converted = factory.create(
        command_id=record.command_id,
        mission_id=record.mission_id,
        result=record.result,
        reason_code=record.reason_code,
        reason=record.reason,
        started_at=patrol_report.ReportTime(started_sec, started_nanosec),
        finished_at=patrol_report.ReportTime(finished_sec, finished_nanosec),
        final_waypoint_id=record.final_waypoint_id,
        related_event_ids=record.related_event_ids,
    )
    if converted.report_id != record.report_id:
        raise ValueError('outbox report_id does not match its sequence')
    return converted


class PatrolReportOutbox:
    """Atomically enqueue results and remove them after a publish attempt."""

    def __init__(self, path) -> None:
        self._path = Path(path).expanduser()
        self._lock_path = self._path.with_suffix(self._path.suffix + '.lock')

    def enqueue(
        self,
        completion: MissionCompletion,
        source_session_id: str,
    ) -> PendingPatrolReport:
        if not source_session_id:
            raise ValueError('source_session_id is required')
        with self._file_lock():
            data = self._load()
            existing = data['pending'].get(completion.command_id)
            if existing is not None:
                record = self._decode(existing)
                if self._same_completion(record, completion, source_session_id):
                    return record
                raise PatrolReportOutboxError(
                    f'command report conflict: {completion.command_id}')

            sequences = data['next_sequences']
            sequence = int(sequences.get(source_session_id, 1))
            sequences[source_session_id] = sequence + 1
            record = PendingPatrolReport(
                report_id=f'rpt-{source_session_id}-{sequence:04d}',
                report_sequence=sequence,
                robot_id=completion.robot_id,
                source_session_id=source_session_id,
                command_id=completion.command_id,
                mission_id=completion.mission_id,
                result=int(completion.outcome),
                reason_code=completion.reason_code,
                reason=completion.reason,
                started_at_ns=completion.started_at_ns,
                finished_at_ns=completion.finished_at_ns,
                final_waypoint_id=completion.final_waypoint_id,
                related_event_ids=completion.related_event_ids,
            )
            encoded = asdict(record)
            encoded['related_event_ids'] = list(record.related_event_ids)
            data['pending'][completion.command_id] = encoded
            self._save(data)
            return record

    def pending(self) -> tuple[PendingPatrolReport, ...]:
        with self._file_lock():
            data = self._load()
            records = tuple(
                self._decode(value) for value in data['pending'].values())
        return tuple(sorted(
            records,
            key=lambda item: (item.source_session_id, item.report_sequence),
        ))

    def mark_published(self, report_id: str) -> bool:
        with self._file_lock():
            data = self._load()
            matching = next(
                (
                    command_id
                    for command_id, value in data['pending'].items()
                    if value.get('report_id') == report_id
                ),
                None,
            )
            if matching is None:
                return False
            del data['pending'][matching]
            self._save(data)
            return True

    @contextmanager
    def _file_lock(self):
        stream = None
        try:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            stream = self._lock_path.open('a+', encoding='utf-8')
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            yield stream
        except OSError as exc:
            raise PatrolReportOutboxError(
                f'cannot lock report outbox {self._path}: {exc}') from exc
        finally:
            if stream is not None:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                finally:
                    stream.close()

    def _load(self):
        if not self._path.exists():
            return {
                'schema_version': SCHEMA_VERSION,
                'next_sequences': {},
                'pending': {},
            }
        try:
            data = json.loads(self._path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise PatrolReportOutboxError(
                f'cannot read report outbox {self._path}: {exc}') from exc
        if (
            not isinstance(data, dict)
            or data.get('schema_version') != SCHEMA_VERSION
            or not isinstance(data.get('next_sequences'), dict)
            or not isinstance(data.get('pending'), dict)
        ):
            raise PatrolReportOutboxError(
                f'unsupported or damaged report outbox: {self._path}')
        if any(
            not isinstance(session_id, str)
            or not session_id
            or not isinstance(sequence, int)
            or sequence < 1
            for session_id, sequence in data['next_sequences'].items()
        ):
            raise PatrolReportOutboxError(
                f'damaged report sequence state: {self._path}')
        return data

    def _save(self, data) -> None:
        parent = self._path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(
                prefix=self._path.name + '.', dir=parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(data, stream, sort_keys=True)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self._path)
                directory = os.open(parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except Exception:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                raise
        except OSError as exc:
            raise PatrolReportOutboxError(
                f'cannot persist report outbox {self._path}: {exc}') from exc

    @staticmethod
    def _decode(value) -> PendingPatrolReport:
        try:
            decoded = dict(value)
            decoded['related_event_ids'] = tuple(decoded['related_event_ids'])
            record = PendingPatrolReport(**decoded)
        except (KeyError, TypeError, ValueError) as exc:
            raise PatrolReportOutboxError(
                'damaged pending PatrolReport record') from exc
        strings = (
            record.report_id,
            record.robot_id,
            record.source_session_id,
            record.command_id,
            record.mission_id,
            record.reason,
            record.final_waypoint_id,
        )
        valid = (
            all(isinstance(value, str) for value in strings)
            and bool(record.report_id)
            and bool(record.robot_id)
            and bool(record.source_session_id)
            and bool(record.command_id)
            and bool(record.mission_id)
            and record.robot_id in {'robot1', 'robot6'}
            and isinstance(record.report_sequence, int)
            and not isinstance(record.report_sequence, bool)
            and record.report_sequence >= 1
            and isinstance(record.result, int)
            and not isinstance(record.result, bool)
            and record.result in {0, 1, 2}
            and isinstance(record.reason_code, int)
            and not isinstance(record.reason_code, bool)
            and 0 <= record.reason_code <= 0xFFFFFFFF
            and (
                (record.result == 0 and record.reason_code == 0)
                or (record.result in {1, 2} and record.reason_code != 0)
            )
            and isinstance(record.started_at_ns, int)
            and not isinstance(record.started_at_ns, bool)
            and record.started_at_ns >= 0
            and isinstance(record.finished_at_ns, int)
            and not isinstance(record.finished_at_ns, bool)
            and record.finished_at_ns >= record.started_at_ns
            and all(
                isinstance(event_id, str)
                for event_id in record.related_event_ids)
        )
        if not valid:
            raise PatrolReportOutboxError(
                'damaged pending PatrolReport record')
        return record

    @staticmethod
    def _same_completion(record, completion, source_session_id):
        return (
            record.source_session_id == source_session_id
            and record.robot_id == completion.robot_id
            and record.command_id == completion.command_id
            and record.mission_id == completion.mission_id
            and record.result == int(completion.outcome)
            and record.reason_code == completion.reason_code
            and record.reason == completion.reason
            and record.started_at_ns == completion.started_at_ns
            and record.finished_at_ns == completion.finished_at_ns
            and record.final_waypoint_id == completion.final_waypoint_id
            and record.related_event_ids == completion.related_event_ids
        )
