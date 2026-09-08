"""Small ROS callback that submits an already validated mission request."""

from patrol_amr.mission_arbiter import (
    MissionArbiter, SubmissionResult)
from patrol_amr.mission_command_parser import InvalidMissionCommand


class MissionCommandCallback:
    """Callable used directly as the rclpy subscription callback."""

    def __init__(
        self,
        parser,
        arbiter: MissionArbiter,
        logger,
        readiness_summary=lambda: 'SAFETY_PATH_NOT_READY',
    ) -> None:
        self._parser = parser
        self._arbiter = arbiter
        self._logger = logger
        self._readiness_summary = readiness_summary

    def __call__(self, msg) -> None:
        try:
            request = self._parser.parse(msg)
        except InvalidMissionCommand as exc:
            self._logger.error(f'mission command rejected: {exc}')
            return
        result = self._arbiter.submit(request)
        if result is SubmissionResult.ACCEPTED:
            self._logger.info(
                f'mission command accepted: {request.command.name} '
                f'{request.command_id}')
        elif result is SubmissionResult.BUSY:
            self._logger.error(
                f'mission command rejected while busy: {request.command_id}')
        elif result is SubmissionResult.SAFETY_NOT_READY:
            reason = (
                self._arbiter.motion_disabled_reason
                or self._readiness_summary()
            )
            self._logger.error(
                f'motion command rejected ({reason}): '
                f'{request.command_id}')
        else:
            self._logger.error(
                f'mission command rejected during shutdown: '
                f'{request.command_id}')
