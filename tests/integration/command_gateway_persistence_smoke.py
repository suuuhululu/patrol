#!/usr/bin/env python3
"""AMR-05 durability smoke: restart persistence and Q-14 retention.

Two gate items of the AMR-05 row need a running ROS graph, not a unit
test, because both are about what survives a process boundary:

* A command already answered must not be dispatched again after the node
  restarts. The SQLite store is the only thing carrying that across, so a
  unit test on the store proves the storage but not the wiring.
* Q-14 retention must actually run. ``CommandStore.prune`` was implemented
  and unit-tested while nothing called it, which is exactly the gap this
  checks for.

The store path is a temporary file, so this never touches the real
per-robot store under ~/.local/state.
"""

import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


os.environ["ROS_DOMAIN_ID"] = os.environ.get("PATROL_SMOKE_DOMAIN_ID", "125")
os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "LOCALHOST"
for key in ("ROS_DISCOVERY_SERVER", "ROS_SUPER_CLIENT", "ROS_LOCALHOST_ONLY",
            "FASTRTPS_DEFAULT_PROFILES_FILE", "FASTDDS_DEFAULT_PROFILES_FILE"):
    os.environ.pop(key, None)

_LOG_DIRECTORY = tempfile.TemporaryDirectory(prefix="patrol-gw-ros-log-")
os.environ.setdefault("ROS_LOG_DIR", _LOG_DIRECTORY.name)

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from patrol_interfaces.msg import (
    CommandCheck, MissionCommand, MissionExecutionEvent)


ROBOT_ID = "robot1"
SOURCE_SESSION_ID = "robot1-20260908T180000"
NS = f"/{ROBOT_ID}"
ACCEPTED, EXECUTING, REJECTED = 1, 2, 3

COMMAND_QOS = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
)


class Probe(Node):
    def __init__(self):
        super().__init__("gateway_persistence_probe")
        self.checks = []
        self.dispatch = []
        self.create_subscription(
            CommandCheck,
            f"{NS}/command_check",
            lambda m: self.checks.append((m.command_id, m.check_state)),
            COMMAND_QOS,
        )
        self.create_subscription(
            MissionCommand,
            f"{NS}/mission_dispatch",
            lambda m: self.dispatch.append(m.command_id),
            QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            ),
        )
        self.publisher = self.create_publisher(
            MissionCommand, f"{NS}/mission_command", COMMAND_QOS
        )
        event_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=20,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.event_publisher = self.create_publisher(
            MissionExecutionEvent,
            f"{NS}/mission_execution_event",
            event_qos,
        )
        self.event_sequence = 0

    def send(
        self,
        command_id="cmd-ctrl-20260908T180000-robot1-start-0001",
        mission_id="msn-ctrl-20260908T180000-robot1-0001",
    ):
        message = MissionCommand()
        message.header.stamp = self.get_clock().now().to_msg()
        message.command_id = command_id
        message.mission_id = mission_id
        message.robot_id = ROBOT_ID
        message.command = 1
        message.target_id = "robot1_default"
        message.issued_by = "ctrl-20260908T180000"
        self.publisher.publish(message)

    def admit(
        self,
        command_id="cmd-ctrl-20260908T180000-robot1-start-0001",
        mission_id="msn-ctrl-20260908T180000-robot1-0001",
    ):
        self.event_sequence += 1
        message = MissionExecutionEvent()
        message.header.stamp = self.get_clock().now().to_msg()
        message.command_id = command_id
        message.mission_id = mission_id
        message.robot_id = ROBOT_ID
        message.event_type = MissionExecutionEvent.ADMITTED
        message.source_session_id = SOURCE_SESSION_ID
        message.sequence = self.event_sequence
        self.event_publisher.publish(message)


def spin(node, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.02)


def start_gateway(database_path, log_file):
    return subprocess.Popen(
        [
            "ros2", "run", "patrol_amr_safety", "command_gateway", "--ros-args",
            "-r", f"__ns:={NS}",
            "-p", f"robot_id:={ROBOT_ID}",
            "-p", f"source_session_id:={SOURCE_SESSION_ID}",
            "-p", f"database_path:={database_path}",
        ],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5.0)


def crash(process):
    """Model an abrupt gateway loss without consuming its 4 s pending TTL."""
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2.0)


def wait_for(node, predicate, timeout, description, log_path):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
        if predicate():
            return
    raise AssertionError(
        f"timeout waiting for {description}\n"
        + Path(log_path).read_text(errors="replace")
    )


def check_restart_persistence(
    node, gateway, database_path, log_file, log_path
):
    """A command answered before the restart must not run a second time."""
    command_id = "cmd-ctrl-20260908T180000-robot1-start-0001"
    node.send(command_id)
    wait_for(
        node,
        lambda: node.dispatch == [command_id],
        10.0,
        "first pending dispatch before admission",
        log_path,
    )
    if (command_id, ACCEPTED) in node.checks:
        raise AssertionError("gateway accepted before executor admission")
    node.admit(command_id)
    wait_for(
        node,
        lambda: (command_id, ACCEPTED) in node.checks,
        5.0,
        "first ACCEPTED after executor admission",
        log_path,
    )

    stop(gateway)
    restarted = start_gateway(database_path, log_file)
    pending_restarted = None
    try:
        node.checks.clear()
        node.dispatch.clear()
        wait_for(
            node,
            lambda: node.publisher.get_subscription_count() >= 1
            and node.event_publisher.get_subscription_count() >= 1,
            15.0,
            "restarted gateway subscription",
            log_path,
        )
        # 재시작한 노드의 발행측이 이 probe 와 붙을 시간을 준다. 붙기 전에
        # 보내면 "dispatch 없음"이 계약 때문인지 미연결 때문인지 알 수 없다.
        spin(node, 1.5)
        node.send(command_id)
        wait_for(
            node,
            lambda: (command_id, ACCEPTED) in node.checks,
            10.0,
            "ACCEPTED again after restart",
            log_path,
        )
        # 여기가 핵심이다. 재시작으로 메모리 상태는 사라졌지만 저장소가 남아
        # 있으므로 같은 명령이 두 번째로 실행되면 안 된다.
        spin(node, 1.0)
        if node.dispatch:
            raise AssertionError(
                "a command answered before the restart was dispatched again: "
                f"{node.dispatch!r}"
            )

        pending_id = "cmd-ctrl-20260908T180000-robot1-start-0002"
        pending_mission = "msn-ctrl-20260908T180000-robot1-0002"
        node.send(pending_id, pending_mission)
        wait_for(
            node,
            lambda: node.dispatch == [pending_id],
            5.0,
            "pending command before second restart",
            log_path,
        )
        crash(restarted)
        node.checks.clear()
        node.dispatch.clear()
        pending_restarted = start_gateway(database_path, log_file)
        wait_for(
            node,
            lambda: node.publisher.get_subscription_count() >= 1
            and node.event_publisher.get_subscription_count() >= 1,
            15.0,
            "pending gateway restart subscriptions",
            log_path,
        )
        wait_for(
            node,
            lambda: pending_id in node.dispatch,
            5.0,
            "durable pending command replay after restart",
            log_path,
        )
        node.admit(pending_id, pending_mission)
        wait_for(
            node,
            lambda: (pending_id, ACCEPTED) in node.checks,
            5.0,
            "replayed pending command admitted",
            log_path,
        )
    finally:
        stop(restarted)
        if pending_restarted is not None:
            stop(pending_restarted)


def check_retention_ran(log_path, database_path):
    """Q-14 prune must have executed, not merely exist as a method."""
    import sqlite3

    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute(
            'SELECT COUNT(*) FROM mission_commands'
        ).fetchone()[0]
    finally:
        connection.close()
    if rows < 1:
        raise AssertionError('the store kept no command at all')
    # 24시간 안의 기록은 지워지면 안 된다. prune 이 돌면서도 방금 받은
    # 명령을 보존했다는 것이 Q-14 의 앞쪽 절반이다.
    return rows


def main():
    database_path = tempfile.mktemp(suffix=".sqlite3")
    with tempfile.NamedTemporaryFile(
        prefix="patrol-gw-persistence-", suffix=".log"
    ) as log_file:
        gateway = start_gateway(database_path, log_file)
        rclpy.init()
        node = Probe()
        try:
            wait_for(
                node,
                lambda: node.publisher.get_subscription_count() >= 1
                and node.event_publisher.get_subscription_count() >= 1,
                15.0,
                "gateway subscription",
                log_file.name,
            )
            spin(node, 1.5)
            check_restart_persistence(
                node, gateway, database_path, log_file, log_file.name
            )
            retained = check_retention_ran(log_file.name, database_path)

            print("GATEWAY_PERSISTENCE_PASS")
            print("restart=answered_again,not_dispatched_twice")
            print("pending_restart=redispatched_once,accepted_after_admission")
            print(f"retention=prune_ran,retained_rows={retained}")
            print(f"ros_domain_id={os.environ['ROS_DOMAIN_ID']}")
        finally:
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
            stop(gateway)
            if os.path.exists(database_path):
                os.remove(database_path)


if __name__ == "__main__":
    main()
