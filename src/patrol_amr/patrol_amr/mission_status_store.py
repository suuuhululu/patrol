"""Atomic process boundary for mission state consumed by status_reporter."""

from __future__ import annotations

from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import tempfile

from patrol_amr.mission_state import MissionStateSnapshot


SCHEMA_VERSION = 1


class MissionStatusStoreError(RuntimeError):
    """The mission snapshot could not be persisted or read safely."""


class MissionStatusStore:
    """Write and read one latest mission snapshot using atomic replacement."""

    def __init__(self, path) -> None:
        self._path = Path(path).expanduser()

    def write(self, snapshot: MissionStateSnapshot) -> None:
        if not isinstance(snapshot, MissionStateSnapshot):
            raise TypeError('snapshot must be MissionStateSnapshot')
        _validate_snapshot(snapshot)
        payload = {'schema_version': SCHEMA_VERSION, **asdict(snapshot)}
        parent = self._path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(
                prefix=self._path.name + '.', dir=parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(payload, stream, sort_keys=True)
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
            raise MissionStatusStoreError(
                f'cannot persist mission status {self._path}: {exc}') from exc

    def read(self) -> MissionStateSnapshot | None:
        if not self._path.exists():
            return None
        try:
            payload = json.loads(self._path.read_text(encoding='utf-8'))
            if not isinstance(payload, dict):
                raise ValueError('mission status root must be an object')
            if payload.pop('schema_version', None) != SCHEMA_VERSION:
                raise ValueError('unsupported schema_version')
            snapshot = MissionStateSnapshot(**payload)
            _validate_snapshot(snapshot)
            return snapshot
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise MissionStatusStoreError(
                f'cannot read mission status {self._path}: {exc}') from exc


def _validate_snapshot(snapshot: MissionStateSnapshot) -> None:
    for name in (
        'mission', 'command_id', 'mission_id', 'outcome', 'reason',
    ):
        if not isinstance(getattr(snapshot, name), str):
            raise ValueError(f'{name} must be a str')
    for name in ('waypoint_index', 'last_waypoint_index'):
        value = getattr(snapshot, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < -1:
            raise ValueError(f'{name} must be an int greater than or equal to -1')
    if (
        isinstance(snapshot.reason_code, bool)
        or not isinstance(snapshot.reason_code, int)
        or not 0 <= snapshot.reason_code <= 0xFFFFFFFF
    ):
        raise ValueError('reason_code must fit in uint32')
    if (
        isinstance(snapshot.updated_monotonic_s, bool)
        or not isinstance(snapshot.updated_monotonic_s, (int, float))
        or not math.isfinite(snapshot.updated_monotonic_s)
        or snapshot.updated_monotonic_s < 0.0
    ):
        raise ValueError('updated_monotonic_s must be finite and non-negative')
    if (
        isinstance(snapshot.revision, bool)
        or not isinstance(snapshot.revision, int)
        or snapshot.revision < 0
    ):
        raise ValueError('revision must be a non-negative int')
