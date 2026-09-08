"""Tests for the ROS-independent W1-W7 configuration boundary."""

import math
import unittest

from patrol_amr.waypoint_repository import load_waypoints


class WaypointRepositoryTest(unittest.TestCase):
    """Validate waypoint count, order, and numeric safety."""

    def test_builds_exactly_w1_through_w7_in_input_order(self):
        values = [float(value) for value in range(21)]

        waypoints = load_waypoints(values)

        self.assertEqual(
            [waypoint.name for waypoint in waypoints],
            ['W1', 'W2', 'W3', 'W4', 'W5', 'W6', 'W7'],
        )
        self.assertEqual(
            (waypoints[0].x, waypoints[0].y, waypoints[0].yaw_deg),
            (0.0, 1.0, 2.0),
        )
        self.assertEqual(
            (waypoints[-1].x, waypoints[-1].y, waypoints[-1].yaw_deg),
            (18.0, 19.0, 20.0),
        )

    def test_rejects_missing_or_extra_values(self):
        for count in (20, 22):
            with self.subTest(count=count):
                with self.assertRaisesRegex(ValueError, 'exactly 7'):
                    load_waypoints([0.0] * count)

    def test_rejects_non_finite_coordinates(self):
        values = [0.0] * 21
        values[4] = math.nan

        with self.assertRaisesRegex(ValueError, 'finite'):
            load_waypoints(values)

    def test_rejects_non_numeric_coordinates(self):
        values = [0.0] * 20 + ['not-a-number']

        with self.assertRaisesRegex(ValueError, 'numeric'):
            load_waypoints(values)


if __name__ == '__main__':
    unittest.main()
