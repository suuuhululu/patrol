"""Measured patrol waypoint catalog tests."""

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATROL_AMR_PACKAGE_ROOT = ROOT / 'src/patrol_amr'
sys.path.insert(0, str(PATROL_AMR_PACKAGE_ROOT))

from patrol_amr import waypoint_catalog as MODULE  # noqa: E402


CATALOG_PATH = PATROL_AMR_PACKAGE_ROOT / 'config/patrol_waypoints.yaml'


class MeasuredCatalogTests(unittest.TestCase):
    def test_catalog_preserves_all_measured_values_in_route_order(self):
        catalog = MODULE.load_waypoint_catalog(CATALOG_PATH)
        self.assertEqual(catalog.map_id, 'final_project_map')
        self.assertEqual(catalog.frame_id, 'map')
        self.assertEqual(
            tuple((item.waypoint_id, item.x, item.y, item.yaw_deg) for item in catalog.waypoints),
            (
                ('WP1', -0.206, -1.038, 90.8),
                ('WP2', -1.147, 0.500, 175.4),
                ('WP3', -2.029, -0.916, 266.3),
                ('WP4', -2.751, -2.422, 182.4),
                ('WP5', -4.389, -1.122, 94.3),
                ('WP6', -2.909, 0.575, 358.3),
                ('WP7', -1.374, -2.439, 359.8),
            ),
        )

    def test_lookup_returns_exact_waypoint_and_unknown_fails(self):
        catalog = MODULE.load_waypoint_catalog(CATALOG_PATH)
        self.assertEqual(catalog.by_id('WP4').direction_approx, 'SOUTH')
        with self.assertRaises(KeyError):
            catalog.by_id('WP8')


class ValidationTests(unittest.TestCase):
    def load_text(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'waypoints.yaml'
            path.write_text(text, encoding='utf-8')
            return MODULE.load_waypoint_catalog(path)

    def test_rejects_non_map_frame_and_duplicate_ids(self):
        with self.assertRaises(ValueError):
            self.load_text('map_id: m\nframe_id: odom\nwaypoints: [{id: A, x: 0, y: 0, yaw_deg: 0, direction_approx: N}]\n')
        with self.assertRaises(ValueError):
            self.load_text('map_id: m\nframe_id: map\nwaypoints: [{id: A, x: 0, y: 0, yaw_deg: 0, direction_approx: N}, {id: A, x: 1, y: 1, yaw_deg: 1, direction_approx: N}]\n')

    def test_rejects_bad_yaw_and_non_finite_coordinate(self):
        with self.assertRaises(ValueError):
            self.load_text('map_id: m\nframe_id: map\nwaypoints: [{id: A, x: 0, y: 0, yaw_deg: 360, direction_approx: N}]\n')
        with self.assertRaises(ValueError):
            self.load_text('map_id: m\nframe_id: map\nwaypoints: [{id: A, x: .nan, y: 0, yaw_deg: 0, direction_approx: N}]\n')


if __name__ == '__main__':
    unittest.main()
