"""Thread-safe callback state for local-safety mission permission."""

from __future__ import annotations

import threading


class MotionPermission:
    """Store ``motion_allowed`` and notify mission arbitration on each edge."""

    def __init__(self, synchronize) -> None:
        self._synchronize = synchronize
        self._allowed = False
        self._lock = threading.Lock()

    def __call__(self, message) -> None:
        """Accept one ``std_msgs/Bool`` callback without running navigation."""
        with self._lock:
            self._allowed = bool(message.data)
        self._synchronize()

    def allowed(self) -> bool:
        """Return the latest fail-closed permission state."""
        with self._lock:
            return self._allowed
