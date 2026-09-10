#!/usr/bin/env python3
"""Isolated ROS smoke test for AMR-07 RobotStatus and PatrolReport."""

import os
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import time


os.environ['ROS_DOMAIN_ID'] = os.environ.get('AMR07_SMOKE_DOMAIN_ID', '126')
os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
for key in ('ROS_DISCOVERY_SERVER', 'ROS_SUPER_CLIENT', 'ROS_LOCALHOST_ONLY',
            'FASTRTPS_DEFAULT_PROFILES_FILE', 'FASTDDS_DEFAULT_PROFILES_FILE'):
    os.environ.pop(key, None)
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
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from std_msgs.msg import UInt8


class Probe(Node):
    def __init__(self):
        super().__init__('amr07_smoke_probe')
        status_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.report_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=20,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.statuses = []
        self.reports = []
        self.create_subscription(
            RobotStatus, '/robot6/robot_status', self.statuses.append, status_qos)
        self.odometry = self.create_publisher(Odometry, '/patrol_report_test/odom', qos_profile_sensor_data)
        self.safety = self.create_publisher(UInt8, '/patrol_report_test/safety_state', QoSProfile(
            depth=1, reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL))

    def subscribe_reports(self):
        return self.create_subscription(
            PatrolReport, '/robot6/patrol_report', self.reports.append, self.report_qos)


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)


def wait_for(probe, process, predicate, log_path, description, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(log_path.read_text(errors='replace'))
        rclpy.spin_once(probe, timeout_sec=0.05)
        if predicate():
            return
    raise AssertionError(f'timeout: {description}\n' + log_path.read_text(errors='replace'))


def observe_for(probe, process, log_path, seconds=0.8):
    deadline = time.monotonic() + seconds
    wait_for(probe, process, lambda: time.monotonic() >= deadline,
             log_path, 'observation window', timeout=seconds + 2)


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
    retained = PatrolReportOutbox(outbox_path).enqueue(MissionCompletion(
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
        'ros2', 'run', 'patrol_amr_safety', 'status_reporter', '--ros-args',
        '-r', '__ns:=/robot6',
        '-p', 'robot_id:=robot6',
        '-p', 'source_session_id:=robot6-20260908T100001',
        '-p', f'mission_status_path:={status_path}',
        '-p', f'report_outbox_path:={outbox_path}',
        '-r', 'odom:=/patrol_report_test/odom',
        '-r', 'safety_state:=/patrol_report_test/safety_state',
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
        wait_for(probe, process, lambda: any(
            item.mission_state == RobotStatus.MISSION_FAILED for item in probe.statuses),
            log_path, 'status while report subscriber absent')
        observe_for(probe, process, log_path)
        assert PatrolReportOutbox(outbox_path).pending() == (retained,)

        # Restart production reporter with the same on-disk files and a new session.
        stop(process)
        command[command.index('source_session_id:=robot6-20260908T100001')] = (
            'source_session_id:=robot6-20260908T100002')
        with log_path.open('a') as log:
            process = subprocess.Popen(
                command, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True, env=os.environ.copy())
        wait_for(probe, process, lambda: any(
            item.source_session_id == 'robot6-20260908T100002'
            and item.mission_state == RobotStatus.MISSION_FAILED
            for item in probe.statuses), log_path, 'restored status after restart')
        observe_for(probe, process, log_path)
        assert PatrolReportOutbox(outbox_path).pending() == (retained,)
        valid_outbox = outbox_path.read_text()
        damaged = json.loads(valid_outbox)
        damaged['pending'][retained.command_id]['finished_at_ns'] = (2 ** 31) * 1_000_000_000
        invalid_outbox = json.dumps(damaged)
        outbox_path.write_text(invalid_outbox)
        probe.subscribe_reports()
        before = len(probe.statuses)
        observe_for(probe, process, log_path, seconds=1.0)
        assert probe.statuses[before:], 'status stream stopped on report conversion failure'
        assert probe.reports == []
        assert outbox_path.read_text() == invalid_outbox
        assert 'cannot publish pending report' in log_path.read_text()
        outbox_path.write_text(valid_outbox)
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
        assert report.report_id == retained.report_id
        assert report.source_session_id == retained.source_session_id
        assert status.reason_code == 303
        assert status.reason == 'PATROL_GOAL_ABORTED'
        assert report.result == PatrolReport.FAILED
        assert report.reason_code == PatrolReport.NAV_GOAL_ABORTED
        assert report.final_waypoint_id == 'W4'
        assert report.started_at.sec == 1 and report.started_at.nanosec == 2
        wait_for(probe, process, lambda: PatrolReportOutbox(outbox_path).pending() == (),
                 log_path, 'published report removed')

        for malformed in ('{', '{"schema_version": 999}'):
            status_path.write_text(malformed)
            start = len(probe.statuses)
            observe_for(probe, process, log_path)
            assert probe.statuses[start:]
            assert all(item.mission_state == RobotStatus.MISSION_FAILED
                       and item.reason_code == 303 for item in probe.statuses[start:])
        MissionStatusStore(status_path).write(MissionStateSnapshot(
            mission='MISSION_PATROLLING', revision=3))
        start = len(probe.statuses)
        observe_for(probe, process, log_path)
        assert probe.statuses[start:]
        assert all(item.mission_state == RobotStatus.MISSION_FAILED
                   for item in probe.statuses[start:])
        MissionStatusStore(status_path).write(MissionStateSnapshot(
            mission='MISSION_PATROLLING', revision=5))
        wait_for(probe, process, lambda: probe.statuses[-1].mission_state
                 == RobotStatus.MISSION_PATROLLING, log_path, 'new valid revision recovers')
        for index, outcome, reason in (
            (2, MissionOutcome.SUCCEEDED, 0),
            (3, MissionOutcome.CANCELED, PatrolReport.CONTROL_CANCELED),
        ):
            expected = PatrolReportOutbox(outbox_path).enqueue(MissionCompletion(
                command_id=f'cmd-ctrl-20260908T100000-robot6-start-{index:04d}',
                mission_id=f'msn-ctrl-20260908T100000-robot6-{index:04d}',
                robot_id='robot6', command=MissionType.START_PATROL, target_id='',
                outcome=outcome, reason='' if reason == 0 else 'CONTROL_CANCELED',
                reason_code=reason, started_at_ns=1_000_000_002,
                finished_at_ns=3_000_000_004, final_waypoint_id='W4',
                related_event_ids=('event-1',)), 'robot6-20260908T100000')
            wait_for(probe, process, lambda: any(
                item.report_id == expected.report_id for item in probe.reports),
                log_path, f'{outcome.name} report')
            received = next(item for item in probe.reports if item.report_id == expected.report_id)
            assert received.result == int(outcome)
            assert received.command_id == expected.command_id
            assert received.mission_id == expected.mission_id
            assert received.reason_code == reason
            assert received.related_event_ids == ['event-1']
            wait_for(probe, process, lambda: PatrolReportOutbox(outbox_path).pending() == (),
                     log_path, 'result drained')
        # Temporary reporting rules are exercised through the production node.
        probe.safety.publish(UInt8(data=RobotStatus.SAFETY_NORMAL))
        for linear, expected_op, expected_scan, duration in (
            (0.2, RobotStatus.OP_MOVING, 'MOVING_TO_WAYPOINT', 0.8),
            (0.0, RobotStatus.OP_READY, 'SCANNING', 1.0),
        ):
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                odom = Odometry()
                odom.header.stamp = probe.get_clock().now().to_msg()
                odom.twist.twist.linear.x = linear
                probe.odometry.publish(odom)
                rclpy.spin_once(probe, timeout_sec=0.04)
            wait_for(probe, process, lambda: (
                probe.statuses[-1].operational_state == expected_op
                and probe.statuses[-1].docking_state == RobotStatus.DOCK_UNDOCKED
                and probe.statuses[-1].scan_state == expected_scan
            ), log_path, f'provisional axes {expected_scan}')
        MissionStatusStore(status_path).write(MissionStateSnapshot(
            mission='MISSION_DOCKING', revision=6))
        wait_for(probe, process, lambda: probe.statuses[-1].docking_state == RobotStatus.DOCK_DOCKING,
                 log_path, 'provisional docking started')
        MissionStatusStore(status_path).write(MissionStateSnapshot(
            mission='MISSION_COMPLETED', outcome='SUCCEEDED', revision=7))
        wait_for(probe, process, lambda: (
            probe.statuses[-1].docking_state == RobotStatus.DOCK_DOCKED
            and probe.statuses[-1].scan_state == 'COMPLETED'
        ), log_path, 'provisional docking completed')
        print('AMR07_STATUS_REPORTER_SMOKE_PASS')
        print('recovery=no_subscriber_retention,restart_same_report_id,invalid_report_time_preserved,corrupt_and_old_snapshot_retained,new_revision_recovers')
        print('results=FAILED,SUCCEEDED,CANCELED')
        print('provisional_axes=operational,docking,scan_connected')
    finally:
        probe.destroy_node()
        rclpy.shutdown()
        stop(process)
        runtime.cleanup()
        _ROS_LOG.cleanup()


if __name__ == '__main__':
    main()
