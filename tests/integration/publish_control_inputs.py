#!/usr/bin/env python3
"""
Publish normal v1.1 vision inputs for control-PC hand testing.

This node stands in for the vision publishers only.  It never publishes an
AMR-owned topic.  Start ``patrol_control_node`` and, when needed, the System
monitor ROS adapter in separate terminals before selecting one scenario:

    python3 tests/integration/publish_control_inputs.py permit-steady
    python3 tests/integration/publish_control_inputs.py permit-cycle
    python3 tests/integration/publish_control_inputs.py detection \
      --robot-id robot1 --event-type fire

The permit scenarios use the fixed 5 Hz publisher contract.  The detection
scenario keeps a healthy ``patrol_allowed=true`` stream active while sending
one valid v1.1 DetectionEvent.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import time

from patrol_interfaces.msg import DetectionEvent

import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile
from rclpy.qos import ReliabilityPolicy
from std_msgs.msg import Bool


PERMIT_PUBLISH_HZ = 5.0
PERMIT_PERIOD_SECONDS = 1.0 / PERMIT_PUBLISH_HZ
EVENT_TYPE_BY_NAME = {
    'fire': DetectionEvent.FIRE,
    'leak': DetectionEvent.LEAK,
    'obstacle': DetectionEvent.OBSTACLE,
}
ROBOT_IDS = ('robot1', 'robot6')


def permit_qos() -> QoSProfile:
    """Return the fixed patrol_allowed QoS."""
    return QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
        deadline=Duration(nanoseconds=500_000_000),
    )


def detection_event_qos() -> QoSProfile:
    """Return the fixed v1.1 DetectionEvent QoS."""
    return QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=10,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )


class ControlInputPublisher(Node):
    """Publish only the vision-owned inputs consumed on the control PC."""

    def __init__(self, args: argparse.Namespace) -> None:
        """Create permit and robot-specific DetectionEvent publishers."""
        super().__init__('control_input_test_publisher')
        self._args = args
        self._started_at = time.monotonic()
        self._permit_value = args.permit == 'true'
        self._event_published = False
        self._done = False
        self._session = datetime.now(timezone.utc).strftime(
            'vision-test-%Y%m%dT%H%M%S'
        ).lower()
        self._permit_publisher = self.create_publisher(
            Bool,
            '/vision/cctv/patrol_allowed',
            permit_qos(),
        )
        self._event_publishers = {
            robot_id: self.create_publisher(
                DetectionEvent,
                f'/{robot_id}/detection/event',
                detection_event_qos(),
            )
            for robot_id in ROBOT_IDS
        }
        self._timer = self.create_timer(PERMIT_PERIOD_SECONDS, self._tick)
        self.get_logger().info(
            'normal scenario started: %s' % args.scenario
        )

    @property
    def done(self) -> bool:
        """Return whether the configured finite scenario has completed."""
        return self._done

    def _tick(self) -> None:
        elapsed = time.monotonic() - self._started_at
        if self._args.duration > 0 and elapsed >= self._args.duration:
            self._done = True
            self._timer.cancel()
            self.get_logger().info('normal scenario completed')
            return
        if self._args.scenario == 'permit-cycle':
            if elapsed < self._args.step_seconds:
                self._permit_value = True
            elif elapsed < self._args.step_seconds * 2:
                self._permit_value = False
            else:
                self._permit_value = True

        permit = Bool()
        permit.data = self._permit_value
        self._permit_publisher.publish(permit)

        if (
            self._args.scenario == 'detection'
            and not self._event_published
            and elapsed >= self._args.event_delay
        ):
            self._publish_detection_event()

    def _publish_detection_event(self) -> None:
        robot_id = self._args.robot_id
        event_name = self._args.event_type
        sequence = 1
        message = DetectionEvent()
        now = self.get_clock().now().to_msg()
        message.header.stamp = now
        message.header.frame_id = 'map'
        message.message_id = (
            f'detmsg-{self._session}-{robot_id}-{sequence:04d}'
        )
        message.event_id = (
            f'det-{self._session}-{robot_id}-{event_name}-{sequence:04d}'
        )
        message.robot_id = robot_id
        message.event_type = EVENT_TYPE_BY_NAME[event_name]
        message.confidence = self._args.confidence
        message.location_valid = False
        message.detected_at = now
        message.evidence_id = (
            f'evi-{self._session}-{robot_id}-{sequence:04d}'
        )
        self._event_publishers[robot_id].publish(message)
        self._event_published = True
        self.get_logger().info(
            'DetectionEvent published: robot=%s event=%s type=%s'
            % (robot_id, message.event_id, event_name)
        )


def parse_args() -> argparse.Namespace:
    """Parse one normal scenario without exposing invalid-message options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'scenario',
        choices=('permit-steady', 'permit-cycle', 'detection'),
    )
    parser.add_argument(
        '--permit',
        choices=('true', 'false'),
        default='true',
        help='Steady Bool value; detection always keeps this stream active.',
    )
    parser.add_argument(
        '--duration',
        type=float,
        default=0.0,
        help='Seconds to run; zero continues until Ctrl+C.',
    )
    parser.add_argument(
        '--step-seconds',
        type=float,
        default=2.0,
        help='Seconds per true/false/true step in permit-cycle.',
    )
    parser.add_argument('--robot-id', choices=ROBOT_IDS, default='robot1')
    parser.add_argument(
        '--event-type',
        choices=tuple(EVENT_TYPE_BY_NAME),
        default='fire',
    )
    parser.add_argument(
        '--confidence',
        type=float,
        default=0.9,
    )
    parser.add_argument(
        '--event-delay',
        type=float,
        default=1.0,
        help='Seconds of healthy permit traffic before DetectionEvent.',
    )
    args = parser.parse_args()
    if args.duration < 0:
        parser.error('--duration must not be negative')
    if args.step_seconds <= 0:
        parser.error('--step-seconds must be positive')
    if not 0.0 <= args.confidence <= 1.0:
        parser.error('--confidence must be between 0.0 and 1.0')
    if args.event_delay < 0:
        parser.error('--event-delay must not be negative')
    return args


def main() -> None:
    """Run the selected normal-input publisher until completion or Ctrl+C."""
    args = parse_args()
    rclpy.init()
    node = ControlInputPublisher(args)
    try:
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
