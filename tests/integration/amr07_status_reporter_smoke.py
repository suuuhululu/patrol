#!/usr/bin/env python3
"""Isolated ROS smoke test for AMR-07 RobotStatus and PatrolReport."""

import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


os.environ['ROS_DOMAIN_ID'] = os.environ.get('AMR07_SMOKE_DOMAIN_ID', '126')
os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
os.environ.pop('ROS_DISCOVERY_SERVER', None)
os.environ.pop('ROS_SUPER_CLIENT', None)
os.environ.pop('ROS_LOCALHOST_ONLY', None)
_ROS_LOG = tempfile.TemporaryDirectory(prefix='amr07-ros-log-')
os.environ['ROS_LOG_DIR'] = _ROS_LOG.name

from patrol_amr.mission_reporter import MissionCompletion  # noqa: E402
from patrol_amr.mission_state import MissionStateSnapshot  # noqa: E402
from patrol_amr.mission_status_store import MissionStatusStore  # noqa: E402
from patrol_amr.mission_types import MissionOutcome, MissionType  # noqa: E402
from patrol_amr.patrol_report_outbox import PatrolReportOutbox  # noqa: E402
from patrol_interfaces.msg import PatrolReport, RobotStatus  # noqa: E402
import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402
from rclpy.qos import (  # noqa: E402
    DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy)


class Probe(Node):
    def __init__(self):
        super().__init__('amr07_smoke_probe')
        status_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        report_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=20,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.statuses = []
        self.reports = []
        self.create_subscription(
            RobotStatus, '/robot6/robot_status', self.statuses.append, status_qos)
        self.create_subscription(
            PatrolReport, '/robot6/patrol_report', self.reports.append, report_qos)


def main():
    runtime = tempfile.TemporaryDirectory(prefix='amr07-runtime-')
    root = Path(runtime.name)
    status_path = root / 'mission_status.json'
    outbox_path = root / 'patrol_report_outbox.json'
    MissionStatusStore(status_path).write(MissionStateSnapshot(
        mission='MISSION_FAILED',
        last_waypoint_index=3,
        outcome='FAILED',
        reason_code=303,
        reason='PATROL_GOAL_ABORTED',
        revision=4,
    ))
    PatrolReportOutbox(outbox_path).enqueue(MissionCompletion(
        command_id='cmd-ctrl-20260908T100000-robot6-start-0001',
        mission_id='msn-ctrl-20260908T100000-robot6-0001',
        robot_id='robot6',
        command=MissionType.START_PATROL,
        target_id='',
        outcome=MissionOutcome.FAILED,
        reason='PATROL_GOAL_ABORTED',
        reason_code=303,
        started_at_ns=1_000_000_002,
        finished_at_ns=3_000_000_004,
        final_waypoint_id='W4',
        related_event_ids=(),
    ), 'robot6-20260908T100000')

    command = [
        'ros2', 'run', 'patrol_amr', 'status_reporter', '--ros-args',
        '-r', '__ns:=/robot6',
        '-p', 'robot_id:=robot6',
        '-p', 'source_session_id:=robot6-20260908T100001',
        '-p', 'safety_state:=0',
        '-p', f'mission_status_path:={status_path}',
        '-p', f'report_outbox_path:={outbox_path}',
    ]
    log_path = root / 'status_reporter.log'
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
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(log_path.read_text(errors='replace'))
            rclpy.spin_once(probe, timeout_sec=0.05)
            if probe.statuses and probe.reports:
                break
        if not probe.statuses or not probe.reports:
            raise AssertionError(
                'timeout waiting for AMR-07 outputs\n'
                + log_path.read_text(errors='replace'))
        status = next(
            item for item in reversed(probe.statuses)
            if item.mission_state == RobotStatus.MISSION_FAILED)
        report = probe.reports[0]
        assert status.reason_code == 303
        assert status.reason == 'PATROL_GOAL_ABORTED'
        assert report.result == PatrolReport.FAILED
        assert report.reason_code == PatrolReport.NAV_GOAL_ABORTED
        assert report.final_waypoint_id == 'W4'
        assert report.started_at.sec == 1 and report.started_at.nanosec == 2
        assert PatrolReportOutbox(outbox_path).pending() == ()
        print('AMR07_STATUS_REPORTER_SMOKE_PASS')
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
