#!/usr/bin/env python3
"""Publish stamped drive candidates for hand testing local_safety_supervisor.

``ros2 topic pub`` cannot do this job: it leaves ``header.stamp`` at zero,
which local_safety_supervisor correctly reads as a decades-old sample and
blocks under Q-17. Filling the stamp from the shell with ``date +%s`` does
not work either -- it truncates to whole seconds, so the stamp lands up to
a second in the past and trips the same 0.5 s limit about half the time.

This publishes a real stamp from the same ROS clock the node compares
against, at the 20 Hz Nav2's controller_server runs at.

    python3 tests/integration/publish_drive_candidate.py
    python3 tests/integration/publish_drive_candidate.py --namespace /robot1
    python3 tests/integration/publish_drive_candidate.py --linear 0.1 --once

It stands in for Nav2 during 12단계 hand testing only. It is not part of
the drive contract and nothing in the running system should depend on it.
"""

import argparse

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from geometry_msgs.msg import TwistStamped


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--namespace',
        default='',
        help="Robot namespace, e.g. /robot1. Empty for a ros2 run node.",
    )
    parser.add_argument(
        '--topic',
        default='cmd_vel_safe',
        help='Candidate topic name under the namespace.',
    )
    parser.add_argument('--linear', type=float, default=0.25)
    parser.add_argument('--angular', type=float, default=-0.1)
    parser.add_argument(
        '--rate',
        type=float,
        default=20.0,
        help="Publish rate in Hz; 20 matches Nav2's controller_frequency.",
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Publish a single sample and exit, to watch Q-17 expire.',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    topic = f"{args.namespace.rstrip('/')}/{args.topic.lstrip('/')}"

    rclpy.init()
    node = Node('drive_candidate_publisher')
    # 12단계 노드의 구독 QoS 와 같다: RELIABLE・VOLATILE・KEEP_LAST(1).
    publisher = node.create_publisher(
        TwistStamped,
        topic,
        QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        ),
    )

    def publish():
        message = TwistStamped()
        message.header.stamp = node.get_clock().now().to_msg()
        message.twist.linear.x = args.linear
        message.twist.angular.z = args.angular
        publisher.publish(message)

    node.get_logger().info(
        f'publishing ({args.linear}, {args.angular}) on {topic} '
        + ('once' if args.once else f'at {args.rate} Hz')
    )
    try:
        if args.once:
            # 구독자가 붙기 전에 보내면 조용히 사라지므로 잠깐 기다린다.
            deadline = node.get_clock().now().nanoseconds + 3_000_000_000
            while (
                publisher.get_subscription_count() == 0
                and node.get_clock().now().nanoseconds < deadline
            ):
                rclpy.spin_once(node, timeout_sec=0.05)
            if publisher.get_subscription_count() == 0:
                node.get_logger().warning(
                    'no subscriber on the candidate topic; is '
                    'local_safety_supervisor running with a matching '
                    'namespace?'
                )
            publish()
            rclpy.spin_once(node, timeout_sec=0.2)
        else:
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
