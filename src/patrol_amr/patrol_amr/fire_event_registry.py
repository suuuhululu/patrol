"""Track active fire event IDs without depending on a ROS message type."""

from __future__ import annotations

from dataclasses import dataclass
import threading


@dataclass(frozen=True)
class FireRegistryUpdate:
    """Result of adding or resolving one active fire event."""

    changed: bool
    buzzer_should_be_on: bool
    active_event_count: int


class FireEventRegistry:
    """Maintain the active set used by the Q-12 buzzer decision."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_event_ids: set[str] = set()

    def activate(self, event_id: str) -> FireRegistryUpdate:
        """Add one fire; an already active ID has no second effect."""
        normalized = self._validate_id(event_id)
        with self._lock:
            before = len(self._active_event_ids)
            self._active_event_ids.add(normalized)
            return self._update(len(self._active_event_ids) != before)

    def resolve(self, event_id: str) -> FireRegistryUpdate:
        """Remove one fire and keep the buzzer on while another remains."""
        normalized = self._validate_id(event_id)
        with self._lock:
            existed = normalized in self._active_event_ids
            self._active_event_ids.discard(normalized)
            return self._update(existed)

    def snapshot(self) -> frozenset[str]:
        """Return an immutable active-event snapshot."""
        with self._lock:
            return frozenset(self._active_event_ids)

    def _update(self, changed: bool) -> FireRegistryUpdate:
        count = len(self._active_event_ids)
        return FireRegistryUpdate(changed, count > 0, count)

    @staticmethod
    def _validate_id(event_id: str) -> str:
        normalized = str(event_id).strip()
        if not normalized:
            raise ValueError('event_id is required')
        return normalized
