#!/usr/bin/env python3
"""Isolated ROS test for the 1A/2A command ownership boundary.

This uses real ROS publishers/subscribers and the production command_gateway.
The mission side is a probe so Nav2 and robot hardware cannot move.
"""

import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import tempfile
import time


os.environ['ROS_DOMAIN_ID'] = os.environ.get(
    'COMMAND_LIFECYCLE_SMOKE_DOMAIN_ID', '124')
os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
os.environ.pop('ROS_DISCOVERY_SERVER', None)
os.environ.pop('ROS_SUPER_CLIENT', None)
os.environ.pop('ROS_LOCALHOST_ONLY', None)
_ROS_LOG = tempfile.TemporaryDirectory(prefix='command-lifecycle-ros-log-')
os.environ['ROS_LOG_DIR'] = _ROS_LOG.name

from patrol_amr import command_lifecycle, patrol_report  # noqa: E402
from patrol_interfaces.msg import (  # noqa: E402
    CommandCheck, MissionCommand, PatrolReport)
import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402
from rclpy.qos import (  # noqa: E402
    DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy)
from std_msgs.msg import String  # noqa: E402


ROBOT_ID = 'robot1'
NS = '/robot1'
COMMAND_ID = 'cmd-ctrl-20260908T200000-robot1-start-0001'
MISSION_ID = 'msn-ctrl-20260908T200000-robot1-0001'
SOURCE_SESSION_ID = 'robot1-20260908T200000'


def qos(depth, durability=DurabilityPolicy.VOLATILE):
    return QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=depth,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=durability,
    )


class Probe(Node):
    def __init__(self):
        super().__init__('command_lifecycle_probe')
        self.checks = []
        self.dispatches = []
        self.replays = []
        self.create_subscription(
            CommandCheck,
            f'{NS}/command_check',
            self.checks.append,
            qos(10),
        )
        self.create_subscription(
            MissionCommand,
            f'{NS}/mission_dispatch',
            self.dispatches.append,
            qos(10),
        )
        self.create_subscription(
            PatrolReport,
            f'{NS}/report_replay_request',
            self.replays.append,
            qos(10),
        )
        self.command_publisher = self.create_publisher(
            MissionCommand, f'{NS}/mission_command', qos(10))
        self.lifecycle_publisher = self.create_publisher(
            String,
            f'{NS}/mission_lifecycle',
            qos(20, DurabilityPolicy.TRANSIENT_LOCAL),
        )

    def command(self, *, target_id='robot1_default'):
        message = MissionCommand()
        message.header.stamp = self.get_clock().now().to_msg()
        message.command_id = COMMAND_ID
        message.mission_id = MISSION_ID
        message.robot_id = ROBOT_ID
        message.command = MissionCommand.START_PATROL
        message.target_id = target_id
        return message


def wait_for(node, process, predicate, description, log_path, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(
                f'gateway exited while waiting for {description}\n'
                + log_path.read_text(errors='replace'))
        rclpy.spin_once(node, timeout_sec=0.05)
        if predicate():
            return
    raise AssertionError(
        f'timeout waiting for {description}\n'
        + log_path.read_text(errors='replace'))


def main():
    runtime = tempfile.TemporaryDirectory(prefix='command-lifecycle-runtime-')
    root = Path(runtime.name)
    database_path = root / 'command_store.sqlite3'
    log_path = root / 'command_gateway.log'
    command = [
        'ros2', 'run', 'patrol_amr_safety', 'command_gateway', '--ros-args',
        '-r', f'__ns:={NS}',
        '-p', f'robot_id:={ROBOT_ID}',
        '-p', f'source_session_id:={SOURCE_SESSION_ID}',
        '-p', f'database_path:={database_path}',
    ]
    with log_path.open('w') as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=os.environ.copy(),
        )

    rclpy.init()
    probe = Probe()
    try:
        wait_for(
            probe,
            process,
            lambda: probe.command_publisher.get_subscription_count() == 1
            and probe.lifecycle_publisher.get_subscription_count() == 1,
            'gateway subscriptions',
            log_path,
        )

        probe.command_publisher.publish(probe.command())
        wait_for(
            probe,
            process,
            lambda: any(
                item.command_id == COMMAND_ID
                and item.check_state == CommandCheck.CHECK_ACCEPTED
                for item in probe.checks)
            and len(probe.dispatches) == 1,
            'ACCEPTED and one full mission dispatch',
            log_path,
        )
        dispatched = probe.dispatches[0]
        assert dispatched.command_id == COMMAND_ID
        assert dispatched.mission_id == MISSION_ID
        assert dispatched.target_id == 'robot1_default'

        probe.command_publisher.publish(probe.command())
        time.sleep(0.2)
        rclpy.spin_once(probe, timeout_sec=0.2)
        assert len(probe.dispatches) == 1

        started = command_lifecycle.executing(dispatched)
        probe.lifecycle_publisher.publish(String(
            data=command_lifecycle.to_json(started)))
        wait_for(
            probe,
            process,
            lambda: any(
                item.command_id == COMMAND_ID
                and item.check_state == CommandCheck.CHECK_EXECUTING
                for item in probe.checks),
            'EXECUTING from mission lifecycle event',
            log_path,
        )

        report = patrol_report.PatrolReportFactory(
            ROBOT_ID, SOURCE_SESSION_ID).create(
                command_id=COMMAND_ID,
                mission_id=MISSION_ID,
                result=patrol_report.PatrolResult.SUCCEEDED,
                reason_code=patrol_report.ReasonCode.NONE,
                reason='',
                started_at=patrol_report.ReportTime(1),
                finished_at=patrol_report.ReportTime(2),
            )
        probe.lifecycle_publisher.publish(String(
            data=command_lifecycle.to_json(
                command_lifecycle.completed(report))))
        wait_for(
            probe,
            process,
            lambda: database_path.exists()
            and sqlite3.connect(database_path).execute(
                'SELECT state FROM mission_commands WHERE command_id = ?',
                (COMMAND_ID,),
            ).fetchone() == ('completed',),
            'completed SQLite state',
            log_path,
        )

        probe.command_publisher.publish(probe.command())
        wait_for(
            probe,
            process,
            lambda: any(item.report_id == report.report_id
                        for item in probe.replays),
            'exact completed report replay request',
            log_path,
        )
        assert len(probe.dispatches) == 1
        print('COMMAND_LIFECYCLE_SMOKE_PASS')
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
        runtime.cleanup()
        _ROS_LOG.cleanup()


if __name__ == '__main__':
    main()
