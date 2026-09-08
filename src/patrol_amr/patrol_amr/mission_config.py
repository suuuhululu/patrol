"""Parameter validation for mission_supervisor."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from patrol_amr.motion_authorization import motion_launch_authorized
from patrol_amr.navigation_types import Waypoint
from patrol_amr.waypoint_repository import load_waypoints


@dataclass(frozen=True)
class MissionConfig:
    """Validated runtime configuration loaded from one ROS node."""

    robot_id: str
    patrol_plan_id: str
    waypoints: tuple[Waypoint, ...]
    waypoint_dwell_s: float
    resume_policy: str
    command_store_path: Path
    mission_status_path: Path
    report_outbox_path: Path
    source_session_id: str
    safety_path_ready: bool
    hardware_test_mode: bool
    motion_enable_token: str
    dock_timeout_s: float
    dock_sensor_stable_s: float

    @property
    def initialize_navigation(self) -> bool:
        """Return whether this launch may create hardware navigation clients."""
        return motion_launch_authorized(
            self.robot_id,
            self.safety_path_ready,
            self.hardware_test_mode,
            self.motion_enable_token,
        )


def declare_parameters(node) -> None:
    """Declare parameters owned by the mission integration feature."""
    node.declare_parameter('robot_id', 'robot1')
    node.declare_parameter('patrol_plan_id', '')
    node.declare_parameter('waypoints_xyyaw', [0.0])
    node.declare_parameter('waypoint_dwell_s', 0.0)
    node.declare_parameter('resume_policy', 'next_waypoint')
    node.declare_parameter('command_store_path', '')
    node.declare_parameter('mission_status_path', '')
    node.declare_parameter('report_outbox_path', '')
    node.declare_parameter('source_session_id', '')
    node.declare_parameter('safety_path_ready', False)
    node.declare_parameter('hardware_test_mode', False)
    node.declare_parameter('motion_enable_token', '')
    node.declare_parameter('dock_timeout_s', 60.0)
    node.declare_parameter('dock_sensor_stable_s', 2.0)


def load_config(node) -> MissionConfig:
    """Read and validate all mission parameters after declaration."""
    robot_id = str(node.get_parameter('robot_id').value)
    if robot_id not in {'robot1', 'robot6'}:
        raise ValueError('robot_id must be robot1 or robot6')
    namespace = node.get_namespace().strip('/')
    if namespace != robot_id:
        raise ValueError(
            f'namespace /{namespace} and robot_id {robot_id} do not match')

    waypoints = load_waypoints(
        node.get_parameter('waypoints_xyyaw').value)

    dwell_s = float(node.get_parameter('waypoint_dwell_s').value)
    dock_timeout_s = float(node.get_parameter('dock_timeout_s').value)
    dock_stable_s = float(node.get_parameter('dock_sensor_stable_s').value)
    if dwell_s < 0.0:
        raise ValueError('waypoint_dwell_s must be non-negative')
    if dock_timeout_s <= 0.0 or dock_stable_s <= 0.0:
        raise ValueError('docking times must be positive')
    if dock_stable_s > dock_timeout_s:
        raise ValueError('dock_sensor_stable_s cannot exceed dock_timeout_s')

    resume_policy = str(node.get_parameter('resume_policy').value)
    if resume_policy != 'next_waypoint':
        raise ValueError(
            'resume_policy must be next_waypoint under the 2026-09-09 '
            'AMR command/mission contract')
    runtime_root = Path(
        os.environ.get('ROS_HOME', str(Path.home() / '.ros'))
    ).expanduser() / 'patrol_amr' / robot_id

    def configured_path(parameter_name: str, file_name: str) -> Path:
        value = str(node.get_parameter(parameter_name).value)
        return Path(value).expanduser() if value else runtime_root / file_name

    source_session_id = str(node.get_parameter('source_session_id').value)
    if not source_session_id:
        raise ValueError('source_session_id must be non-empty')
    return MissionConfig(
        robot_id=robot_id,
        patrol_plan_id=(
            str(node.get_parameter('patrol_plan_id').value)
            or f'{robot_id}_default'
        ),
        waypoints=waypoints,
        waypoint_dwell_s=dwell_s,
        resume_policy=resume_policy,
        command_store_path=configured_path(
            'command_store_path', 'command_store.json'),
        mission_status_path=configured_path(
            'mission_status_path', 'mission_status.json'),
        report_outbox_path=configured_path(
            'report_outbox_path', 'patrol_report_outbox.json'),
        source_session_id=source_session_id,
        safety_path_ready=bool(
            node.get_parameter('safety_path_ready').value),
        hardware_test_mode=bool(
            node.get_parameter('hardware_test_mode').value),
        motion_enable_token=str(
            node.get_parameter('motion_enable_token').value),
        dock_timeout_s=dock_timeout_s,
        dock_sensor_stable_s=dock_stable_s,
    )
