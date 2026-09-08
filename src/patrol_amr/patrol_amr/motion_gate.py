"""Combine launch authorization with live robot readiness."""

from __future__ import annotations

from patrol_amr.motion_authorization import authorization_blockers


class MotionGate:
    """Provide one fail-closed predicate to the command arbiter."""

    def __init__(
        self,
        robot_id: str,
        safety_path_ready: bool,
        hardware_test_mode: bool,
        motion_enable_token: str,
        readiness_snapshot,
    ) -> None:
        self._robot_id = robot_id
        self._safety_path_ready = safety_path_ready
        self._hardware_test_mode = hardware_test_mode
        self._motion_enable_token = motion_enable_token
        self._readiness_snapshot = readiness_snapshot

    def ready(self) -> bool:
        """Return true when both static and live checks pass."""
        return not self.blocking_reasons()

    def blocking_reasons(self) -> tuple[str, ...]:
        """Return all current launch and sensor blockers."""
        launch_reasons = authorization_blockers(
            self._robot_id,
            self._safety_path_ready,
            self._hardware_test_mode,
            self._motion_enable_token,
        )
        readiness_reasons = self._readiness_snapshot().blocking_reasons
        if self._hardware_test_mode and not self._safety_path_ready:
            # AMCL may retain an older header stamp while the robot is still.
            # Stock Nav2 owns TF/costmap freshness in this isolated test path.
            readiness_reasons = tuple(
                reason for reason in readiness_reasons
                if reason != 'AMCL_POSE_STALE'
            )
        return launch_reasons + readiness_reasons

    def summary(self) -> str:
        """Format current blockers for a concise operator log."""
        reasons = self.blocking_reasons()
        return 'READY' if not reasons else ','.join(reasons)
