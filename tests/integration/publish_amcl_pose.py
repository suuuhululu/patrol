#!/usr/bin/env python3
"""Publish one stamped map-frame AMCL pose for stage-17 hand testing.

    python3 tests/integration/publish_amcl_pose.py --namespace /robot1

The message is stamped from the ROS clock and sent only after the
status_reporter subscription is discovered. It stands in for Nav2 AMCL during
hand testing and is not part of the runtime system.
"""

import argparse
import math
import time

from geometry_msgs.msg import PoseWithCovarianceStamped
import rclpy
from rclpy.node import Node


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--namespace', default='/robot1')
    parser.add_argument('--topic', default='amcl_pose')
    parser.add_argument('--x', type=float, default=1.25)
    parser.add_argument('--y', type=float, default=-0.5)
    parser.add_argument('--yaw', type=float, default=0.0)
    return parser.parse_args()


def main():
    args = parse_args()
    topic = f"{args.namespace.rstrip('/')}/{args.topic.lstrip('/')}"

    rclpy.init()
    node = Node('amcl_pose_handtest_publisher')
    publisher = node.create_publisher(PoseWithCovarianceStamped, topic, 10)
    try:
        deadline = time.monotonic() + 3.0
        while publisher.get_subscription_count() == 0:
            if time.monotonic() >= deadline:
                raise RuntimeError(f'no subscriber discovered on {topic}')
            rclpy.spin_once(node, timeout_sec=0.05)

        message = PoseWithCovarianceStamped()
        message.header.stamp = node.get_clock().now().to_msg()
        message.header.frame_id = 'map'
        message.pose.pose.position.x = args.x
        message.pose.pose.position.y = args.y
        message.pose.pose.orientation.z = math.sin(args.yaw / 2.0)
        message.pose.pose.orientation.w = math.cos(args.yaw / 2.0)
        message.pose.covariance[0] = 0.1
        message.pose.covariance[7] = 0.1
        message.pose.covariance[35] = 0.05
        publisher.publish(message)
        rclpy.spin_once(node, timeout_sec=0.2)
        node.get_logger().info(
            f'published map pose x={args.x} y={args.y} yaw={args.yaw} '
            f'on {topic}'
        )
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
