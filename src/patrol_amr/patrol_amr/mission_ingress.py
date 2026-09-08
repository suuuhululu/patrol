"""MissionCommand ingress decisions shared by a future ROS mission node.

This module joins the persistent command store to the fixed duplicate-handling
contract.  It deliberately does not execute command-specific behavior because
target schemas and the mission transition table remain TBD-IF-001 and
TBD-AMR-005.  Rejection reason codes are injected rather than guessed.
"""

from dataclasses import dataclass
from typing import Any, Optional

from patrol_amr import command_check
from patrol_amr import command_store


UINT32_MAX = 0xFFFFFFFF


@dataclass(frozen=True)
class IngressDecision:
    check_meaning: Optional[command_check.CheckMeaning]
    reason_code: int
    reason: str
    dispatch_new: bool
    replay_report: Any = None


class MissionIngress:
    """Classify one received command without running it more than once."""

    def __init__(
        self,
        store: command_store.CommandStore,
        *,
        invalid_reason_code: int,
        conflict_reason_code: int,
    ):
        if not isinstance(store, command_store.CommandStore):
            raise ValueError('store must be a CommandStore')
        self._store = store
        self._invalid_reason_code = _uint32(
            invalid_reason_code, 'invalid_reason_code'
        )
        self._conflict_reason_code = _uint32(
            conflict_reason_code, 'conflict_reason_code'
        )

    def observe(self, **command_fields) -> IngressDecision:
        """Return the exact response action for a wire command payload."""
        try:
            observed = self._store.register(**command_fields)
        except ValueError as error:
            return IngressDecision(
                check_meaning=command_check.CheckMeaning.REJECTED,
                reason_code=self._invalid_reason_code,
                reason=str(error),
                dispatch_new=False,
            )

        verdict = observed.verdict
        if verdict is command_store.RegisterVerdict.NEW:
            return IngressDecision(
                check_meaning=command_check.CheckMeaning.ACCEPTED,
                reason_code=0,
                reason='',
                dispatch_new=True,
            )
        if verdict is command_store.RegisterVerdict.DUPLICATE_ACCEPTED:
            return IngressDecision(
                check_meaning=command_check.CheckMeaning.ACCEPTED,
                reason_code=0,
                reason='',
                dispatch_new=False,
            )
        if verdict is command_store.RegisterVerdict.DUPLICATE_EXECUTING:
            return IngressDecision(
                check_meaning=command_check.CheckMeaning.EXECUTING,
                reason_code=0,
                reason='',
                dispatch_new=False,
            )
        if verdict is command_store.RegisterVerdict.DUPLICATE_COMPLETED:
            return IngressDecision(
                check_meaning=None,
                reason_code=0,
                reason='',
                dispatch_new=False,
                replay_report=self._store.completed_report(
                    command_fields['command_id']
                ),
            )
        if verdict is command_store.RegisterVerdict.COMMAND_ID_CONFLICT:
            return IngressDecision(
                check_meaning=command_check.CheckMeaning.REJECTED,
                reason_code=self._conflict_reason_code,
                reason='COMMAND_ID_CONFLICT',
                dispatch_new=False,
            )
        raise RuntimeError(f'unhandled register verdict: {verdict}')


def pose_stamped_payload(message) -> dict:
    """Copy every PoseStamped field into a JSON-compatible fingerprint."""
    try:
        return {
            'header': {
                'stamp': {
                    'sec': message.header.stamp.sec,
                    'nanosec': message.header.stamp.nanosec,
                },
                'frame_id': message.header.frame_id,
            },
            'pose': {
                'position': {
                    'x': message.pose.position.x,
                    'y': message.pose.position.y,
                    'z': message.pose.position.z,
                },
                'orientation': {
                    'x': message.pose.orientation.x,
                    'y': message.pose.orientation.y,
                    'z': message.pose.orientation.z,
                    'w': message.pose.orientation.w,
                },
            },
        }
    except AttributeError as error:
        raise ValueError('target_pose must have PoseStamped fields') from error


def mission_command_fields(message, *, received_at: float) -> dict:
    """Copy the exact CommandStore fingerprint fields from MissionCommand."""
    try:
        return {
            'command_id': message.command_id,
            'mission_id': message.mission_id,
            'robot_id': message.robot_id,
            'command': message.command,
            'target_id': message.target_id,
            'target_pose': pose_stamped_payload(message.target_pose),
            'parameters_json': message.parameters_json,
            'received_at': received_at,
        }
    except AttributeError as error:
        raise ValueError('message must have MissionCommand fields') from error


def _uint32(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= UINT32_MAX
    ):
        raise ValueError(f'{name} must be in uint32 range')
    return value
