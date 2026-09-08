"""Small DriveToken callback separated from mission and navigation logic."""

from __future__ import annotations

from patrol_amr.mission_drive_token import DriveTokenDecision


class DriveTokenCallback:
    """Apply one token message and notify the mission safety gate."""

    def __init__(self, guard, synchronize_gate, logger) -> None:
        """Store collaborators while keeping ROS work out of the callback."""
        self._guard = guard
        self._synchronize_gate = synchronize_gate
        self._logger = logger

    def __call__(self, msg) -> None:
        """Validate one message, synchronize cancellation, and log edges."""
        decision = self._guard.update_message(msg)
        self._synchronize_gate()
        if decision is DriveTokenDecision.GRANTED:
            snapshot = self._guard.snapshot()
            self._logger.info(
                f'drive token granted: {snapshot.token_id} '
                f'sequence={snapshot.message_sequence}')
        elif decision is DriveTokenDecision.REVOKED:
            self._logger.warn('drive token revoked; active motion canceled')
        elif decision is DriveTokenDecision.HOLDER_CHANGED:
            self._logger.warn(
                'drive token moved to another robot; active motion canceled')
        elif decision is DriveTokenDecision.INVALID:
            self._logger.error('invalid drive token ignored')
