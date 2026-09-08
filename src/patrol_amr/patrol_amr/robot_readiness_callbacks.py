"""ROS subscriptions that feed the physical-navigation readiness state."""

from __future__ import annotations

import math
import time

from patrol_amr.robot_readiness import RobotReadiness
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


class RobotReadinessCallbacks:
    """Keep ROS callback work small and separate from mission decisions."""

    def __init__(self, node) -> None:
        self._node = node
        self._state = RobotReadiness(time.monotonic)
        self._subscriptions = (
            node.create_subscription(
                PoseWithCovarianceStamped,
                'amcl_pose',
                self.on_amcl_pose,
                qos_profile_sensor_data,
            ),
            node.create_subscription(
                LaserScan,
                'scan',
                self.on_scan,
                qos_profile_sensor_data,
            ),
            node.create_subscription(
                Odometry,
                'odom',
                self.on_odom,
                qos_profile_sensor_data,
            ),
        )

    def on_amcl_pose(self, msg: PoseWithCovarianceStamped) -> None:
        """Validate finite map pose data and preserve its source timestamp."""
        pose = msg.pose.pose
        values = (
            pose.position.x,
            pose.position.y,
            pose.position.z,
            pose.orientation.x,
            pose.orientation.y,
            pose.orientation.z,
            pose.orientation.w,
        )
        quaternion_norm = math.sqrt(sum(value * value for value in values[3:]))
        pose_valid = (
            msg.header.frame_id == 'map'
            and all(math.isfinite(value) for value in values)
            and quaternion_norm > 1e-6
        )
        stamp_ns = (
            int(msg.header.stamp.sec) * 1_000_000_000
            + int(msg.header.stamp.nanosec)
        )
        self._state.record_pose(
            stamp_ns,
            self._node.get_clock().now().nanoseconds,
            pose_valid,
        )

    def on_scan(self, _msg: LaserScan) -> None:
        """Mark the first LiDAR sample received under this namespace."""
        self._state.record_scan()

    def on_odom(self, _msg: Odometry) -> None:
        """Mark the first odometry sample received under this namespace."""
        self._state.record_odom()

    def snapshot(self):
        """Expose an immutable readiness snapshot to the motion gate."""
        return self._state.snapshot()
