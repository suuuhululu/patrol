"""ROS-independent mission command and execution value objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import hashlib
import json


class MissionType(IntEnum):
    """MissionCommand command values from docs/interfaces.md."""

    STOP = 0
    START_PATROL = 1
    MOVE_TO_SAFE_ZONE = 2
    RESUME_PATROL = 3
    DOCK = 4
    CANCEL = 5


class MissionOutcome(IntEnum):
    """PatrolReport result values from docs/interfaces.md."""

    SUCCEEDED = 0
    FAILED = 1
    CANCELED = 2


@dataclass(frozen=True)
class PoseTarget:
    """Normalized map-frame navigation target."""

    frame_id: str
    x: float
    y: float
    yaw_deg: float


@dataclass(frozen=True)
class MissionRequest:
    """Validated command independent of generated ROS message classes."""

    command_id: str
    mission_id: str
    robot_id: str
    command: MissionType
    target_id: str = ''
    target_pose: PoseTarget | None = None
    issued_by: str = ''
    parameters_json: str = ''

    def fingerprint(self) -> str:
        """Return stable content identity, excluding transport timestamps."""
        payload = {
            'robot_id': self.robot_id,
            'command': int(self.command),
            'mission_id': self.mission_id,
            'target_id': self.target_id,
            'target_pose': None if self.target_pose is None else {
                'frame_id': self.target_pose.frame_id,
                'x': self.target_pose.x,
                'y': self.target_pose.y,
                'yaw_deg': self.target_pose.yaw_deg,
            },
            'parameters_json': self.parameters_json,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
