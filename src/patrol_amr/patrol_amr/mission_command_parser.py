"""Validate public MissionCommand messages and build domain requests."""

from __future__ import annotations

import math
import re

from patrol_amr.mission_types import MissionRequest, MissionType


COMMAND_ID_PATTERN = re.compile(
    r'^cmd-ctrl-\d{8}T\d{6}(?:-\d+)?-'
    r'(?:robot1|robot6)-'
    r'(?:start|evacuate|resume|dock|stop|cancel)-\d{4,}$')
MISSION_ID_PATTERN = re.compile(
    r'^msn-ctrl-\d{8}T\d{6}(?:-\d+)?-'
    r'(?:robot1|robot6)-\d{4,}$')


class InvalidMissionCommand(ValueError):
    """A received command violates a confirmed public interface rule."""

    def __init__(self, message: str, reason_code: int = 200):
        super().__init__(message)
        self.reason_code = reason_code


class MissionCommandParser:
    """
    Convert a generated MissionCommand into a validated request.

    IDs are checked for traceability and duplicate handling only. Robot and
    command behavior always uses their dedicated message fields.
    """

    def __init__(self, robot_id: str, patrol_plan_id: str | None = None) -> None:
        self._robot_id = robot_id
        self._patrol_plan_id = patrol_plan_id or f'{robot_id}_default'

    def parse(self, msg) -> MissionRequest:
        command_id = str(getattr(msg, 'command_id', '')).strip()
        if not COMMAND_ID_PATTERN.fullmatch(command_id):
            raise InvalidMissionCommand(
                'command_id does not match the structured ID contract')

        robot_id = str(getattr(msg, 'robot_id', '')).strip()
        if robot_id != self._robot_id:
            raise InvalidMissionCommand(
                f'robot_id {robot_id!r} does not match {self._robot_id!r}',
                reason_code=205,
            )
        try:
            command = MissionType(int(getattr(msg, 'command')))
        except (TypeError, ValueError, AttributeError) as exc:
            raise InvalidMissionCommand(
                'unsupported command enum', reason_code=202) from exc

        mission_id = str(getattr(msg, 'mission_id', '')).strip()
        if mission_id:
            if not MISSION_ID_PATTERN.fullmatch(mission_id):
                raise InvalidMissionCommand(
                    'mission_id does not match the structured ID contract',
                    reason_code=204,
                )
        elif command is not MissionType.STOP:
            raise InvalidMissionCommand(
                f'{command.name} requires mission_id', reason_code=204)

        target_id = str(getattr(msg, 'target_id', '')).strip()
        self._validate_target(command, target_id)

        # target_pose remains on the compatibility wire for now, but every
        # agreed command requires its default value and AMR never navigates
        # to a pose supplied through MissionCommand.
        if not self._target_pose_is_default(getattr(msg, 'target_pose', None)):
            raise InvalidMissionCommand(
                'target_pose is unused and must be empty', reason_code=205)

        return MissionRequest(
            command_id=command_id,
            mission_id=mission_id,
            robot_id=robot_id,
            command=command,
            target_id=target_id,
            target_pose=None,
            issued_by=str(getattr(msg, 'issued_by', '')).strip(),
        )

    def _validate_target(self, command: MissionType, target_id: str) -> None:
        if command is MissionType.START_PATROL:
            if not target_id:
                raise InvalidMissionCommand(
                    'START_PATROL requires patrol_plan_id in target_id',
                    reason_code=205,
                )
            if target_id != self._patrol_plan_id:
                raise InvalidMissionCommand(
                    f'unknown patrol_plan_id: {target_id}', reason_code=201)
            return
        if command is MissionType.DOCK:
            expected = 'dock_1' if self._robot_id == 'robot1' else 'dock_6'
            if target_id != expected:
                raise InvalidMissionCommand(
                    f'DOCK target_id must be {expected}', reason_code=201)
            return
        if target_id:
            raise InvalidMissionCommand(
                f'{command.name} requires an empty target_id', reason_code=205)

    @staticmethod
    def _target_pose_is_default(pose) -> bool:
        if pose is None:
            return True
        try:
            header = pose.header
            stamp = header.stamp
            position = pose.pose.position
            orientation = pose.pose.orientation
            position_values = (
                float(position.x), float(position.y), float(position.z))
            orientation_values = (
                float(orientation.x), float(orientation.y),
                float(orientation.z), float(orientation.w))
        except (AttributeError, TypeError, ValueError) as exc:
            raise InvalidMissionCommand(
                'target_pose is incomplete', reason_code=205) from exc
        if not all(math.isfinite(value) for value in (
            *position_values, *orientation_values
        )):
            raise InvalidMissionCommand(
                'target_pose contains a non-finite value', reason_code=205)
        return (
            str(header.frame_id).strip() == ''
            and stamp.sec == 0
            and stamp.nanosec == 0
            and position_values == (0.0, 0.0, 0.0)
            and orientation_values == (0.0, 0.0, 0.0, 1.0)
        )
