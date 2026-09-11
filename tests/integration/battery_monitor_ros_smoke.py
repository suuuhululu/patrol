#!/usr/bin/env python3
"""Real ROS pub/sub test for the BatteryState -> LOW path."""

import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


os.environ['ROS_DOMAIN_ID'] = os.environ.get('BATTERY_SMOKE_DOMAIN_ID', '122')
os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
for key in ('ROS_DISCOVERY_SERVER', 'ROS_SUPER_CLIENT', 'ROS_LOCALHOST_ONLY',
            'FASTRTPS_DEFAULT_PROFILES_FILE', 'FASTDDS_DEFAULT_PROFILES_FILE'):
    os.environ.pop(key, None)
_ROS_LOG = tempfile.TemporaryDirectory(prefix='battery-smoke-ros-log-')
os.environ['ROS_LOG_DIR'] = _ROS_LOG.name

import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402
from rclpy.qos import (  # noqa: E402
    DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy,
    qos_profile_sensor_data)
from sensor_msgs.msg import BatteryState  # noqa: E402
from std_msgs.msg import UInt8  # noqa: E402


class Probe(Node):
    def __init__(self):
        super().__init__('battery_monitor_probe')
        self.states = []
        output_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.publisher = self.create_publisher(
            BatteryState, '/robot1/battery_state', qos_profile_sensor_data)
        self.create_subscription(
            UInt8, '/robot1/battery_status',
            lambda message: self.states.append(message.data), output_qos)


def spin_until(node, predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.02)
        if predicate():
            return True
    return False


def main():
    with tempfile.NamedTemporaryFile(
        prefix='battery-monitor-', suffix='.log') as log:
        process = subprocess.Popen(
            [
                'ros2', 'run', 'patrol_amr_safety', 'battery_monitor',
                '--ros-args', '-r', '__ns:=/robot1',
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=os.environ.copy(),
        )
        rclpy.init()
        probe = Probe()
        try:
            if not spin_until(
                probe,
                lambda: probe.publisher.get_subscription_count() == 1,
                10.0,
            ):
                raise AssertionError('battery subscription not matched')
            deadline = time.monotonic() + 6.0
            while time.monotonic() < deadline and 2 not in probe.states:
                message = BatteryState()
                message.header.stamp = probe.get_clock().now().to_msg()
                message.percentage = 0.15
                message.power_supply_status = (
                    BatteryState.POWER_SUPPLY_STATUS_DISCHARGING)
                message.present = True
                probe.publisher.publish(message)
                rclpy.spin_once(probe, timeout_sec=0.1)
            if 2 not in probe.states:
                raise AssertionError(
                    f'LOW not received; states={probe.states!r}\n'
                    + Path(log.name).read_text(errors='replace'))
            print('BATTERY_MONITOR_ROS_SMOKE_PASS')
        finally:
            probe.destroy_node()
            rclpy.shutdown()
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)
            _ROS_LOG.cleanup()


if __name__ == '__main__':
    main()
