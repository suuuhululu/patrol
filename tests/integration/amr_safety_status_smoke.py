#!/usr/bin/env python3
"""Single-robot AMR ROS graph smoke test (stages 10 and 13).

This intentionally verifies only the connections implemented by
``amr_safety_status.launch.py``:

* BatteryState -> battery_monitor -> battery_status -> status_reporter
  -> RobotStatus                                                  (10단계)
* EStop + DriveToken -> local_safety_supervisor -> motion_allowed  (10단계)
* cmd_vel_safe + the two gates above -> local_safety_supervisor
  -> cmd_vel                                                      (13단계)
* Odometry -> status_reporter -> RobotStatus velocity/motion_stopped
                                                                  (14단계)
* A latched EStop -> local_safety_supervisor stays stopped         (15단계)
* Accepted/expired DriveToken -> RobotStatus token fields          (16단계)
* AMCL pose -> RobotStatus current/last-valid pose                 (17단계)

All topics live under the robot namespace the launch file now applies.

The drive candidate here is published by this script, not by Nav2. That
makes this a gate test, not IT-16: it shows the gate passes and blocks
correctly, not that a real planner drives the robot. It is also not a
hardware, heartbeat, mission, docking, Detection, or two-robot test. Run
it only after building and sourcing ``patrol_interfaces`` and
``patrol_amr``.
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
os.environ["ROS_DOMAIN_ID"] = os.environ.get("PATROL_SMOKE_DOMAIN_ID", "127")
os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "LOCALHOST"

_LOG_DIRECTORY = tempfile.TemporaryDirectory(prefix="patrol-amr-smoke-ros-log-")
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
from geometry_msgs.msg import PoseWithCovarianceStamped, Twist, TwistStamped
from nav_msgs.msg import Odometry
from patrol_interfaces.msg import DriveToken, EStop, RobotStatus
from sensor_msgs.msg import BatteryState
from std_msgs.msg import Bool


ROBOT_ID = "robot1"
SOURCE_SESSION_ID = "robot1-amr-smoke"
NS = f"/{ROBOT_ID}"
# 12단계에서 확정한 Q-17 값. motion_guard.CANDIDATE_MAX_AGE_SECONDS 와 같다.
CANDIDATE_MAX_AGE_SECONDS = 0.5
CANDIDATE = (0.25, -0.1)
# 14단계: interfaces.md 3절 실제 정지 판정.
STOP_HOLD_SECONDS = 0.5
MOVING_LINEAR = 0.3


def _qos(depth, reliability, durability):
    return QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=depth,
        reliability=reliability,
        durability=durability,
    )


class SmokeProbe(Node):
    """Publish test inputs and retain the three implemented output streams."""

    def __init__(self):
        super().__init__("amr_smoke_probe")
        self.motion_observations = []
        self.status_observations = []
        self.velocity_observations = []

        self.create_subscription(
            Bool,
            f"{NS}/motion_allowed",
            self._on_motion_allowed,
            _qos(
                10,
                ReliabilityPolicy.RELIABLE,
                DurabilityPolicy.TRANSIENT_LOCAL,
            ),
        )
        self.create_subscription(
            RobotStatus,
            f"{NS}/robot_status",
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
            BatteryState, f"{NS}/battery_state", qos_profile_sensor_data
        )
        # 12단계 속도 경로: RELIABLE・VOLATILE・KEEP_LAST(1).
        velocity_qos = _qos(
            1, ReliabilityPolicy.RELIABLE, DurabilityPolicy.VOLATILE
        )
        self.create_subscription(
            Twist, f"{NS}/cmd_vel", self._on_cmd_vel, velocity_qos
        )
        self.candidate_publisher = self.create_publisher(
            TwistStamped, f"{NS}/cmd_vel_safe", velocity_qos
        )
        self.odometry_publisher = self.create_publisher(
            Odometry, f"{NS}/odom", qos_profile_sensor_data
        )
        self.pose_publisher = self.create_publisher(
            PoseWithCovarianceStamped,
            f"{NS}/amcl_pose",
            10,
        )

    def _on_motion_allowed(self, message):
        self.motion_observations.append(bool(message.data))

    def _on_cmd_vel(self, message):
        self.velocity_observations.append(
            (round(message.linear.x, 6), round(message.angular.z, 6))
        )


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


def _publish_estop(node, sequence, active, latched=False):
    message = EStop()
    message.target_robot_id = ROBOT_ID
    message.active = active
    message.reason = 2 if active else 0
    message.latched = latched
    message.sequence = sequence
    node.estop_publisher.publish(message)


def _publish_token(node, sequence, lease_seconds):
    message = DriveToken()
    message.control_session_id = "ctrl-amr-smoke"
    message.token_id = "tok-amr-smoke-robot1"
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
        and node.battery_publisher.get_subscription_count() >= 2
        and node.candidate_publisher.get_subscription_count() >= 1
        and node.pose_publisher.get_subscription_count() >= 1,
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

    accepted_status_start = len(node.status_observations)
    _publish_token(node, 1, 8)
    _wait_for(
        node,
        launch_process,
        lambda: node.motion_observations[-1] is True,
        3.0,
        "valid token motion_allowed=true",
        log_path,
    )
    _wait_for(
        node,
        launch_process,
        lambda: any(
            status.source_session_id == SOURCE_SESSION_ID
            and status.accepted_token_id == 'tok-amr-smoke-robot1'
            and status.token_valid
            for status in node.status_observations[accepted_status_start:]
        ),
        2.0,
        'accepted token in RobotStatus',
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

    expiry_status_start = len(node.status_observations)
    _publish_token(node, 2, 2)
    _wait_for(
        node,
        launch_process,
        lambda: node.motion_observations[-1] is False,
        3.5,
        "two-second token lease expiry",
        log_path,
    )
    _wait_for(
        node,
        launch_process,
        lambda: any(
            status.source_session_id == SOURCE_SESSION_ID
            and not status.token_valid
            and status.accepted_token_id == ''
            for status in node.status_observations[expiry_status_start:]
        ),
        2.0,
        'expired token cleared from RobotStatus',
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


def _publish_candidate(node, linear, angular):
    """Publish one stamped drive candidate.

    The stamp matters: local_safety_supervisor measures Q-17 age against
    it, so an unstamped sample would read as decades old and be blocked.
    """
    message = TwistStamped()
    message.header.stamp = node.get_clock().now().to_msg()
    message.twist.linear.x = linear
    message.twist.angular.z = angular
    node.candidate_publisher.publish(message)


def _stream_candidate(node, seconds, linear, angular, period=0.05):
    """Feed candidates at 20 Hz, the rate Nav2's controller_server runs at."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _publish_candidate(node, linear, angular)
        rclpy.spin_once(node, timeout_sec=period)


def _check_velocity_path(node, launch_process, log_path):
    """13단계: the gated final velocity output."""
    _wait_for(
        node,
        launch_process,
        lambda: node.velocity_observations
        and node.velocity_observations[-1] == (0.0, 0.0),
        5.0,
        "initial cmd_vel stop stream",
        log_path,
    )

    # 권한만으로는 움직이지 않는다: 후보가 없으면 내보낼 값이 없다.
    _publish_estop(node, 10, False)
    _publish_token(node, 10, 8)
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
    if set(node.velocity_observations) != {(0.0, 0.0)}:
        raise AssertionError(
            "permission alone must not move the robot: "
            f"{sorted(set(node.velocity_observations))!r}"
        )

    # 후보가 들어오면 변형 없이 그대로 나간다.
    node.velocity_observations.clear()
    _stream_candidate(node, 0.6, *CANDIDATE)
    if CANDIDATE not in set(node.velocity_observations):
        raise AssertionError(
            "fresh candidate did not pass through: "
            f"{sorted(set(node.velocity_observations))!r}"
        )

    # 후보가 끊기면 Q-17 로 만료되어 정지로 돌아간다.
    node.velocity_observations.clear()
    _wait_for(
        node,
        launch_process,
        lambda: node.velocity_observations
        and node.velocity_observations[-1] == (0.0, 0.0),
        CANDIDATE_MAX_AGE_SECONDS + 1.0,
        "cmd_vel stop after candidate stream ended",
        log_path,
    )

    # E-stop 은 후보가 흐르는 중에도 즉시 반영된다.
    _stream_candidate(node, 0.4, *CANDIDATE)
    if node.velocity_observations[-1] != CANDIDATE:
        raise AssertionError("candidate did not resume before the E-stop step")
    _publish_estop(node, 11, True)
    node.velocity_observations.clear()
    _stream_candidate(node, 0.4, *CANDIDATE)
    if set(node.velocity_observations) != {(0.0, 0.0)}:
        raise AssertionError(
            "active E-stop must stop the output: "
            f"{sorted(set(node.velocity_observations))!r}"
        )

    # 해제하면 같은 후보 스트림으로 다시 통과한다.
    _publish_estop(node, 12, False)
    node.velocity_observations.clear()
    _stream_candidate(node, 0.6, *CANDIDATE)
    if CANDIDATE not in set(node.velocity_observations):
        raise AssertionError("released E-stop did not resume the candidate")


def _publish_odometry(node, linear, angular):
    message = Odometry()
    message.header.stamp = node.get_clock().now().to_msg()
    message.twist.twist.linear.x = linear
    message.twist.twist.angular.z = angular
    node.odometry_publisher.publish(message)


def _stream_odometry(node, seconds, linear, angular, period=0.05):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _publish_odometry(node, linear, angular)
        rclpy.spin_once(node, timeout_sec=period)


def _check_odometry_path(node, launch_process, log_path):
    """14단계: measured velocity and the motion_stopped judgment."""
    if any(status.motion_stopped for status in node.status_observations):
        raise AssertionError(
            "motion_stopped must stay false before any odometry arrives"
        )

    # 움직이는 표본은 정지가 아니고, 측정값이 그대로 보고된다.
    start = len(node.status_observations)
    _stream_odometry(node, STOP_HOLD_SECONDS + 0.4, MOVING_LINEAR, 0.0)
    moving = [
        status
        for status in node.status_observations[start:]
        if math.isclose(status.linear_velocity, MOVING_LINEAR, abs_tol=1e-6)
    ]
    if not moving:
        raise AssertionError("measured linear velocity was not reported")
    if any(status.motion_stopped for status in moving):
        raise AssertionError("a moving robot must not report motion_stopped")

    # 한도 안의 표본이 0.5초 연속 유지되면 정지로 본다.
    _stream_odometry(node, STOP_HOLD_SECONDS + 0.4, 0.0, 0.0)
    _wait_for(
        node,
        launch_process,
        lambda: node.status_observations[-1].motion_stopped,
        3.0,
        "motion_stopped after the odometry hold window",
        log_path,
    )

    # 관측이 끊기면 정지 주장을 거두고 속도를 NaN 으로 되돌린다.
    _wait_for(
        node,
        launch_process,
        lambda: not node.status_observations[-1].motion_stopped
        and math.isnan(node.status_observations[-1].linear_velocity),
        3.0,
        "stale odometry returns to NaN and not-stopped",
        log_path,
    )


def _check_pose_path(node, launch_process, log_path):
    """17단계: a received map pose stays valid without a guessed timeout."""
    source_statuses = [
        status for status in node.status_observations
        if status.source_session_id == SOURCE_SESSION_ID
    ]
    if any(status.pose_valid for status in source_statuses):
        raise AssertionError('pose_valid must start false before amcl_pose')

    start = len(node.status_observations)
    message = PoseWithCovarianceStamped()
    message.header.stamp = node.get_clock().now().to_msg()
    message.header.frame_id = 'map'
    message.pose.pose.position.x = 1.25
    message.pose.pose.position.y = -0.5
    message.pose.pose.orientation.w = 1.0
    message.pose.covariance[0] = 0.1
    message.pose.covariance[7] = 0.1
    message.pose.covariance[35] = 0.05
    node.pose_publisher.publish(message)

    def matching_pose(status):
        return (
            status.source_session_id == SOURCE_SESSION_ID
            and status.pose_valid
            and math.isclose(status.pose.pose.pose.position.x, 1.25)
            and math.isclose(status.pose.pose.pose.position.y, -0.5)
            and math.isclose(
                status.last_valid_pose.pose.pose.position.x, 1.25
            )
        )

    _wait_for(
        node,
        launch_process,
        lambda: any(
            matching_pose(status)
            for status in node.status_observations[start:]
        ),
        2.0,
        'valid current and last-valid pose in RobotStatus',
        log_path,
    )

    # Q-03/Q-05의 1.5초를 pose_valid timeout으로 오용하지 않는다.
    hold_deadline = time.monotonic() + 1.7
    while time.monotonic() < hold_deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
    own_latest = next(
        status for status in reversed(node.status_observations)
        if status.source_session_id == SOURCE_SESSION_ID
    )
    if not matching_pose(own_latest):
        raise AssertionError(
            'pose_valid changed or last-valid pose was lost without input'
        )


def _check_local_latch(node, launch_process, log_path):
    """15단계: a latched E-stop must survive the arbiter clearing it.

    Runs last on purpose. Once the local latch engages, nothing this script
    can publish releases it -- that is the point -- so no later check could
    observe motion.
    """
    _stream_candidate(node, 0.4, *CANDIDATE)
    if node.velocity_observations[-1] != CANDIDATE:
        raise AssertionError("candidate was not flowing before the latch step")

    _publish_estop(node, 20, True, latched=True)
    node.velocity_observations.clear()
    _stream_candidate(node, 0.4, *CANDIDATE)
    if set(node.velocity_observations) != {(0.0, 0.0)}:
        raise AssertionError("a latched E-stop must stop the output")

    # 관제가 active·latched 를 모두 내려도 로컬 latch 는 남는다.
    _publish_estop(node, 21, False, latched=False)
    node.velocity_observations.clear()
    _stream_candidate(node, 0.8, *CANDIDATE)
    if set(node.velocity_observations) != {(0.0, 0.0)}:
        raise AssertionError(
            "the arbiter clearing latched must not release the local latch: "
            f"{sorted(set(node.velocity_observations))!r}"
        )


def _check_single_velocity_publisher(node):
    """interfaces.md 7절: local_safety_supervisor is the sole publisher."""
    publishers = node.get_publishers_info_by_topic(f"{NS}/cmd_vel")
    names = sorted(info.node_name for info in publishers)
    if names != ["local_safety_supervisor"]:
        raise AssertionError(
            f"{NS}/cmd_vel publishers must be exactly "
            f"['local_safety_supervisor'], got {names!r}"
        )
    return names


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
        prefix="patrol-amr-smoke-launch-", suffix=".log"
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
        node = SmokeProbe()
        try:
            _check_initial_outputs(node, launch_process, launch_log.name)
            _check_safety_path(node, launch_process, launch_log.name)
            _check_pose_path(node, launch_process, launch_log.name)
            _check_battery_path(node, launch_process, launch_log.name)
            _check_velocity_path(node, launch_process, launch_log.name)
            _check_odometry_path(node, launch_process, launch_log.name)
            _check_local_latch(node, launch_process, launch_log.name)
            velocity_publishers = _check_single_velocity_publisher(node)
            sequences = _check_status_sequence(node)

            print("AMR_SMOKE_PASS")
            print(f"namespace={NS}")
            print("motion_allowed=false,true,false,true,false")
            print("token_status=empty,accepted,empty_after_expiry")
            print("battery_state=0,2,0")
            print(
                "cmd_vel=stop,candidate,stop_on_stale,stop_on_estop,"
                "candidate_after_release"
            )
            print("motion_stopped=false,moving_false,held_true,stale_false")
            print("pose=initial_invalid,valid_map_pose,held_without_timeout")
            print("local_latch=engaged_on_latched,held_after_arbiter_cleared")
            print(f"cmd_vel_publishers={velocity_publishers}")
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
