"""Atomic process boundary for mission state consumed by status_reporter."""

from __future__ import annotations

from dataclasses import asdict
import json
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
            return MissionStateSnapshot(**payload)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise MissionStatusStoreError(
                f'cannot read mission status {self._path}: {exc}') from exc
