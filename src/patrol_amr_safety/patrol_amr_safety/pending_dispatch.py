"""Admission timeout and restart replay decisions for pending commands."""

from __future__ import annotations

from enum import Enum
import math


ADMISSION_TIMEOUT_SECONDS = 4.0


class PendingAction(Enum):
    WAIT = 'wait'
    REDISPATCH = 'redispatch'
    REJECT_TIMEOUT = 'reject_timeout'


def decide(
    *,
    received_at: float,
    now: float,
    replayed_since_start: bool,
) -> PendingAction:
    """Return the one safe action for a persisted PENDING command."""
    received_at = _time(received_at, 'received_at')
    now = _time(now, 'now')
    if now < received_at:
        # A ROS clock reset must not replay an old side effect indefinitely.
        return PendingAction.REJECT_TIMEOUT
    if now - received_at >= ADMISSION_TIMEOUT_SECONDS:
        return PendingAction.REJECT_TIMEOUT
    if not replayed_since_start:
        return PendingAction.REDISPATCH
    return PendingAction.WAIT


def _time(value, name) -> float:
    if (
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(value) or value < 0.0
    ):
        raise ValueError(f'{name} must be finite and non-negative')
    return float(value)
