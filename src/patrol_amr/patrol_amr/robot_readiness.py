"""Thread-safe, ROS-independent readiness state for physical navigation."""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading


@dataclass(frozen=True)
class ReadinessSnapshot:
    """Current inputs used to admit a hardware motion command."""

    pose_valid: bool
    pose_age_s: float | None
    scan_seen: bool
    odom_seen: bool

    @property
    def ready(self) -> bool:
        """Return true only when all startup inputs are usable."""
        return not self.blocking_reasons

    @property
    def blocking_reasons(self) -> tuple[str, ...]:
        """Return stable reason codes suitable for operator logs."""
        reasons = []
        if not self.pose_valid:
            reasons.append('AMCL_POSE_INVALID_OR_MISSING')
        elif self.pose_age_s is None or self.pose_age_s > 1.5:
            reasons.append('AMCL_POSE_STALE')
        if not self.scan_seen:
            reasons.append('LIDAR_SCAN_NOT_RECEIVED')
        if not self.odom_seen:
            reasons.append('ODOMETRY_NOT_RECEIVED')
        return tuple(reasons)


class RobotReadiness:
    """Track AMCL freshness and initial LiDAR/odometry reception."""

    def __init__(self, monotonic) -> None:
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._pose_valid = False
        self._pose_source_age_s: float | None = None
        self._pose_received_at: float | None = None
        self._scan_seen = False
        self._odom_seen = False

    def record_pose(
        self,
        pose_stamp_ns: int,
        now_ros_ns: int,
        pose_valid: bool,
    ) -> None:
        """Record pose validity and age using its ROS header timestamp."""
        source_age_s = (now_ros_ns - pose_stamp_ns) / 1_000_000_000
        timestamp_valid = pose_stamp_ns > 0 and source_age_s >= 0.0
        with self._lock:
            self._pose_valid = pose_valid and timestamp_valid
            self._pose_source_age_s = (
                source_age_s if timestamp_valid and math.isfinite(source_age_s)
                else None
            )
            self._pose_received_at = self._monotonic()

    def record_scan(self) -> None:
        """Record that the namespaced LiDAR stream reached this process."""
        with self._lock:
            self._scan_seen = True

    def record_odom(self) -> None:
        """Record that the namespaced odometry stream reached this process."""
        with self._lock:
            self._odom_seen = True

    def snapshot(self) -> ReadinessSnapshot:
        """Return a consistent view and advance pose age monotonically."""
        now = self._monotonic()
        with self._lock:
            pose_age_s = self._pose_source_age_s
            if pose_age_s is not None and self._pose_received_at is not None:
                pose_age_s += max(0.0, now - self._pose_received_at)
            return ReadinessSnapshot(
                pose_valid=self._pose_valid,
                pose_age_s=pose_age_s,
                scan_seen=self._scan_seen,
                odom_seen=self._odom_seen,
            )
