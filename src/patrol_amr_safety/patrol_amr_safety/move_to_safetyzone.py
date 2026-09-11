#!/usr/bin/env python3
"""Evacuation helper imported by 3_1_c_follow_waypoints.py.

Shares the patrol navigator; owns no patrol route or standalone ROS node.
See move_to_safeyzone.md for settings and the flowchart.
"""

import argparse
import math
import time

import rclpy
from nav_msgs.msg import Odometry
from nav2_simple_commander.robot_navigator import TaskResult
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from rclpy.utilities import remove_ros_args
from std_msgs.msg import UInt8
from tf2_ros import Buffer, TransformListener


# ── 1. 명령·상태·시험용 기본 설정 ──
MOVE_TO_SAFE_ZONE, RESUME_PATROL = 1, 2
PATROLLING, EVACUATING, WAITING = 0, 1, 2
STATE_NAMES = {PATROLLING: "PATROLLING", EVACUATING: "EVACUATING", WAITING: "WAITING"}
SPIN = "spin"
SAFE_ZONES = {  # map 좌표 (x, y, yaw degree); WP 3은 안전구역 제외
    1: (-0.206, -1.038, 90.8),
    2: (-1.147, 0.500, 175.4),
    4: (-2.751, -2.422, 182.4),
    5: (-4.389, -1.122, 94.3),
    6: (-2.909, 0.575, 358.3),
    7: (-1.374, -2.439, 359.8),
}
TEST_DEFAULTS = {  # 사용자 요청으로 지정한 시험값; 실기 검증 전
    "linear-epsilon": 0.01,   # m/s
    "angular-epsilon": 0.02,  # rad/s
    "stop-hold": 0.5,         # s
    "stop-timeout": 10.0,     # s
    "data-max-age": 1.0,      # s
}


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robot-id", "--namespace", dest="namespace",
                        choices=("robot1", "robot6"), default="robot1")
    parser.add_argument("--command-topic")
    parser.add_argument("--stop-service")
    parser.add_argument("--resume-topic")
    parser.add_argument("--odom-topic")
    parser.add_argument("--base-frame", default="base_link")
    parser.add_argument("--safe", nargs=3, type=float, action="append",
                        metavar=("X", "Y", "YAW_DEG"))
    for name, value in TEST_DEFAULTS.items():
        parser.add_argument(f"--{name}", type=float, default=value)
    args = parser.parse_args(remove_ros_args()[1:])
    args.command_topic = (f"/{args.namespace}/safety_command"
                          if args.command_topic is None else args.command_topic)
    args.stop_service = (f"/{args.namespace}/patrol_stop"
                         if args.stop_service is None else args.stop_service)
    args.resume_topic = (f"/{args.namespace}/patrol_resume"
                         if args.resume_topic is None else args.resume_topic)
    args.odom_topic = f"/{args.namespace}/odom" if args.odom_topic is None else args.odom_topic
    args.safe = list(SAFE_ZONES.values()) if args.safe is None else args.safe
    values = [v for pose in args.safe for v in pose]
    limits = [args.linear_epsilon, args.angular_epsilon, args.stop_hold,
              args.stop_timeout, args.data_max_age]
    if not all(math.isfinite(v) for v in values + limits):
        parser.error("Coordinates and limits must be finite")
    if min(limits) <= 0 or args.stop_timeout <= args.stop_hold:
        parser.error("Limits must be positive; stop-timeout must exceed stop-hold")
    if not all((args.namespace.strip('/'), args.command_topic,
                args.odom_topic, args.base_frame, args.stop_service, args.resume_topic)):
        parser.error("Namespace, topics and base-frame must not be empty")
    return args


class Evacuation:
    def __init__(self, nav, args, event_check=None):
        self.nav, self.args = nav, args
        self.event_check = event_check
        self.state, self.saved_index = PATROLLING, None
        self.active = self.evacuate = self.resume = False
        self.odom = None
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, nav)
        self.command_sub = None
        if event_check is None:
            self.command_sub = nav.create_subscription(
                UInt8, args.command_topic, self.on_command, 10)
        self.odom_sub = nav.create_subscription(
            Odometry, args.odom_topic, self.on_odom, qos_profile_sensor_data)
        self.safe = [nav.getPoseStamped([x, y], yaw) for x, y, yaw in args.safe]
        nav.info(
            f"[SAFETY_SUB] node={nav.get_fully_qualified_name()} "
            f"command={self.command_sub.topic_name if self.command_sub else 'event_check'} "
            f"odom={self.odom_sub.topic_name} "
            f"tf={self.listener.tf_sub.topic_name} "
            f"tf_static={self.listener.tf_static_sub.topic_name}; "
            "active=False state=PATROLLING (patrol preparation)")

    def on_command(self, msg):
        accepted = False
        if self.active and self.state == PATROLLING and msg.data == MOVE_TO_SAFE_ZONE:
            self.evacuate = True
            accepted, reason = True, "evacuation_flag_set"
        elif self.active and self.state == WAITING and msg.data == RESUME_PATROL:
            self.resume = True
            accepted, reason = True, "resume_flag_set"
        elif not self.active:
            reason = "patrol_inactive"
        elif msg.data == MOVE_TO_SAFE_ZONE:
            reason = "requires_PATROLLING"
        elif msg.data == RESUME_PATROL:
            reason = "requires_WAITING"
        else:
            reason = "unsupported_command"
        self.nav.info(
            f"[SAFETY_CMD] received data={msg.data} active={self.active} "
            f"state={STATE_NAMES.get(self.state, 'UNKNOWN')}({self.state}) "
            f"decision={'ACCEPTED' if accepted else 'IGNORED'} reason={reason} "
            f"evacuate={self.evacuate} resume={self.resume}")

    def on_odom(self, msg):
        self.odom = msg

    def set_active(self, active):
        self.active = active
        if self.event_check is not None:
            self.event_check.set_active(active)

    def check_events(self):
        if self.event_check is not None and self.event_check.stop_requested:
            self.evacuate = True

    def tick(self):
        if not rclpy.ok():
            raise RuntimeError("ROS shutdown")
        rclpy.spin_once(self.nav, timeout_sec=0.1)
        self.check_events()

    def fresh(self, stamp):
        age = (self.nav.get_clock().now() - Time.from_msg(stamp)).nanoseconds / 1e9
        return 0 <= age <= self.args.data_max_age

    def position(self):
        self.nav.info(f"[SAFETY_TF] looking up map -> {self.args.base_frame}")
        transform = self.tf.lookup_transform("map", self.args.base_frame, Time())
        if not self.fresh(transform.header.stamp):
            raise RuntimeError("Current map position is stale")
        p = transform.transform.translation
        if not all(math.isfinite(v) for v in (p.x, p.y)):
            raise RuntimeError("Invalid current position")
        return p.x, p.y

    # ── 3. 기존 순찰의 이동·spin 완료 대기 중 명령 확인 ──
    def wait_for_task(self, interruptible=True):
        while True:
            complete = self.nav.isTaskComplete()
            self.check_events()
            if interruptible and self.evacuate:
                self.nav.info("[SAFETY_STEP] evacuation flag detected; leaving patrol task wait")
                return False
            if complete:
                return self.nav.getResult() == TaskResult.SUCCEEDED
            if not rclpy.ok():
                raise RuntimeError("ROS shutdown")

    def navigate(self, pose):
        pose.header.stamp = self.nav.get_clock().now().to_msg()
        self.nav.info(
            f"[SAFETY_NAV] requesting goal x={pose.pose.position.x:.3f} "
            f"y={pose.pose.position.y:.3f}")
        if not self.nav.goToPose(pose):
            raise RuntimeError("Evacuation/return navigation failed")
        self.nav.info("[SAFETY_NAV] goal accepted; waiting for result")
        if not self.wait_for_task(interruptible=False):
            raise RuntimeError("Evacuation/return navigation failed")
        self.nav.info("[SAFETY_NAV] task succeeded")

    def stop(self):
        deadline = time.monotonic() + self.args.stop_timeout
        # Bound cancellation acknowledgement too; cancelTask() itself waits forever.
        if self.nav.result_future is not None and not self.nav.result_future.done():
            cancel = self.nav.goal_handle.cancel_goal_async()
            while not cancel.done():
                if time.monotonic() >= deadline:
                    raise RuntimeError("Action cancellation acknowledgement timeout")
                self.tick()
            cancel.result()  # propagate transport failure; still verify action termination
        self.nav.info("[SAFETY_STOP] cancellation checked; waiting for action termination")
        while not self.nav.isTaskComplete():
            if time.monotonic() >= deadline:
                raise RuntimeError("Action termination timeout")
            self.tick()
        # 취소 이전 측정값을 정지 확인에 재사용하지 않음
        self.odom = None
        after_stop_stamp = self.nav.get_clock().now().nanoseconds
        settled = None
        first_stamp = None
        self.nav.info(
            "[SAFETY_STOP] action termination check passed; waiting for fresh stopped odometry")
        while time.monotonic() < deadline:
            self.tick()
            msg = self.odom
            stopped = False
            if (msg is not None and self.fresh(msg.header.stamp)
                    and Time.from_msg(msg.header.stamp).nanoseconds > after_stop_stamp):
                v, w = msg.twist.twist.linear, msg.twist.twist.angular
                stopped = (math.hypot(v.x, v.y, v.z) <= self.args.linear_epsilon
                           and math.hypot(w.x, w.y, w.z) <= self.args.angular_epsilon)
            if not stopped:
                settled = first_stamp = None
                continue
            stamp = Time.from_msg(msg.header.stamp).nanoseconds / 1e9
            if settled is None:
                settled, first_stamp = time.monotonic(), stamp
            if (stamp - first_stamp >= self.args.stop_hold
                    and time.monotonic() - settled >= self.args.stop_hold):
                self.nav.info("[SAFETY_STOP] fresh odometry confirmed a stop")
                return
        raise RuntimeError("Fresh odometry did not confirm a stop")

    # ── 4. map 직선거리 기준 최근접 안전구역 이동 ──
    def escape_and_wait(self, route, index):
        # ── 2. 원래 순찰 단계 저장; 경로 실행은 호출자가 담당 ──
        self.saved_index = index
        self.state, self.evacuate = EVACUATING, False
        self.nav.info(f"Evacuating; saved patrol index={self.saved_index}")
        self.stop()
        x, y = self.position()
        target = min(self.safe, key=lambda p:
                     (p.pose.position.x - x) ** 2 + (p.pose.position.y - y) ** 2)
        self.nav.info(
            f"[SAFETY_TARGET] current=({x:.3f}, {y:.3f}) "
            f"safe=({target.pose.position.x:.3f}, {target.pose.position.y:.3f})")
        self.navigate(target)
        self.stop()

        # ── 5. 안전구역에서 명령 2 대기 ──
        self.resume = False
        self.state = WAITING
        self.nav.info("WAITING: publish command 2 to resume")
        while not self.resume:
            self.tick()

        # ── 6. spin이면 직전 위치로 복귀 후 360도 재실행 ──
        self.state = EVACUATING
        if route[self.saved_index] == SPIN:
            self.navigate(route[self.saved_index - 1])
        self.resume = False
        self.state = PATROLLING
        self.nav.info(f"Resuming patrol index={self.saved_index}")


if __name__ == "__main__":
    raise SystemExit("Run 3_1_c_follow_waypoints.py; this file is an imported helper.")
