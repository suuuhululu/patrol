"""Unit tests for the ROS-independent patrol control state machine."""

from patrol_control.control_core import ControlCore
from patrol_control.control_core import ControlStateError
from patrol_control.control_core import EventType
from patrol_control.control_core import PatrolCommandType
from patrol_control.control_core import TaskState
import pytest


ROBOTS = ('robot1', 'robot6')


def make_core(*, token: str = 'token-1') -> ControlCore:
    """Create a deterministic core for assertions involving DriveToken."""
    return ControlCore(ROBOTS, token_factory=lambda: token)


def start_and_accept(core: ControlCore, robot_id: str = 'robot1') -> None:
    """Create an accepted goal under a positive CCTV permit."""
    core.observe_permit(True)
    core.prepare_goal(robot_id)
    core.mark_goal_accepted(robot_id)


@pytest.mark.parametrize(
    'robot_ids',
    [(), ('robot1', 'robot1'), ('robot1', '')],
)
def test_robot_ids_must_be_non_empty_unique_and_populated(robot_ids) -> None:
    with pytest.raises(ValueError, match='robot_ids'):
        ControlCore(robot_ids)


def test_goal_requires_known_robot_and_positive_permit() -> None:
    core = make_core()

    with pytest.raises(ValueError, match='unknown robot_id'):
        core.prepare_goal('robot9')
    with pytest.raises(ControlStateError, match='not allowed'):
        core.prepare_goal('robot1')

    core.observe_permit(True)
    intent = core.prepare_goal('robot1')

    assert intent.robot_id == 'robot1'
    assert intent.command_id == 'cmd-robot1-start-000001'


def test_only_one_active_goal_can_be_reserved() -> None:
    core = make_core()
    core.observe_permit(True)
    core.prepare_goal('robot1')

    with pytest.raises(ControlStateError, match='already exists'):
        core.prepare_goal('robot6')


def test_goal_acceptance_must_match_the_active_robot() -> None:
    core = make_core()
    core.observe_permit(True)
    core.prepare_goal('robot1')

    with pytest.raises(ControlStateError, match='not the active'):
        core.mark_goal_accepted('robot6')


def test_waiting_feedback_is_required_before_token_grant() -> None:
    core = make_core()
    start_and_accept(core)

    patrolling = core.observe_feedback(
        'robot1',
        task_state=TaskState.PATROLLING,
        event_type=0,
        event_id='',
    )
    waiting = core.observe_feedback(
        'robot1',
        task_state=TaskState.WAITING_FOR_TOKEN,
        event_type=0,
        event_id='',
    )
    duplicate = core.observe_feedback(
        'robot1',
        task_state=TaskState.WAITING_FOR_TOKEN,
        event_type=0,
        event_id='',
    )

    assert patrolling.accepted
    assert not patrolling.token_granted
    assert waiting.token_granted
    assert not duplicate.token_granted
    assert core.drive_granted
    assert core.active_token == 'token-1'


def test_waiting_feedback_cannot_grant_token_without_positive_permit() -> None:
    core = make_core()
    start_and_accept(core)
    core.observe_permit(False)

    effect = core.observe_feedback(
        'robot1',
        task_state=TaskState.WAITING_FOR_TOKEN,
        event_type=0,
        event_id='',
    )

    assert effect.accepted
    assert not effect.token_granted
    assert not core.drive_granted


def test_feedback_from_non_active_robot_or_unknown_state_is_ignored() -> None:
    core = make_core()
    start_and_accept(core)

    wrong_robot = core.observe_feedback(
        'robot6',
        task_state=TaskState.WAITING_FOR_TOKEN,
        event_type=0,
        event_id='',
    )
    unknown_state = core.observe_feedback(
        'robot1',
        task_state=999,
        event_type=0,
        event_id='',
    )

    assert not wrong_robot.accepted
    assert not unknown_state.accepted
    assert not core.drive_granted


def test_empty_token_factory_result_is_rejected() -> None:
    core = make_core(token='')
    start_and_accept(core)

    with pytest.raises(ValueError, match='empty token'):
        core.observe_feedback(
            'robot1',
            task_state=TaskState.WAITING_FOR_TOKEN,
            event_type=0,
            event_id='',
        )


def test_permit_edges_publish_one_command_for_an_accepted_goal() -> None:
    core = make_core()
    start_and_accept(core)

    move = core.observe_permit(False)
    duplicate = core.observe_permit(False)
    resume = core.observe_permit(True)

    assert len(move) == 1
    assert move[0].robot_id == 'robot1'
    assert move[0].command is PatrolCommandType.MOVE_TO_SAFE_ZONE
    assert duplicate == ()
    assert len(resume) == 1
    assert resume[0].command is PatrolCommandType.RESUME_PATROL
    assert move[0].command_id != resume[0].command_id


def test_permit_edge_before_goal_acceptance_does_not_create_command() -> None:
    core = make_core()
    core.observe_permit(True)
    core.prepare_goal('robot1')

    assert core.observe_permit(False) == ()


def test_permit_rejects_non_boolean_values() -> None:
    with pytest.raises(ValueError, match='allowed must be bool'):
        make_core().observe_permit(1)


def test_token_frames_are_robot_specific_and_monotonically_sequenced() -> None:
    core = make_core()
    start_and_accept(core)
    core.observe_feedback(
        'robot1',
        task_state=TaskState.WAITING_FOR_TOKEN,
        event_type=0,
        event_id='',
    )

    first = core.token_frames()
    second = core.token_frames()

    assert [(frame.robot_id, frame.token) for frame in first] == [
        ('robot1', 'token-1'),
        ('robot6', ''),
    ]
    assert [frame.sequence for frame in first] == [1, 1]
    assert [frame.sequence for frame in second] == [2, 2]


def test_fire_confirmation_holds_future_patrol_until_explicit_clear() -> None:
    core = make_core()
    start_and_accept(core)

    ignored = core.observe_feedback(
        'robot1',
        task_state=TaskState.DETECTION_CONFIRMED,
        event_type=EventType.FIRE,
        event_id='',
    )
    activated = core.observe_feedback(
        'robot1',
        task_state=TaskState.DETECTION_CONFIRMED,
        event_type=EventType.FIRE,
        event_id='fire-001',
    )

    assert not ignored.fire_hold_activated
    assert activated.fire_hold_activated
    assert core.fire_event_id == 'fire-001'

    core.finish_goal('robot1')
    with pytest.raises(ControlStateError, match='fire hold'):
        core.prepare_goal('robot6')

    core.clear_fire_hold()
    assert core.prepare_goal('robot6').robot_id == 'robot6'


def test_revoke_removes_drive_authority_but_keeps_goal_until_result() -> None:
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
    assert not core.drive_granted
    assert core.token_frames()[0].token == ''

    core.finish_goal('robot1')
    assert core.active_robot_id is None
