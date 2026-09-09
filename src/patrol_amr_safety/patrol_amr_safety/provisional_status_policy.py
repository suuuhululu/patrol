"""TEMPORARY status projection approved by the user on 2026-09-08.

Merge replacement point: replace project_axes() when mission supplies explicit
operational/docking/scan inputs. This module NEVER grants motion, controls Nav2,
or changes the measured motion_stopped/safety_state/battery_state fields.
See docs/development/provisional-amr-status-policy.md for all assumptions.
"""

from dataclasses import dataclass
import math

from patrol_amr_safety import robot_status_state as rss

POLICY_VERSION = 'TEMP-AMR-STATUS-20260908-v1'


@dataclass(frozen=True)
class StatusAxes:
    operational_state: rss.OperationalState
    docking_state: rss.DockingState
    scan_state: str


CHARGING_STATES = frozenset((rss.BatteryState.CHARGING,
    rss.BatteryState.PATROL_READY, rss.BatteryState.FULL))
UNDOCKED_MISSIONS = frozenset((rss.MissionState.MISSION_PATROLLING,
    rss.MissionState.MISSION_MOVING_TO_SAFE_ZONE,
    rss.MissionState.MISSION_WAITING_SAFE_ZONE,
    rss.MissionState.MISSION_RETURNING_TO_DOCK))


def project_axes(snapshot, mission, *, has_mission):
    """Derive three reporting axes only; all inferred rules are provisional."""
    charging = snapshot.battery_state in CHARGING_STATES
    moving = (
        math.isfinite(snapshot.linear_velocity)
        and math.isfinite(snapshot.angular_velocity)
        and (abs(snapshot.linear_velocity) > rss.STOP_LINEAR_LIMIT
             or abs(snapshot.angular_velocity) > rss.STOP_ANGULAR_LIMIT)
    )
    operational = _operational(snapshot, has_mission, charging, moving)
    docking = _docking(snapshot, mission, charging)
    scan = _scan(snapshot, has_mission)
    return StatusAxes(operational, docking, scan)


def _operational(snapshot, has_mission, charging, moving):
    op = rss.OperationalState
    if (snapshot.safety_state == rss.SafetyState.SAFETY_ERROR
            or snapshot.mission_state == rss.MissionState.MISSION_FAILED):
        return op.OP_ERROR
    if snapshot.safety_state in (rss.SafetyState.SAFETY_STOPPING,
            rss.SafetyState.SAFETY_STOPPED, rss.SafetyState.SAFETY_ESTOPPED):
        return op.OP_STOPPED_SAFETY
    if moving:
        return op.OP_MOVING
    if charging:
        return op.OP_CHARGING
    if not has_mission or not snapshot.motion_stopped:
        return op.OP_INITIALIZING
    return op.OP_READY


def _docking(snapshot, mission, charging):
    dock = rss.DockingState
    state = snapshot.mission_state
    previous = snapshot.docking_state
    if state == rss.MissionState.MISSION_UNDOCKING:
        return dock.DOCK_UNDOCKING
    if state == rss.MissionState.MISSION_DOCKING:
        return dock.DOCK_DOCKING
    if state in UNDOCKED_MISSIONS:
        return dock.DOCK_UNDOCKED
    if state == rss.MissionState.MISSION_FAILED and previous in (
            dock.DOCK_UNDOCKING, dock.DOCK_DOCKING, dock.DOCK_FAILED):
        return dock.DOCK_FAILED
    if state == rss.MissionState.MISSION_COMPLETED and mission.outcome == 'SUCCEEDED':
        if previous == dock.DOCK_DOCKING:
            return dock.DOCK_DOCKED
        if previous == dock.DOCK_UNDOCKING:
            return dock.DOCK_UNDOCKED
    if state == rss.MissionState.MISSION_CANCELED and previous in (
            dock.DOCK_UNDOCKING, dock.DOCK_DOCKING):
        return dock.DOCK_UNKNOWN
    if charging:
        return dock.DOCK_DOCKED
    return previous


def _scan(snapshot, has_mission):
    state = snapshot.mission_state
    if not has_mission:
        return 'UNKNOWN'
    if state == rss.MissionState.MISSION_PATROLLING:
        if snapshot.safety_state != rss.SafetyState.SAFETY_NORMAL:
            return 'PAUSED'
        if snapshot.motion_stopped:
            return 'SCANNING'
        if not math.isfinite(snapshot.linear_velocity):
            return 'UNKNOWN'
        return 'MOVING_TO_WAYPOINT'
    return {
        rss.MissionState.MISSION_PAUSED: 'PAUSED',
        rss.MissionState.MISSION_FAILED: 'FAILED',
        rss.MissionState.MISSION_CANCELED: 'CANCELED',
        rss.MissionState.MISSION_COMPLETED: 'COMPLETED',
    }.get(state, 'IDLE')
