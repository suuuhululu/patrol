#!/usr/bin/env python3
"""Isolated ROS test for the 2026-09-09 admission/event boundary.

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
for key in ('ROS_DISCOVERY_SERVER', 'ROS_SUPER_CLIENT', 'ROS_LOCALHOST_ONLY',
            'FASTRTPS_DEFAULT_PROFILES_FILE', 'FASTDDS_DEFAULT_PROFILES_FILE'):
    os.environ.pop(key, None)
_ROS_LOG = tempfile.TemporaryDirectory(prefix='command-lifecycle-ros-log-')
os.environ['ROS_LOG_DIR'] = _ROS_LOG.name

from patrol_amr import patrol_report  # noqa: E402
from patrol_interfaces.msg import (  # noqa: E402
    CommandCheck, MissionCommand, MissionExecutionEvent, PatrolReport)
import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402
from rclpy.qos import (  # noqa: E402
    DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy)


ROBOT_ID = os.environ.get('PATROL_SMOKE_ROBOT_ID', 'robot1')
if ROBOT_ID not in ('robot1', 'robot6'):
    raise ValueError('PATROL_SMOKE_ROBOT_ID must be robot1 or robot6')
NS = f'/{ROBOT_ID}'
COMMAND_ID = f'cmd-ctrl-20260908T200000-{ROBOT_ID}-start-0001'
MISSION_ID = f'msn-ctrl-20260908T200000-{ROBOT_ID}-0001'
SOURCE_SESSION_ID = f'{ROBOT_ID}-20260908T200000'


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
        self.event_sequence = 0
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
        self.event_publisher = self.create_publisher(
            MissionExecutionEvent,
            f'{NS}/mission_execution_event',
            qos(20, DurabilityPolicy.TRANSIENT_LOCAL),
        )

    def command(self, *, target_id=None):
        message = MissionCommand()
        message.header.stamp = self.get_clock().now().to_msg()
        message.command_id = COMMAND_ID
        message.mission_id = MISSION_ID
        message.robot_id = ROBOT_ID
        message.command = MissionCommand.START_PATROL
        message.target_id = f'{ROBOT_ID}_default' if target_id is None else target_id
        message.issued_by = 'ctrl-20260908T200000'
        return message

    def event(self, command, event_type, report=None, **overrides):
        self.event_sequence += 1
        message = MissionExecutionEvent()
        message.header.stamp = self.get_clock().now().to_msg()
        message.command_id = command.command_id
        message.mission_id = command.mission_id
        message.robot_id = command.robot_id
        message.event_type = event_type
        message.source_session_id = SOURCE_SESSION_ID
        message.sequence = self.event_sequence
        message.mission_state = overrides.get('mission_state', 0)
        message.reason_code = overrides.get('reason_code', 0)
        message.reason = overrides.get('reason', '')
        message.has_report = report is not None
        if report is not None:
            patrol_report.populate_message(
                message.report, report, patrol_report.ReportTime(3))
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
        # A filename relative to the node working directory must also work.
        '-p', f'database_path:={database_path.name}',
    ]
    with log_path.open('w') as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=os.environ.copy(),
            cwd=root,
        )

    rclpy.init()
    probe = Probe()
    try:
        wait_for(
            probe,
            process,
            lambda: probe.command_publisher.get_subscription_count() == 1
            and probe.event_publisher.get_subscription_count() == 1,
            'gateway subscriptions',
            log_path,
        )

        probe.command_publisher.publish(probe.command())
        wait_for(
            probe,
            process,
            lambda: len(probe.dispatches) == 1,
            'one full mission dispatch before admission',
            log_path,
        )
        dispatched = probe.dispatches[0]
        assert dispatched.command_id == COMMAND_ID
        assert dispatched.mission_id == MISSION_ID
        assert dispatched.target_id == f'{ROBOT_ID}_default'
        assert not any(
            item.command_id == COMMAND_ID
            and item.check_state == CommandCheck.CHECK_ACCEPTED
            for item in probe.checks)

        probe.event_publisher.publish(probe.event(
            dispatched, MissionExecutionEvent.ADMITTED))
        wait_for(
            probe, process,
            lambda: any(
                item.command_id == COMMAND_ID
                and item.check_state == CommandCheck.CHECK_ACCEPTED
                for item in probe.checks),
            'ACCEPTED after ADMITTED', log_path)

        probe.command_publisher.publish(probe.command())
        time.sleep(0.2)
        rclpy.spin_once(probe, timeout_sec=0.2)
        assert len(probe.dispatches) == 1

        probe.event_publisher.publish(probe.event(
            dispatched, MissionExecutionEvent.STARTED))
        wait_for(
            probe,
            process,
            lambda: any(
                item.command_id == COMMAND_ID
                and item.check_state == CommandCheck.CHECK_EXECUTING
                for item in probe.checks),
            'EXECUTING from mission execution event',
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
        probe.event_publisher.publish(probe.event(
            dispatched, MissionExecutionEvent.RESULT_STORED, report))
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
        check_command_matrix(probe, process, log_path)
        check_admission_timeout(probe, process, log_path)
        print('MISSION_EXECUTION_EVENT_SMOKE_PASS')
        print(f'robot_id={ROBOT_ID}, relative_database_path=PASS')
        print('command_matrix=six_types,invalid_robot,invalid_enum,invalid_target,duplicate,conflict')
        print('admission_timeout=206,late_admission_ignored')
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


def check_command_matrix(probe, process, log_path):
    """Exercise the real gateway only; no mission worker or robot is started."""
    for index, (kind, label, target) in enumerate((
        (MissionCommand.STOP, 'stop', ''),
        (MissionCommand.MOVE_TO_SAFE_ZONE, 'evacuate', ''),
        (MissionCommand.RESUME_PATROL, 'resume', ''),
        (MissionCommand.DOCK, 'dock', 'dock_1' if ROBOT_ID == 'robot1' else 'dock_6'),
        (MissionCommand.CANCEL, 'cancel', ''),
    ), start=2):
        message = probe.command(target_id=target)
        message.command_id = f'cmd-ctrl-20260908T200000-{ROBOT_ID}-{label}-{index:04d}'
        message.command = kind
        if kind == MissionCommand.STOP:
            message.mission_id = ''
        before = len(probe.dispatches)
        probe.command_publisher.publish(message)
        wait_for(probe, process, lambda: len(probe.dispatches) == before + 1,
                 f'{label} dispatched pending admission', log_path)
        dispatched = probe.dispatches[-1]
        probe.event_publisher.publish(probe.event(
            dispatched, MissionExecutionEvent.ADMITTED))
        wait_for(probe, process, lambda: any(
            item.command_id == message.command_id
            and item.check_state == CommandCheck.CHECK_ACCEPTED
            for item in probe.checks
        ), f'{label} accepted after admission', log_path)

    # A valid new START command stays stored once, even when its payload conflicts.
    valid = probe.command()
    valid.command_id = f'cmd-ctrl-20260908T200000-{ROBOT_ID}-start-0010'
    before = len(probe.dispatches)
    probe.command_publisher.publish(valid)
    wait_for(probe, process, lambda: len(probe.dispatches) == before + 1,
             'new START for duplicate and conflict', log_path)
    probe.event_publisher.publish(probe.event(
        probe.dispatches[-1], MissionExecutionEvent.ADMITTED))
    wait_for(probe, process, lambda: any(
        item.command_id == valid.command_id
        and item.check_state == CommandCheck.CHECK_ACCEPTED
        for item in probe.checks
    ), 'new START admitted', log_path)
    for change, value, expected in (
        (None, None, CommandCheck.CHECK_ACCEPTED),
        ('mission_id', f'msn-ctrl-20260908T200000-{ROBOT_ID}-9999', CommandCheck.CHECK_REJECTED),
        ('robot_id', 'robot6' if ROBOT_ID == 'robot1' else 'robot1', CommandCheck.CHECK_REJECTED),
        ('command', 99, CommandCheck.CHECK_REJECTED),
        ('target_id', 'unknown_plan', CommandCheck.CHECK_REJECTED),
    ):
        message = probe.command()
        message.command_id = valid.command_id
        if change:
            setattr(message, change, value)
        check_start = len(probe.checks)
        dispatch_start = len(probe.dispatches)
        probe.command_publisher.publish(message)
        wait_for(probe, process, lambda: any(
            item.command_id == message.command_id and item.check_state == expected
            for item in probe.checks[check_start:]
        ), f'duplicate/rejection {change}', log_path)
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            rclpy.spin_once(probe, timeout_sec=0.02)
        assert len(probe.dispatches) == dispatch_start, change
        if change == 'mission_id':
            assert any(item.reason_code == 203 for item in probe.checks[check_start:])


def check_admission_timeout(probe, process, log_path):
    """No executor admission within four seconds must fail closed."""
    message = probe.command()
    message.command_id = (
        f'cmd-ctrl-20260908T200000-{ROBOT_ID}-start-0099')
    message.mission_id = (
        f'msn-ctrl-20260908T200000-{ROBOT_ID}-0099')
    dispatch_start = len(probe.dispatches)
    check_start = len(probe.checks)
    probe.command_publisher.publish(message)
    wait_for(
        probe, process,
        lambda: len(probe.dispatches) == dispatch_start + 1,
        'timeout command pending dispatch', log_path)
    wait_for(
        probe, process,
        lambda: any(
            item.command_id == message.command_id
            and item.check_state == CommandCheck.CHECK_REJECTED
            and item.reason_code == 206
            for item in probe.checks[check_start:]),
        'four-second admission timeout rejection', log_path, timeout=6.0)

    probe.event_publisher.publish(probe.event(
        message, MissionExecutionEvent.ADMITTED))
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        rclpy.spin_once(probe, timeout_sec=0.02)
    assert not any(
        item.command_id == message.command_id
        and item.check_state == CommandCheck.CHECK_ACCEPTED
        for item in probe.checks[check_start:])


if __name__ == '__main__':
    main()
