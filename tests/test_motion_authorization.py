"""Tests for the explicit real-hardware launch interlock."""

import unittest

from patrol_amr.motion_authorization import (
    authorization_blockers, expected_motion_token,
    motion_launch_authorized)


class MotionAuthorizationTest(unittest.TestCase):
    """Verify that no single accidental parameter can enable movement."""

    def test_robot_specific_token(self):
        """Each namespace has a different exact arm token."""
        self.assertEqual(
            expected_motion_token('robot6'), 'ENABLE_ROBOT6_MOTION')

    def test_hardware_test_requires_token_and_mode(self):
        """The stock Nav2 test path needs both independent settings."""
        self.assertFalse(motion_launch_authorized(
            'robot6', False, True, 'ENABLE_ROBOT1_MOTION'))
        self.assertFalse(motion_launch_authorized(
            'robot6', False, False, 'ENABLE_ROBOT6_MOTION'))
        self.assertTrue(motion_launch_authorized(
            'robot6', False, True, 'ENABLE_ROBOT6_MOTION'))

    def test_blockers_explain_failed_authorization(self):
        """Operator logs contain both missing conditions."""
        self.assertEqual(
            authorization_blockers('robot6', False, False, ''),
            ('NO_DRIVE_PATH_SELECTED', 'MOTION_ENABLE_TOKEN_MISMATCH'),
        )
