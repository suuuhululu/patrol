"""Reason-code policy for public PatrolReport terminal results."""

from __future__ import annotations


NONE = 0
CONTROL_CANCELED = 100
NAV_GOAL_REJECTED = 302
NAV_GOAL_ABORTED = 303
INTERNAL_ERROR = 1001


def navigation_result_reason(outcome: str, reason: str) -> int:
    """Map the currently implemented navigation outcomes to fixed codes."""
    if outcome == 'SUCCEEDED':
        return NONE
    if outcome == 'CANCELED':
        return CONTROL_CANCELED
    if outcome == 'FAILED':
        if reason.endswith('_GOAL_REJECTED'):
            return NAV_GOAL_REJECTED
        return NAV_GOAL_ABORTED
    if outcome == 'REJECTED':
        return NONE
    return INTERNAL_ERROR
