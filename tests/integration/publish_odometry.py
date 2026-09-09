#!/usr/bin/env python3
"""Publish stamped Odometry for hand testing status_reporter's motion_stopped.

``ros2 topic pub -r`` leaves ``header.stamp`` at zero, which reads as a
decades-old measurement and fails the interfaces.md 3절 freshness half of
the judgment every time. This stamps from the same ROS clock the reporter
compares against.

    python3 tests/integration/publish_odometry.py
    python3 tests/integration/publish_odometry.py --linear 0.3
    python3 tests/integration/publish_odometry.py --namespace /robot1

Defaults publish a stopped robot (0.0, 0.0) at 20 Hz. It stands in for the
drive base during hand testing only and is not part of any contract.
"""

import argparse

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--namespace',
        default='',
        help="Robot namespace, e.g. /robot1. Empty for a ros2 run node.",
    )
    parser.add_argument('--topic', default='odom')
    parser.add_argument(
        '--linear',
        type=float,
        default=0.0,
        help='twist.twist.linear.x in m/s. interfaces.md 3절 stop limit: 0.05.',
    )
    parser.add_argument(
        '--angular',
        type=float,
        default=0.0,
        help='twist.twist.angular.z in rad/s. Stop limit: 0.1.',
    )
    parser.add_argument('--rate', type=float, default=20.0)
    parser.add_argument('--frame-id', default='odom')
    parser.add_argument('--child-frame-id', default='base_link')
    return parser.parse_args()


def main():
    args = parse_args()
    topic = f"{args.namespace.rstrip('/')}/{args.topic.lstrip('/')}"

    rclpy.init()
    node = Node('odometry_publisher')
    # status_reporter 구독과 같은 sensor data QoS.
    publisher = node.create_publisher(Odometry, topic, qos_profile_sensor_data)

    def publish():
        message = Odometry()
        message.header.stamp = node.get_clock().now().to_msg()
        message.header.frame_id = args.frame_id
        message.child_frame_id = args.child_frame_id
        message.twist.twist.linear.x = args.linear
        message.twist.twist.angular.z = args.angular
        publisher.publish(message)

    node.get_logger().info(
        f'publishing linear={args.linear} angular={args.angular} '
        f'on {topic} at {args.rate} Hz'
    )
    try:
        node.create_timer(1.0 / args.rate, publish)
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
