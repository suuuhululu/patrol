#!/usr/bin/env python3
"""Run both safety launches on one isolated ROS domain; no robot or Nav2."""

import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import tempfile
import time

os.environ['ROS_DOMAIN_ID'] = os.environ.get('PATROL_DUAL_SMOKE_DOMAIN_ID', '129')
os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
for key in ('ROS_DISCOVERY_SERVER', 'ROS_SUPER_CLIENT',
            'FASTRTPS_DEFAULT_PROFILES_FILE', 'FASTDDS_DEFAULT_PROFILES_FILE'):
    os.environ.pop(key, None)

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, qos_profile_sensor_data
from geometry_msgs.msg import Twist, TwistStamped
from sensor_msgs.msg import BatteryState
from patrol_interfaces.msg import ControlHeartbeat, DriveToken, EStop, MissionCommand, RobotStatus
from std_msgs.msg import Bool
from patrol_amr.mission_state import MissionStateSnapshot
from patrol_amr.mission_status_store import MissionStatusStore

ROBOTS = ('robot1', 'robot6')
CONTROL = '/patrol_dual/control'
SESSION = 'ctrl-20260908T231500'


def qos(depth=10, *, best_effort=False, retained=False):
    return QoSProfile(depth=depth,
        reliability=ReliabilityPolicy.BEST_EFFORT if best_effort else ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL if retained else DurabilityPolicy.VOLATILE)


class Probe(Node):
    def __init__(self):
        super().__init__('patrol_dual_probe')
        self.status = {robot: [] for robot in ROBOTS}
        self.velocity = {robot: [] for robot in ROBOTS}
        self.motion = {robot: [] for robot in ROBOTS}
        self.dispatch = {robot: [] for robot in ROBOTS}
        self.candidates = {}
        self.batteries = {}
        self.commands = {}
        self.holder = 'robot1'
        self.sequence = 0
        self.estop_sequence = 0
        self.heartbeat = self.create_publisher(ControlHeartbeat, CONTROL + '/heartbeat', qos(3, best_effort=True))
        self.token = self.create_publisher(DriveToken, CONTROL + '/drive_token', qos(3, best_effort=True))
        self.estop = self.create_publisher(EStop, CONTROL + '/estop', qos(1, retained=True))
        for robot in ROBOTS:
            ns = f'/patrol_dual/{robot}'
            self.create_subscription(RobotStatus, f'/{robot}/robot_status', self.status[robot].append, qos(20))
            self.create_subscription(Twist, ns + '/cmd_vel', self.velocity[robot].append, qos(1))
            self.create_subscription(Bool, ns + '/motion_allowed', self.motion[robot].append, qos(1, retained=True))
            self.create_subscription(MissionCommand, f'/{robot}/mission_dispatch', self.dispatch[robot].append, qos())
            self.commands[robot] = self.create_publisher(MissionCommand, f'/{robot}/mission_command', qos())
            self.candidates[robot] = self.create_publisher(TwistStamped, ns + '/cmd_vel_safe', qos(1))
            self.batteries[robot] = self.create_publisher(BatteryState, ns + '/battery_state', qos_profile_sensor_data)
        self.create_timer(0.1, self.publish_inputs)

    def publish_inputs(self):
        self.sequence += 1
        heartbeat = ControlHeartbeat()
        heartbeat.control_session_id = SESSION
        heartbeat.sequence = self.sequence
        heartbeat.header.stamp = self.get_clock().now().to_msg()
        self.heartbeat.publish(heartbeat)
        token = DriveToken()
        token.control_session_id = SESSION
        token.token_id = f'tok-dual-{self.holder}'
        token.holder_robot_id = self.holder
        token.message_sequence = self.sequence
        token.lease_duration.sec = 1
        self.token.publish(token)
        for robot in ROBOTS:
            candidate = TwistStamped()
            candidate.header.stamp = self.get_clock().now().to_msg()
            candidate.twist.linear.x = 0.12 if robot == 'robot1' else 0.24
            self.candidates[robot].publish(candidate)
            battery = BatteryState()
            battery.header.stamp = self.get_clock().now().to_msg()
            battery.present = True
            battery.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_DISCHARGING
            battery.percentage = 0.15 if robot == 'robot1' else 0.65
            self.batteries[robot].publish(battery)

    def set_estop(self, target, active):
        self.estop_sequence += 1
        message = EStop()
        message.target_robot_id = target
        message.active = active
        message.reason = 2 if active else 0
        message.sequence = self.estop_sequence
        self.estop.publish(message)


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)


def main():
    with tempfile.TemporaryDirectory(prefix='patrol-dual-') as directory:
        root = Path(directory)
        os.environ['ROS_LOG_DIR'] = str(root / 'ros_logs')
        processes = []
        logs = []
        rclpy.init()
        probe = Probe()

        def wait(predicate, description, timeout=12):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if any(process.poll() is not None for process in processes):
                    raise AssertionError('launch exited\n' + '\n'.join(path.read_text() for path in logs))
                rclpy.spin_once(probe, timeout_sec=0.03)
                if predicate():
                    return
            raise AssertionError(f'timeout: {description}\n' + '\n'.join(path.read_text() for path in logs))

        def settle(seconds=0.5):
            until = time.monotonic() + seconds
            wait(lambda: time.monotonic() >= until, 'settle', seconds + 2)

        def latest_velocity(robot):
            return probe.velocity[robot][-1].linear.x if probe.velocity[robot] else None

        try:
            for robot in ROBOTS:
                runtime = root / robot
                MissionStatusStore(runtime / 'mission_status.json').write(MissionStateSnapshot(
                    mission='MISSION_PATROLLING' if robot == 'robot1' else 'MISSION_PAUSED',
                    mission_id=f'msn-{SESSION}-{robot}-0001',
                    command_id=f'cmd-{SESSION}-{robot}-start-0001', revision=1))
                ns = f'/patrol_dual/{robot}'
                command = ['ros2', 'launch', 'patrol_amr_safety', 'amr_safety_status.launch.py',
                    f'robot_id:={robot}', f'source_session_id:={robot}-20260908T231500',
                    f'database_path:={runtime / "commands.sqlite3"}',
                    f'mission_status_path:={runtime / "mission_status.json"}',
                    f'report_outbox_path:={runtime / "outbox.json"}']
                for argument, topic in {
                    'battery_state': 'battery_state', 'battery_status': 'battery_status',
                    'candidate': 'cmd_vel_safe', 'output': 'cmd_vel', 'odom': 'odom',
                    'pose': 'amcl_pose', 'motion_allowed': 'motion_allowed',
                    'safety_state': 'safety_state', 'accepted_token': 'accepted_token_id',
                }.items():
                    command.append(f'{argument}_topic:={ns}/{topic}')
                for topic in ('drive_token', 'heartbeat', 'estop'):
                    command.append(f'{topic}_topic:={CONTROL}/{topic}')
                log_path = runtime / 'launch.log'
                logs.append(log_path)
                with log_path.open('w') as log:
                    processes.append(subprocess.Popen(command, stdout=log,
                        stderr=subprocess.STDOUT, start_new_session=True))
            wait(lambda: probe.estop.get_subscription_count() == 2
                 and all(probe.commands[r].get_subscription_count() == 1 for r in ROBOTS),
                 'two independent launches')
            probe.set_estop('all', False)
            wait(lambda: latest_velocity('robot1') == 0.12 and latest_velocity('robot6') == 0.0,
                 'robot1 holds token exclusively')
            wait(lambda: all(probe.status[r] for r in ROBOTS)
                 and probe.status['robot1'][-1].battery_state == RobotStatus.LOW
                 and probe.status['robot6'][-1].battery_state == RobotStatus.NORMAL,
                 'separate battery classification')
            for robot in ROBOTS:
                statuses = probe.status[robot]
                assert all(status.robot_id == robot for status in statuses)
                assert statuses[-1].active_mission_id == f'msn-{SESSION}-{robot}-0001'
                expected = RobotStatus.MISSION_PATROLLING if robot == 'robot1' else RobotStatus.MISSION_PAUSED
                assert statuses[-1].mission_state == expected
                publishers = probe.get_publishers_info_by_topic(f'/patrol_dual/{robot}/cmd_vel')
                assert [(p.node_name, p.node_namespace) for p in publishers] == [('local_safety_supervisor', f'/{robot}')]
                assert probe.get_publishers_info_by_topic(f'/{robot}/cmd_vel') == []

            # No Nav2/mission owner exists; these commands can only reach probes.
            for robot in ROBOTS:
                command = MissionCommand()
                command.robot_id = robot
                command.command_id = f'cmd-{SESSION}-{robot}-start-0001'
                command.mission_id = f'msn-{SESSION}-{robot}-0001'
                command.command = MissionCommand.START_PATROL
                command.target_id = f'{robot}_default'
                probe.commands[robot].publish(command)
            wait(lambda: all(len(probe.dispatch[r]) == 1 for r in ROBOTS), 'one dispatch per namespace')
            for robot in ROBOTS:
                assert probe.dispatch[robot][0].robot_id == robot
                with sqlite3.connect(root / robot / 'commands.sqlite3') as database:
                    rows = database.execute('SELECT command_id FROM mission_commands').fetchall()
                assert rows == [(f'cmd-{SESSION}-{robot}-start-0001',)]

            # Test token handoff only after an explicit stop of the old holder.
            probe.set_estop('robot1', True)
            wait(lambda: latest_velocity('robot1') == 0.0, 'old holder stopped at test sink')
            probe.holder = 'robot6'
            wait(lambda: latest_velocity('robot1') == 0.0 and latest_velocity('robot6') == 0.24,
                 'robot6 token with robot1-only estop')
            settle()
            assert probe.motion['robot1'][-1].data is False
            assert probe.motion['robot6'][-1].data is True
            probe.set_estop('all', True)
            wait(lambda: all(latest_velocity(r) == 0.0 for r in ROBOTS), 'all-target estop')
            print('AMR_DUAL_NAMESPACE_SMOKE_PASS')
            print('isolation=two_launches,one_domain,separate_status_mission_battery_command_database')
            print('motion=exclusive_token_holder,targeted_estop,all_estop,one_publisher_per_test_sink')
            print(f'ros_domain_id={os.environ["ROS_DOMAIN_ID"]}')
        finally:
            for process in reversed(processes):
                stop(process)
            probe.destroy_node()
            rclpy.shutdown()


if __name__ == '__main__':
    main()
