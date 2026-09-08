"""Validate public MissionCommand messages and build domain requests."""

from __future__ import annotations

import json
import math
import re

from patrol_amr.mission_types import (
    MissionRequest, MissionType, PoseTarget)


COMMAND_ID_PATTERN = re.compile(
    r'^cmd-ctrl-\d{8}T\d{6}(?:-\d+)?-'
    r'(?:robot1|robot6)-'
    r'(?:start|evacuate|resume|dock|stop|cancel)-\d{4,}$')
MISSION_ID_PATTERN = re.compile(
    r'^msn-ctrl-\d{8}T\d{6}(?:-\d+)?-'
    r'(?:robot1|robot6)-\d{4,}$')


class InvalidMissionCommand(ValueError):
    """A received command violates a confirmed public interface rule."""


class MissionCommandParser:
    """
    Convert a generated MissionCommand into a validated request.

    IDs are checked for traceability and duplicate handling only. Robot and
    command behavior always uses their dedicated message fields.
    """

    def __init__(self, robot_id: str) -> None:
        self._robot_id = robot_id

    def parse(self, msg) -> MissionRequest:
        command_id = str(getattr(msg, 'command_id', '')).strip()
        if not COMMAND_ID_PATTERN.fullmatch(command_id):
            raise InvalidMissionCommand(
                'command_id does not match the structured ID contract')

        mission_id = str(getattr(msg, 'mission_id', '')).strip()
        if not MISSION_ID_PATTERN.fullmatch(mission_id):
            raise InvalidMissionCommand(
                'mission_id does not match the structured ID contract')

        robot_id = str(getattr(msg, 'robot_id', '')).strip()
        if robot_id != self._robot_id:
            raise InvalidMissionCommand(
                f'robot_id {robot_id!r} does not match {self._robot_id!r}')
        try:
            command = MissionType(int(getattr(msg, 'command')))
        except (TypeError, ValueError, AttributeError) as exc:
            raise InvalidMissionCommand('unsupported command enum') from exc

        parameters_json = self._normalize_parameters(
            str(getattr(msg, 'parameters_json', '')).strip())
        target_pose = None
        if command is MissionType.MOVE_TO_SAFE_ZONE:
            target_pose = self._parse_safe_zone_pose(
                getattr(msg, 'target_pose', None))

        return MissionRequest(
            command_id=command_id,
            mission_id=mission_id,
            robot_id=robot_id,
            command=command,
            target_id=str(getattr(msg, 'target_id', '')).strip(),
            target_pose=target_pose,
            issued_by=str(getattr(msg, 'issued_by', '')).strip(),
            parameters_json=parameters_json,
        )

    @staticmethod
    def _normalize_parameters(raw: str) -> str:
        if not raw:
            return ''
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InvalidMissionCommand(
                'parameters_json is not valid JSON') from exc
        return json.dumps(value, sort_keys=True, separators=(',', ':'))

    @staticmethod
    def _parse_safe_zone_pose(pose) -> PoseTarget:
        if pose is None:
            raise InvalidMissionCommand(
                'MOVE_TO_SAFE_ZONE requires target_pose')
        frame_id = str(
            getattr(getattr(pose, 'header', None), 'frame_id', '')).strip()
        if frame_id != 'map':
            raise InvalidMissionCommand(
                'target_pose.header.frame_id must be map')
        try:
            position = pose.pose.position
            orientation = pose.pose.orientation
            values = (
                float(position.x), float(position.y),
                float(orientation.x), float(orientation.y),
                float(orientation.z), float(orientation.w),
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise InvalidMissionCommand('target_pose is incomplete') from exc
        if not all(math.isfinite(value) for value in values):
            raise InvalidMissionCommand(
                'target_pose contains a non-finite value')
        norm = math.sqrt(sum(value * value for value in values[2:]))
        if norm < 1e-6:
            raise InvalidMissionCommand(
                'target_pose orientation quaternion is invalid')
        x, y, qx, qy, qz, qw = values
        yaw_rad = math.atan2(
            2.0 * (qw * qz + qx * qy),
            1.0 - 2.0 * (qy * qy + qz * qz),
        )
        return PoseTarget(frame_id, x, y, math.degrees(yaw_rad))
