"""Unit tests for the ROS-independent patrol Control Server state."""

from patrol_control.control_core import ControlCore
from patrol_control.control_core import ControlStateError
from patrol_control.control_core import EventType
from patrol_control.control_core import PatrolCommandType
from patrol_control.control_core import TaskState
import pytest


ROBOTS = ('robot1', 'robot6')


def make_core() -> ControlCore:
    return ControlCore(ROBOTS, token_factory=lambda: 'token-1')


def start_and_accept(core: ControlCore, robot_id: str = 'robot1') -> None:
    core.observe_permit(True)
    core.prepare_goal(robot_id)
    core.mark_goal_accepted(robot_id)


def test_goal_requires_positive_permit() -> None:
    core = make_core()

    with pytest.raises(ControlStateError, match='not allowed'):
        core.prepare_goal('robot1')

    core.observe_permit(True)
    intent = core.prepare_goal('robot1')

    assert intent.robot_id == 'robot1'
    assert intent.command_id == 'cmd-robot1-start-000001'


def test_waiting_feedback_is_required_before_token_grant() -> None:
    core = make_core()
    start_and_accept(core)

    before = core.token_frames()
    effect = core.observe_feedback(
        'robot1',
        task_state=TaskState.PATROLLING,
        event_type=0,
        event_id='',
    )
    after_non_waiting = core.token_frames()
    grant = core.observe_feedback(
        'robot1',
        task_state=TaskState.WAITING_FOR_TOKEN,
        event_type=0,
        event_id='',
    )
    after_grant = core.token_frames()

    assert effect.accepted is True
    assert effect.token_granted is False
    assert all(frame.token == '' for frame in before)
    assert all(frame.token == '' for frame in after_non_waiting)
    assert grant.token_granted is True
    assert after_grant[0].token == 'token-1'
    assert after_grant[1].token == ''
    assert [frame.sequence for frame in after_grant] == [3, 3]


def test_permit_edges_create_one_command_for_active_goal() -> None:
    core = make_core()
    start_and_accept(core)

    evacuate = core.observe_permit(False)
    duplicate = core.observe_permit(False)
    resume = core.observe_permit(True)

    assert len(evacuate) == 1
    assert evacuate[0].command is PatrolCommandType.MOVE_TO_SAFE_ZONE
    assert duplicate == ()
    assert len(resume) == 1
    assert resume[0].command is PatrolCommandType.RESUME_PATROL
    assert evacuate[0].command_id != resume[0].command_id


def test_waiting_feedback_does_not_grant_token_while_permit_is_false() -> None:
    core = make_core()
    start_and_accept(core)
    core.observe_permit(False)

    effect = core.observe_feedback(
        'robot1',
        task_state=TaskState.WAITING_FOR_TOKEN,
        event_type=0,
        event_id='',
    )

    assert effect.accepted is True
    assert effect.token_granted is False
    assert core.token_frames()[0].token == ''


def test_fire_feedback_holds_the_next_patrol() -> None:
    core = make_core()
    start_and_accept(core)
    core.observe_feedback(
        'robot1',
        task_state=TaskState.WAITING_FOR_TOKEN,
        event_type=0,
        event_id='',
    )

    effect = core.observe_feedback(
        'robot1',
        task_state=TaskState.DETECTION_CONFIRMED,
        event_type=EventType.FIRE,
        event_id='9b3d2aa3-235d-46d0-93ae-63f207730123',
    )

    assert effect.fire_hold_activated is True
    assert core.token_frames()[0].token == 'token-1'

    core.finish_goal('robot1')
    with pytest.raises(ControlStateError, match='fire hold'):
        core.prepare_goal('robot6')

    core.clear_fire_hold()
    assert core.prepare_goal('robot6').robot_id == 'robot6'


def test_cancel_revoke_keeps_goal_until_action_result() -> None:
    core = make_core()
    start_and_accept(core)
    core.observe_feedback(
        'robot1',
        task_state=TaskState.WAITING_FOR_TOKEN,
        event_type=0,
        event_id='',
    )

    core.revoke_drive('robot1')

    assert core.active_robot_id == 'robot1'
    assert core.token_frames()[0].token == ''
    core.finish_goal('robot1')
    assert core.active_robot_id is None


def test_feedback_from_non_active_robot_is_ignored() -> None:
    core = make_core()
    start_and_accept(core)

    effect = core.observe_feedback(
        'robot6',
        task_state=TaskState.WAITING_FOR_TOKEN,
        event_type=0,
        event_id='',
    )

    assert effect.accepted is False
    assert all(frame.token == '' for frame in core.token_frames())
