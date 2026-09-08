"""Durable command-id and patrol checkpoint storage."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any


SCHEMA_VERSION = 1
RETENTION_SECONDS = 24 * 60 * 60
OLD_COMMAND_LIMIT = 1000


class StoreError(RuntimeError):
    """The command store could not guarantee durable state."""


class ClaimResult(Enum):
    NEW = 'new'
    DUPLICATE = 'duplicate'
    CONFLICT = 'conflict'


@dataclass(frozen=True)
class Claim:
    result: ClaimResult
    command_id: str


class CommandStore:
    """Atomically claims commands and stores per-patrol checkpoints."""

    def __init__(self, path: str | os.PathLike[str], clock=time.time):
        if not path:
            raise ValueError('command_store_path must be an explicit robot-specific path')
        self._path = Path(path).expanduser()
        self._clock = clock
        self._lock = threading.RLock()
        self._data = self._empty_data()
        self._load()

    @staticmethod
    def _empty_data() -> dict[str, Any]:
        return {'schema_version': SCHEMA_VERSION, 'commands': {}, 'checkpoints': {}}

    def claim(self, command_id: str, fingerprint: str) -> Claim:
        """Persist a command before side effects and detect ID/content conflicts."""
        if not command_id or not fingerprint:
            raise ValueError('command_id and fingerprint are required')
        with self._lock:
            now = self._clock()
            pruned = self._prune_commands(now)
            existing = self._data['commands'].get(command_id)
            if existing is not None:
                result = (ClaimResult.DUPLICATE if existing['fingerprint'] == fingerprint
                          else ClaimResult.CONFLICT)
                if pruned:
                    self._save()
                return Claim(result, command_id)
            self._data['commands'][command_id] = {
                'fingerprint': fingerprint,
                'claimed_unix_s': now,
                'outcome': 'CLAIMED',
                'reason': '',
            }
            self._prune_commands(now)
            self._save()
            return Claim(ClaimResult.NEW, command_id)

    def finish(self, command_id: str, outcome: str, reason: str = '') -> None:
        if outcome not in {
            'SUCCEEDED', 'FAILED', 'CANCELED', 'REJECTED', 'PAUSED',
            'SUPERSEDED',
        }:
            raise ValueError(f'unsupported outcome: {outcome}')
        with self._lock:
            entry = self._data['commands'].get(command_id)
            if entry is None:
                raise StoreError(f'cannot finish unclaimed command: {command_id}')
            entry.update({
                'outcome': outcome,
                'reason': reason,
                'finished_unix_s': self._clock(),
            })
            self._save()

    def outcome(self, command_id: str) -> str | None:
        with self._lock:
            entry = self._data['commands'].get(command_id)
            return None if entry is None else str(entry['outcome'])

    def save_checkpoint(self, patrol_id: str, next_waypoint_index: int) -> None:
        if not patrol_id:
            raise ValueError('patrol_id is required')
        if next_waypoint_index < 0:
            raise ValueError('next_waypoint_index must be non-negative')
        with self._lock:
            self._data['checkpoints'][patrol_id] = {
                'next_waypoint_index': int(next_waypoint_index),
                'updated_unix_s': self._clock(),
            }
            self._save()

    def load_checkpoint(self, patrol_id: str) -> int | None:
        with self._lock:
            entry = self._data['checkpoints'].get(patrol_id)
            return None if entry is None else int(entry['next_waypoint_index'])

    def clear_checkpoint(self, patrol_id: str) -> None:
        with self._lock:
            if self._data['checkpoints'].pop(patrol_id, None) is not None:
                self._save()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            loaded = json.loads(self._path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreError(f'cannot read command store {self._path}: {exc}') from exc
        if (not isinstance(loaded, dict)
                or loaded.get('schema_version') != SCHEMA_VERSION
                or not isinstance(loaded.get('commands'), dict)
                or not isinstance(loaded.get('checkpoints'), dict)):
            raise StoreError(f'unsupported or damaged command store: {self._path}')
        self._data = loaded

    def _prune_commands(self, now_unix_s: float) -> bool:
        """Keep every recent command plus the newest 1,000 older commands."""
        cutoff = now_unix_s - RETENTION_SECONDS
        commands = self._data['commands']
        old_commands = [
            (command_id, float(entry.get('claimed_unix_s', 0.0)))
            for command_id, entry in commands.items()
            if float(entry.get('claimed_unix_s', 0.0)) < cutoff
        ]
        old_commands.sort(key=lambda item: (item[1], item[0]), reverse=True)
        remove_ids = {
            command_id
            for command_id, _ in old_commands[OLD_COMMAND_LIMIT:]
        }
        for command_id in remove_ids:
            del commands[command_id]
        return bool(remove_ids)

    def _save(self) -> None:
        parent = self._path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=self._path.name + '.', dir=parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(self._data, stream, ensure_ascii=False, sort_keys=True)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(tmp_name, self._path)
                dir_fd = os.open(parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except FileNotFoundError:
                    pass
                raise
        except OSError as exc:
            raise StoreError(f'cannot persist command store {self._path}: {exc}') from exc
