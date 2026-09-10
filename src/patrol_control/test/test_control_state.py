"""Unit tests for staged integration profile and vision input state."""

from patrol_control.control_state import DetectionDisposition
from patrol_control.control_state import DetectionEventTracker
from patrol_control.control_state import IntegrationProfile
from patrol_control.control_state import parse_profile
from patrol_control.control_state import PermitHealth
from patrol_control.control_state import PermitMonitor
from patrol_control.control_state import PROFILE_CAPABILITIES

import pytest


SECOND = 1_000_000_000


def test_vision_profile_disables_all_amr_io():
    """Keep the first integration independent of absent AMR topics."""
    profile = parse_profile('vision_integration')
    capabilities = PROFILE_CAPABILITIES[profile]

    assert profile is IntegrationProfile.VISION_INTEGRATION
    assert capabilities.vision_input
    assert not capabilities.amr_input
    assert not capabilities.amr_output
    assert capabilities.production_ready


def test_full_system_is_reserved_until_safety_work_is_complete():
    """Do not advertise the incomplete AMR integration as runnable."""
    capabilities = PROFILE_CAPABILITIES[IntegrationProfile.FULL_SYSTEM]

    assert capabilities.amr_input
    assert capabilities.amr_output
    assert not capabilities.production_ready


def test_unknown_profile_is_rejected():
    """Fail clearly instead of silently enabling an unexpected scope."""
    with pytest.raises(ValueError, match='integration_profile'):
        parse_profile('debug')


def test_first_permit_sample_becomes_healthy_and_updates_value():
    """Apply the first valid Bool immediately before any timeout."""
    monitor = PermitMonitor(0)

    transition = monitor.observe(False, SECOND)

    assert transition.health is PermitHealth.HEALTHY
    assert transition.patrol_allowed is False
    assert transition.value_changed
    assert transition.became_healthy


def test_permit_timeout_boundary_preserves_last_value():
    """Enter timeout at five seconds without changing the permit."""
    monitor = PermitMonitor(0)
    monitor.observe(False, SECOND)

    before = monitor.check_timeout(6 * SECOND - 1)
    boundary = monitor.check_timeout(6 * SECOND)
    repeated = monitor.check_timeout(7 * SECOND)

    assert before.health is PermitHealth.HEALTHY
    assert not before.became_timed_out
    assert boundary.health is PermitHealth.TIMED_OUT
    assert boundary.became_timed_out
    assert boundary.patrol_allowed is False
    assert not repeated.became_timed_out


def test_no_initial_message_times_out_from_startup():
    """Report a missing cam_master even when no sample has arrived."""
    monitor = PermitMonitor(10)

    assert monitor.check_timeout(5 * SECOND + 9).health is PermitHealth.WAITING
    transition = monitor.check_timeout(5 * SECOND + 10)

    assert transition.health is PermitHealth.TIMED_OUT
    assert transition.became_timed_out
    assert transition.patrol_allowed is True


def test_timeout_recovery_requires_three_spaced_identical_samples():
    """Recover only after the fixed Bool recovery sequence."""
    monitor = PermitMonitor(0)
    monitor.observe(True, 0)
    monitor.check_timeout(5 * SECOND)

    first = monitor.observe(False, 5 * SECOND + 100_000_000)
    second = monitor.observe(False, 5 * SECOND + 300_000_000)
    third = monitor.observe(False, 5 * SECOND + 500_000_000)

    assert first.health is PermitHealth.RECOVERING
    assert second.health is PermitHealth.RECOVERING
    assert first.patrol_allowed is True
    assert second.patrol_allowed is True
    assert third.health is PermitHealth.HEALTHY
    assert third.recovered
    assert third.value_changed
    assert third.patrol_allowed is False


def test_recovery_restarts_when_value_changes():
    """Do not combine different Bool values into one recovery sequence."""
    monitor = PermitMonitor(0)
    monitor.check_timeout(5 * SECOND)
    monitor.observe(False, 5 * SECOND + 100_000_000)
    monitor.observe(False, 5 * SECOND + 300_000_000)

    reset = monitor.observe(True, 5 * SECOND + 500_000_000)
    second = monitor.observe(True, 5 * SECOND + 700_000_000)
    third = monitor.observe(True, 5 * SECOND + 900_000_000)

    assert reset.health is PermitHealth.RECOVERING
    assert second.health is PermitHealth.RECOVERING
    assert third.recovered
    assert third.patrol_allowed is True


def test_recovery_restarts_when_gap_exceeds_half_second():
    """Reject a recovery sequence containing an excessive receive gap."""
    monitor = PermitMonitor(0)
    monitor.check_timeout(5 * SECOND)
    monitor.observe(False, 5 * SECOND + 100_000_000)

    reset = monitor.observe(False, 5 * SECOND + 600_000_001)

    assert reset.health is PermitHealth.RECOVERING
    assert not reset.recovered
    assert reset.patrol_allowed is True


def test_too_fast_recovery_sequence_restarts():
    """Require at least 0.3 seconds from the first to third sample."""
    monitor = PermitMonitor(0)
    monitor.check_timeout(5 * SECOND)

    monitor.observe(False, 5 * SECOND + 10_000_000)
    monitor.observe(False, 5 * SECOND + 60_000_000)
    third = monitor.observe(False, 5 * SECOND + 110_000_000)

    assert third.health is PermitHealth.RECOVERING
    assert not third.recovered
    assert third.patrol_allowed is True


def test_detection_event_validates_v11_identity_enum_and_duplicate():
    """Accept each valid v1.1 event ID only once per control session."""
    tracker = DetectionEventTracker()

    accepted = tracker.observe(
        expected_robot_id='robot1',
        robot_id='robot1',
        message_id='detmsg-1',
        event_id='det-robot1-fire-0001',
        event_type=1,
    )
    duplicate = tracker.observe(
        expected_robot_id='robot1',
        robot_id='robot1',
        message_id='detmsg-2',
        event_id='det-robot1-fire-0001',
        event_type=1,
    )

    assert accepted.disposition is DetectionDisposition.ACCEPTED
    assert duplicate.disposition is DetectionDisposition.DUPLICATE


@pytest.mark.parametrize(
    ('expected_robot_id', 'robot_id', 'message_id', 'event_id', 'event_type'),
    [
        ('robot1', 'robot6', 'message-1', 'event-1', 1),
        ('robot1', 'robot1', '', 'event-1', 1),
        ('robot1', 'robot1', 'message-1', '', 1),
        ('robot1', 'robot1', 'message-1', 'event-1', 0),
        ('robot1', 'robot1', 'message-1', 'event-1', 4),
    ],
)
def test_invalid_detection_event_is_rejected(
    expected_robot_id,
    robot_id,
    message_id,
    event_id,
    event_type,
):
    """Reject topic identity, required-field, and enum violations."""
    result = DetectionEventTracker().observe(
        expected_robot_id=expected_robot_id,
        robot_id=robot_id,
        message_id=message_id,
        event_id=event_id,
        event_type=event_type,
    )

    assert result.disposition is DetectionDisposition.REJECTED
