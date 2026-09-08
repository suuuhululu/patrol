"""Map-aligned base and center-corridor Keepout mask tests."""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'src/patrol_amr'
sys.path.insert(0, str(PACKAGE))

from patrol_amr import keepout_mask as MODULE  # noqa: E402
from patrol_amr import waypoint_catalog  # noqa: E402


MAP_YAML = PACKAGE / 'maps/final_project_map.yaml'
MAP_PGM = PACKAGE / 'maps/final_project_map.pgm'
ZONES_YAML = PACKAGE / 'config/keepout_zones.yaml'
WAYPOINTS_YAML = PACKAGE / 'config/patrol_waypoints.yaml'


class ZoneContractTests(unittest.TestCase):
    def test_red_and_yellow_regions_use_the_confirmed_point_order(self):
        zones = MODULE.load_keepout_zones(ZONES_YAML)
        base = zones.layer('base_keepout')
        corridor = zones.layer('center_corridor_keepout')
        self.assertEqual(tuple(item.polygon_id for item in base.polygons), ('base_right', 'base_left'))
        self.assertEqual(tuple(item.polygon_id for item in corridor.polygons), ('center_corridor',))
        self.assertEqual(base.activation_policy, 'always')
        self.assertEqual(
            corridor.activation_policy,
            'control_when_patrol_disallowed',
        )
        self.assertEqual(
            tuple((point.x, point.y) for point in base.polygons[0].points),
            ((-0.504, 0.126), (-1.628, 0.188), (-1.761, -2.156), (-0.667, -2.230)),
        )
        self.assertEqual(
            tuple((point.x, point.y) for point in corridor.polygons[0].points),
            ((-1.628, 0.188), (-2.267, 0.222), (-2.445, -2.068), (-1.761, -2.156)),
        )

    def test_named_sample_points_match_each_region(self):
        zones = MODULE.load_keepout_zones(ZONES_YAML)
        base = zones.layer('base_keepout')
        corridor = zones.layer('center_corridor_keepout')
        right_red = MODULE.Point(-1.0, -1.0)
        left_red = MODULE.Point(-3.0, -1.0)
        center_yellow = MODULE.Point(-2.1, -1.0)
        self.assertTrue(any(MODULE.point_in_polygon(right_red, p.points) for p in base.polygons))
        self.assertTrue(any(MODULE.point_in_polygon(left_red, p.points) for p in base.polygons))
        self.assertFalse(any(MODULE.point_in_polygon(center_yellow, p.points) for p in base.polygons))
        self.assertTrue(MODULE.point_in_polygon(center_yellow, corridor.polygons[0].points))


class RasterTests(unittest.TestCase):
    def test_map_metadata_and_pgm_size_match_supplied_map(self):
        metadata = MODULE.load_map_metadata(MAP_YAML)
        self.assertEqual((metadata.resolution, metadata.origin_x, metadata.origin_y), (0.05, -5.801, -3.43))
        self.assertEqual(MODULE.read_pgm_size(MAP_PGM), (126, 90))

    def test_masks_are_binary_and_map_sized(self):
        zones = MODULE.load_keepout_zones(ZONES_YAML)
        metadata = MODULE.load_map_metadata(MAP_YAML)
        for layer in zones.layers:
            pixels = MODULE.rasterize_layer(layer, metadata, 126, 90)
            self.assertEqual(len(pixels), 126 * 90)
            self.assertEqual(set(pixels), {0, 254})

    def test_wp3_is_only_in_corridor_and_other_waypoints_are_outside(self):
        zones = MODULE.load_keepout_zones(ZONES_YAML)
        catalog = waypoint_catalog.load_waypoint_catalog(WAYPOINTS_YAML)
        base = zones.layer('base_keepout')
        corridor = zones.layer('center_corridor_keepout').polygons[0]
        for waypoint in catalog.waypoints:
            point = MODULE.Point(waypoint.x, waypoint.y)
            self.assertFalse(any(MODULE.point_in_polygon(point, p.points) for p in base.polygons))
            self.assertEqual(
                MODULE.point_in_polygon(point, corridor.points),
                waypoint.waypoint_id == 'WP3',
            )


if __name__ == '__main__':
    unittest.main()
