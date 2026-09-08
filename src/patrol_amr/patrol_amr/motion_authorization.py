"""Local launch authorization for commands that can move real hardware."""

from __future__ import annotations


def expected_motion_token(robot_id: str) -> str:
    """Return the deliberate operator token for one robot."""
    return f'ENABLE_{robot_id.upper()}_MOTION'


def motion_launch_authorized(
    robot_id: str,
    safety_path_ready: bool,
    hardware_test_mode: bool,
    motion_enable_token: str,
) -> bool:
    """Require an implemented drive path and an exact robot-specific token."""
    drive_path_selected = safety_path_ready or hardware_test_mode
    return (
        drive_path_selected
        and motion_enable_token == expected_motion_token(robot_id)
    )


def authorization_blockers(
    robot_id: str,
    safety_path_ready: bool,
    hardware_test_mode: bool,
    motion_enable_token: str,
) -> tuple[str, ...]:
    """Describe why hardware motion remains blocked."""
    blockers = []
    if not safety_path_ready and not hardware_test_mode:
        blockers.append('NO_DRIVE_PATH_SELECTED')
    if motion_enable_token != expected_motion_token(robot_id):
        blockers.append('MOTION_ENABLE_TOKEN_MISMATCH')
    return tuple(blockers)
