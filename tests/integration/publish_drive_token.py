#!/usr/bin/env python3
"""Publish renewing DriveToken messages for hand testing.

``ros2 topic pub -r 5`` cannot do this job. It repeats one fixed message,
so every sample after the first carries the same ``message_sequence`` and
DriveTokenGuard discards it as STALE_MESSAGE_SEQUENCE without extending
the lease (drive_token_guard.py). The robot then loses authority exactly
one ``lease_duration`` after the first message, whatever the publish rate.

This increments ``message_sequence`` the way 관제 will, so the lease keeps
renewing while the script runs and expires Q-01's 1.0 s after it stops.

    python3 tests/integration/publish_drive_token.py
    python3 tests/integration/publish_drive_token.py --robot-id robot6
    python3 tests/integration/publish_drive_token.py --revoke

Defaults are Q-01: 5 Hz publish, 1.0 s lease. It stands in for 관제 during
hand testing only and is not part of the token contract.
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
from patrol_interfaces.msg import DriveToken


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot-id', default='robot1', help='Token holder.')
    parser.add_argument(
        '--session',
        default='ctrl-handtest',
        help='control_session_id; change it to retire the previous session.',
    )
    parser.add_argument('--token', default='tok-a', help='token_id.')
    parser.add_argument(
        '--rate', type=float, default=5.0, help='Publish rate in Hz (Q-01: 5).'
    )
    parser.add_argument(
        '--lease',
        type=float,
        default=1.0,
        help='lease_duration in seconds (Q-01: 1.0).',
    )
    parser.add_argument(
        '--start-sequence', type=int, default=1, help='First message_sequence.'
    )
    parser.add_argument(
        '--revoke',
        action='store_true',
        help="Publish an empty token_id once: 관제's authority revocation.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    rclpy.init()
    node = Node('drive_token_publisher')
    # 9절: drive_token 은 BEST_EFFORT・VOLATILE・KEEP_LAST(3).
    publisher = node.create_publisher(
        DriveToken,
        '/control/drive_token',
        QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=3,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        ),
    )
    state = {'sequence': args.start_sequence}

    def publish():
        message = DriveToken()
        message.header.stamp = node.get_clock().now().to_msg()
        message.control_session_id = args.session
        message.token_id = '' if args.revoke else args.token
        message.holder_robot_id = args.robot_id
        message.lease_duration.sec = int(args.lease)
        message.lease_duration.nanosec = int(
            round((args.lease - int(args.lease)) * 1e9)
        )
        message.message_sequence = state['sequence']
        publisher.publish(message)
        state['sequence'] += 1

    try:
        if args.revoke:
            deadline = node.get_clock().now().nanoseconds + 3_000_000_000
            while (
                publisher.get_subscription_count() == 0
                and node.get_clock().now().nanoseconds < deadline
            ):
                rclpy.spin_once(node, timeout_sec=0.05)
            node.get_logger().info(
                f'revoking authority for {args.robot_id} '
                f'(empty token_id, sequence {state["sequence"]})'
            )
            publish()
            rclpy.spin_once(node, timeout_sec=0.2)
        else:
            node.get_logger().info(
                f'granting {args.robot_id} token {args.token!r} at '
                f'{args.rate} Hz, lease {args.lease}s, '
                f'message_sequence from {args.start_sequence}'
            )
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
