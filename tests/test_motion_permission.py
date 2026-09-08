"""Tests for the mission-facing local-safety permission callback."""

import unittest
from types import SimpleNamespace

from patrol_amr.motion_permission import MotionPermission


class MotionPermissionTest(unittest.TestCase):
    def test_fail_closed_then_tracks_callback_edges(self):
        calls = []
        permission = MotionPermission(lambda: calls.append('sync'))

        self.assertFalse(permission.allowed())
        permission(SimpleNamespace(data=True))
        self.assertTrue(permission.allowed())
        permission(SimpleNamespace(data=False))
        self.assertFalse(permission.allowed())
        self.assertEqual(calls, ['sync', 'sync'])


if __name__ == '__main__':
    unittest.main()
