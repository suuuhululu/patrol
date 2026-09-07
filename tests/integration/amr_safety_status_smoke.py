#!/usr/bin/env python3
"""Stage-10, single-robot ROS graph smoke test.

This intentionally verifies only the two connections implemented by
``amr_safety_status.launch.py``:

* BatteryState -> battery_monitor -> battery_status -> status_reporter
  -> RobotStatus
* EStop + DriveToken -> local_safety_supervisor -> motion_allowed

It is not a hardware, final cmd_vel, heartbeat, mission, docking, Detection,
or two-robot integration test. Run it only after building and sourcing the
``patrol_interfaces`` and ``patrol_amr`` packages.
"""

import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


# Isolate the probe from the normal robot domain without changing the parent
# shell. A caller can select another test-only domain when 127 is already used.
os.environ["ROS_DOMAIN_ID"] = os.environ.get("PATROL_STAGE10_DOMAIN_ID", "127")
os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "LOCALHOST"

_LOG_DIRECTORY = tempfile.TemporaryDirectory(prefix="patrol-stage10-ros-log-")
os.environ.setdefault("ROS_LOG_DIR", _LOG_DIRECTORY.name)

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
    qos_profile_sensor_data,
)
from patrol_interfaces.msg import DriveToken, EStop, RobotStatus
from sensor_msgs.msg import BatteryState
from std_msgs.msg import Bool


ROBOT_ID = "robot1"
SOURCE_SESSION_ID = "robot1-stage10-smoke"


def _qos(depth, reliability, durability):
    return QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=depth,
        reliability=reliability,
        durability=durability,
    )


class Stage10Probe(Node):
    """Publish test inputs and retain the two implemented output streams."""

    def __init__(self):
        super().__init__("stage10_probe")
        self.motion_observations = []
        self.status_observations = []

        self.create_subscription(
            Bool,
            "/motion_allowed",
            self._on_motion_allowed,
            _qos(
                10,
                ReliabilityPolicy.RELIABLE,
                DurabilityPolicy.TRANSIENT_LOCAL,
            ),
        )
        self.create_subscription(
            RobotStatus,
            f"/{ROBOT_ID}/robot_status",
            self.status_observations.append,
            _qos(
                20,
                ReliabilityPolicy.RELIABLE,
                DurabilityPolicy.VOLATILE,
            ),
        )
        self.estop_publisher = self.create_publisher(
            EStop,
            "/control/estop",
            _qos(
                1,
                ReliabilityPolicy.RELIABLE,
                DurabilityPolicy.TRANSIENT_LOCAL,
            ),
        )
        self.token_publisher = self.create_publisher(
            DriveToken,
            "/control/drive_token",
            _qos(
                3,
                ReliabilityPolicy.BEST_EFFORT,
                DurabilityPolicy.VOLATILE,
            ),
        )
        self.battery_publisher = self.create_publisher(
            BatteryState, "/battery_state", qos_profile_sensor_data
        )

    def _on_motion_allowed(self, message):
        self.motion_observations.append(bool(message.data))


def _launch_log(log_path):
    return Path(log_path).read_text(errors="replace")


def _wait_for(node, launch_process, predicate, timeout, description, log_path):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if launch_process.poll() is not None:
            raise AssertionError(
                f"launch exited while waiting for {description}\n"
                + _launch_log(log_path)
            )
        rclpy.spin_once(node, timeout_sec=0.05)
        if predicate():
            return
    raise AssertionError(
        f"timeout waiting for {description}\n" + _launch_log(log_path)
    )


def _publish_estop(node, sequence, active):
    message = EStop()
    message.target_robot_id = ROBOT_ID
    message.active = active
    message.reason = 2 if active else 0
    message.latched = False
    message.sequence = sequence
    node.estop_publisher.publish(message)


def _publish_token(node, sequence, lease_seconds):
    message = DriveToken()
    message.control_session_id = "ctrl-stage10-smoke"
    message.token_id = "tok-stage10-smoke-robot1"
    message.holder_robot_id = ROBOT_ID
    message.lease_duration.sec = lease_seconds
    message.lease_duration.nanosec = 0
    message.message_sequence = sequence
    node.token_publisher.publish(message)


def _check_initial_outputs(node, launch_process, log_path):
    _wait_for(
        node,
        launch_process,
        lambda: node.estop_publisher.get_subscription_count() >= 1
        and node.token_publisher.get_subscription_count() >= 1
        and node.battery_publisher.get_subscription_count() >= 2,
        10.0,
        "all launch subscriptions",
        log_path,
    )
    _wait_for(
        node,
        launch_process,
        lambda: False in node.motion_observations,
        5.0,
        "initial motion_allowed=false",
        log_path,
    )
    _wait_for(
        node,
        launch_process,
        lambda: any(
            status.source_session_id == SOURCE_SESSION_ID
            and status.battery_state == RobotStatus.UNKNOWN
            for status in node.status_observations
        ),
        5.0,
        "initial RobotStatus",
        log_path,
    )


def _check_safety_path(node, launch_process, log_path):
    initial_count = len(node.motion_observations)
    _publish_estop(node, 1, False)
    deadline = time.monotonic() + 0.4
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
    if node.motion_observations[-1] is not False:
        raise AssertionError("E-stop release alone must not grant motion")
    if len(node.motion_observations) != initial_count:
        raise AssertionError("unchanged false state must not be republished")

    _publish_token(node, 1, 8)
    _wait_for(
        node,
        launch_process,
        lambda: node.motion_observations[-1] is True,
        3.0,
        "valid token motion_allowed=true",
        log_path,
    )

    _publish_estop(node, 2, True)
    _wait_for(
        node,
        launch_process,
        lambda: node.motion_observations[-1] is False,
        2.0,
        "active E-stop motion_allowed=false",
        log_path,
    )

    _publish_estop(node, 3, False)
    _wait_for(
        node,
        launch_process,
        lambda: node.motion_observations[-1] is True,
        2.0,
        "released E-stop with valid token motion_allowed=true",
        log_path,
    )

    _publish_token(node, 2, 2)
    _wait_for(
        node,
        launch_process,
        lambda: node.motion_observations[-1] is False,
        3.5,
        "two-second token lease expiry",
        log_path,
    )

    expected = [False, True, False, True, False]
    if node.motion_observations != expected:
        raise AssertionError(
            f"motion transitions {node.motion_observations!r} != {expected!r}"
        )


def _check_battery_path(node, launch_process, log_path):
    low_start_index = len(node.status_observations)
    publish_started_at = time.monotonic()
    for index in range(36):
        target_time = publish_started_at + index * 0.1
        while True:
            remaining = target_time - time.monotonic()
            if remaining <= 0.0:
                break
            rclpy.spin_once(node, timeout_sec=min(0.02, remaining))
        message = BatteryState()
        message.header.stamp = node.get_clock().now().to_msg()
        message.percentage = 0.15
        message.power_supply_status = (
            BatteryState.POWER_SUPPLY_STATUS_DISCHARGING
        )
        message.present = True
        node.battery_publisher.publish(message)
    rclpy.spin_once(node, timeout_sec=0.05)

    _wait_for(
        node,
        launch_process,
        lambda: any(
            status.battery_state == RobotStatus.LOW
            and math.isclose(status.battery_soc, 0.15, abs_tol=1e-6)
            for status in node.status_observations[low_start_index:]
        ),
        2.0,
        "LOW RobotStatus after sustained battery input",
        log_path,
    )
    low_seen_index = next(
        index
        for index, status in enumerate(node.status_observations)
        if index >= low_start_index and status.battery_state == RobotStatus.LOW
    )
    _wait_for(
        node,
        launch_process,
        lambda: any(
            status.battery_state == RobotStatus.UNKNOWN
            for status in node.status_observations[low_seen_index + 1 :]
        ),
        5.0,
        "battery stale transition back to UNKNOWN",
        log_path,
    )


def _check_status_sequence(node):
    sequences = [
        status.status_sequence
        for status in node.status_observations
        if status.source_session_id == SOURCE_SESSION_ID
    ]
    if len(sequences) < 5:
        raise AssertionError(f"too few RobotStatus messages: {len(sequences)}")
    if not all(new > old for old, new in zip(sequences, sequences[1:])):
        raise AssertionError(f"status_sequence did not increase: {sequences!r}")
    return sequences


def main():
    with tempfile.NamedTemporaryFile(
        prefix="patrol-stage10-launch-", suffix=".log"
    ) as launch_log:
        launch_process = subprocess.Popen(
            [
                "ros2",
                "launch",
                "patrol_amr",
                "amr_safety_status.launch.py",
                f"robot_id:={ROBOT_ID}",
                f"source_session_id:={SOURCE_SESSION_ID}",
                "safety_state:=0",
            ],
            stdout=launch_log,
            stderr=subprocess.STDOUT,
        )

        rclpy.init()
        node = Stage10Probe()
        try:
            _check_initial_outputs(node, launch_process, launch_log.name)
            _check_safety_path(node, launch_process, launch_log.name)
            _check_battery_path(node, launch_process, launch_log.name)
            sequences = _check_status_sequence(node)

            print("STAGE10_PASS")
            print("motion_allowed=false,true,false,true,false")
            print("battery_state=0,2,0")
            print(
                f"status_messages={len(sequences)} "
                f"sequence={sequences[0]}..{sequences[-1]}"
            )
            print(f"ros_domain_id={os.environ['ROS_DOMAIN_ID']}")
        finally:
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
            if launch_process.poll() is None:
                launch_process.send_signal(signal.SIGINT)
                try:
                    launch_process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    launch_process.kill()
                    launch_process.wait(timeout=5.0)


if __name__ == "__main__":
    main()
