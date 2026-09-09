"""Unit tests for the integrated command-control domain module."""

from datetime import datetime, timezone

from patrol_control.command_control import CheckState
from patrol_control.command_control import CommandControl
from patrol_control.command_control import CommandIdFactory
from patrol_control.command_control import CommandLifecycle
from patrol_control.command_control import CommandType
from patrol_control.command_control import CommandValidationError
from patrol_control.command_control import RetryActionType
from patrol_control.command_control import TrackingDisposition

import pytest


def make_control(**kwargs):
    """Build a deterministic command-control fixture."""
    factory = CommandIdFactory('ctrl-20260908T150000')
    return CommandControl(factory, **kwargs)


def test_identifier_sequences_are_human_readable_and_global():
    """Keep IDs readable and command sequence global across robots."""
    factory = CommandIdFactory.new_session(
        datetime(2026, 9, 8, 15, 0, 0, tzinfo=timezone.utc)
    )

    mission = factory.new_mission_id('robot1')
    first = factory.new_command_id('robot1', CommandType.START_PATROL)
    second = factory.new_command_id('robot6', CommandType.DOCK)

    assert mission == 'msn-ctrl-20260908T150000-robot1-0001'
    assert first == 'cmd-ctrl-20260908T150000-robot1-start-0001'
    assert second == 'cmd-ctrl-20260908T150000-robot6-dock-0002'


@pytest.mark.parametrize(
    ('command', 'mission_id', 'target_id'),
    [
        (CommandType.STOP, '', ''),
        (CommandType.STOP, 'existing-mission', ''),
        (CommandType.START_PATROL, '', 'robot1_default'),
        (CommandType.MOVE_TO_SAFE_ZONE, 'mission-a', ''),
        (CommandType.RESUME_PATROL, 'mission-a', ''),
        (CommandType.DOCK, 'mission-a', 'dock_1'),
        (CommandType.CANCEL, 'mission-a', ''),
    ],
)
def test_valid_command_matrix(command, mission_id, target_id):
    """Accept each fixed mission and target combination."""
    control = make_control()

    envelope = control.create_command(
        robot_id='robot1',
        command=command,
        now_ns=10,
        mission_id=mission_id,
        target_id=target_id,
    )

    assert envelope.command is command
    if command in (CommandType.START_PATROL, CommandType.DOCK):
        assert envelope.mission_id


@pytest.mark.parametrize(
    ('command', 'mission_id', 'target_id', 'reason'),
    [
        (CommandType.START_PATROL, '', '', 201),
        (CommandType.START_PATROL, '', 'plan-a', 201),
        (CommandType.MOVE_TO_SAFE_ZONE, '', '', 204),
        (CommandType.RESUME_PATROL, 'mission-a', 'waypoint', 205),
        (CommandType.DOCK, 'mission-a', 'dock_6', 201),
        (CommandType.CANCEL, '', '', 204),
        (CommandType.STOP, '', 'unexpected', 205),
    ],
)
def test_invalid_command_matrix(command, mission_id, target_id, reason):
    """Reject invalid mission and target combinations with a reason."""
    control = make_control()

    with pytest.raises(CommandValidationError) as caught:
        control.create_command(
            robot_id='robot1',
            command=command,
            now_ns=10,
            mission_id=mission_id,
            target_id=target_id,
        )

    assert caught.value.result.reason_code == reason


def test_start_patrol_rejects_caller_supplied_mission_id():
    """Keep START_PATROL mission ID ownership in control."""
    control = make_control()

    with pytest.raises(CommandValidationError) as caught:
        control.create_command(
            robot_id='robot1',
            command=CommandType.START_PATROL,
            now_ns=10,
            mission_id='caller-owned-mission',
            target_id='robot1_default',
        )

    assert caught.value.result.reason_code == 204


def test_robot6_start_patrol_uses_its_fixed_plan_id():
    """Keep the two robot-specific default patrol plans distinct."""
    control = make_control()

    envelope = control.create_command(
        robot_id='robot6',
        command=CommandType.START_PATROL,
        now_ns=10,
        target_id='robot6_default',
    )

    assert envelope.target_id == 'robot6_default'


@pytest.mark.parametrize(
    ('robot_id', 'command', 'reason'),
    [
        ('robot2', CommandType.STOP, 201),
        ('robot1', 99, 202),
    ],
)
def test_invalid_robot_and_command_return_structured_reason(
    robot_id, command, reason
):
    """Return the shared reason code for invalid routing values."""
    control = make_control()

    with pytest.raises(CommandValidationError) as caught:
        control.create_command(
            robot_id=robot_id,
            command=command,
            now_ns=10,
        )

    assert caught.value.result.reason_code == reason


def test_normal_check_transition_and_reverse_discard():
    """Apply the normal transition and discard a backward Check."""
    control = make_control()
    command = control.create_command(
        robot_id='robot1',
        command=CommandType.START_PATROL,
        now_ns=0,
        target_id='robot1_default',
    )

    accepted = control.handle_check(
        command_id=command.command_id,
        mission_id=command.mission_id,
        robot_id=command.robot_id,
        check_state=CheckState.ACCEPTED,
    )
    executing = control.handle_check(
        command_id=command.command_id,
        mission_id=command.mission_id,
        robot_id=command.robot_id,
        check_state=CheckState.EXECUTING,
    )
    reverse = control.handle_check(
        command_id=command.command_id,
        mission_id=command.mission_id,
        robot_id=command.robot_id,
        check_state=CheckState.ACCEPTED,
    )

    assert accepted.lifecycle is CommandLifecycle.ACCEPTED
    assert executing.lifecycle is CommandLifecycle.EXECUTING
    assert reverse.disposition is TrackingDisposition.DISCARDED
    assert (
        control.get_record(command.command_id).lifecycle
        is CommandLifecycle.EXECUTING
    )


def test_waiting_to_executing_stops_retries_with_warning():
    """Accept recovery EXECUTING and immediately stop retransmission."""
    control = make_control()
    command = control.create_command(
        robot_id='robot6',
        command=CommandType.DOCK,
        now_ns=0,
        target_id='dock_6',
    )

    result = control.handle_check(
        command_id=command.command_id,
        mission_id=command.mission_id,
        robot_id=command.robot_id,
        check_state=CheckState.EXECUTING,
    )

    assert result.lifecycle is CommandLifecycle.EXECUTING
    assert result.warnings == ('ACCEPTED_MISSING',)
    assert control.poll_retries(10_000_000_000) == ()
    assert control.poll_retries(20_000_000_000) == ()


def test_rejected_check_preserves_amr_reason():
    """Preserve the structured AMR rejection reason for orchestration."""
    control = make_control()
    command = control.create_command(
        robot_id='robot1',
        command=CommandType.CANCEL,
        mission_id='mission-a',
        now_ns=0,
    )

    result = control.handle_check(
        command_id=command.command_id,
        mission_id=command.mission_id,
        robot_id=command.robot_id,
        check_state=CheckState.REJECTED,
        reason_code=204,
        reason='mission is not active',
    )

    record = control.get_record(command.command_id)
    assert result.lifecycle is CommandLifecycle.REJECTED
    assert record.check_reason_code == 204
    assert record.check_reason == 'mission is not active'


@pytest.mark.parametrize('state', [CheckState.UNKNOWN, 99])
def test_unknown_check_values_are_discarded(state):
    """Discard CHECK_UNKNOWN and values outside the wire enum."""
    control = make_control()
    command = control.create_command(
        robot_id='robot1',
        command=CommandType.STOP,
        now_ns=0,
    )

    result = control.handle_check(
        command_id=command.command_id,
        mission_id=command.mission_id,
        robot_id=command.robot_id,
        check_state=state,
    )

    assert result.disposition is TrackingDisposition.DISCARDED
    assert result.lifecycle is CommandLifecycle.WAITING


def test_check_requires_matching_command_mission_and_robot_ids():
    """Require all three identity fields before changing state."""
    control = make_control()
    command = control.create_command(
        robot_id='robot1',
        command=CommandType.START_PATROL,
        now_ns=0,
        target_id='robot1_default',
    )

    result = control.handle_check(
        command_id=command.command_id,
        mission_id='different-mission',
        robot_id=command.robot_id,
        check_state=CheckState.ACCEPTED,
    )

    assert result.disposition is TrackingDisposition.DISCARDED
    assert (
        control.get_record(command.command_id).lifecycle
        is CommandLifecycle.WAITING
    )


def test_retry_twice_then_emit_one_timeout_with_same_id():
    """Retransmit twice, preserve the ID, and report timeout once."""
    control = make_control(timeout_ns=5, max_retransmissions=2)
    command = control.create_command(
        robot_id='robot1',
        command=CommandType.STOP,
        now_ns=0,
    )

    assert control.poll_retries(4) == ()
    first = control.poll_retries(5)
    second = control.poll_retries(10)
    timeout = control.poll_retries(15)

    assert first[0].action is RetryActionType.RETRANSMIT
    assert second[0].action is RetryActionType.RETRANSMIT
    assert timeout[0].action is RetryActionType.TIMEOUT
    assert first[0].envelope.command_id == command.command_id
    assert second[0].envelope == command
    assert control.poll_retries(20) == ()


def test_report_is_accepted_without_intermediate_check():
    """Accept a valid final report despite missing intermediate Checks."""
    control = make_control()
    command = control.create_command(
        robot_id='robot1',
        command=CommandType.CANCEL,
        mission_id='mission-a',
        now_ns=0,
    )

    result = control.handle_report(
        report_id='rpt-amr-0001',
        command_id=command.command_id,
        mission_id=command.mission_id,
        robot_id=command.robot_id,
        result=2,
        reason_code=100,
        reason='canceled by control',
    )
    duplicate = control.handle_report(
        report_id='rpt-amr-0001',
        command_id=command.command_id,
        mission_id=command.mission_id,
        robot_id=command.robot_id,
    )

    assert result.lifecycle is CommandLifecycle.COMPLETED
    assert result.warnings == ('INTERMEDIATE_COMMAND_CHECK_MISSING',)
    assert duplicate.disposition is TrackingDisposition.DUPLICATE
    record = control.get_record(command.command_id)
    assert record.report_result == 2
    assert record.report_reason_code == 100
    assert record.report_reason == 'canceled by control'


def test_report_with_mismatched_identity_is_discarded():
    """Discard a final report whose robot identity differs."""
    control = make_control()
    command = control.create_command(
        robot_id='robot1',
        command=CommandType.CANCEL,
        mission_id='mission-a',
        now_ns=0,
    )

    result = control.handle_report(
        report_id='rpt-amr-0001',
        command_id=command.command_id,
        mission_id=command.mission_id,
        robot_id='robot6',
    )

    assert result.disposition is TrackingDisposition.DISCARDED
    assert (
        control.get_record(command.command_id).lifecycle
        is CommandLifecycle.WAITING
    )


def test_second_final_report_id_for_same_command_is_discarded():
    """Bind each command to one immutable final report ID."""
    control = make_control()
    command = control.create_command(
        robot_id='robot1',
        command=CommandType.CANCEL,
        mission_id='mission-a',
        now_ns=0,
    )
    control.handle_report(
        report_id='rpt-amr-0001',
        command_id=command.command_id,
        mission_id=command.mission_id,
        robot_id=command.robot_id,
    )

    result = control.handle_report(
        report_id='rpt-amr-0002',
        command_id=command.command_id,
        mission_id=command.mission_id,
        robot_id=command.robot_id,
    )

    assert result.disposition is TrackingDisposition.DISCARDED
    assert control.get_record(command.command_id).report_id == 'rpt-amr-0001'
