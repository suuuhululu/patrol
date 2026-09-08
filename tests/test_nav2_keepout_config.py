import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'src/patrol_amr/config/nav2_keepout_filters.yaml'
LAUNCH = ROOT / 'src/patrol_amr/launch/amr_nav2_keepout.launch.py'


class Nav2KeepoutConfigTests(unittest.TestCase):
    def setUp(self):
        self.payload = yaml.safe_load(OVERLAY.read_text(encoding='utf-8'))

    def test_global_and_local_costmaps_have_the_same_two_filters(self):
        expected = [
            'base_keepout_filter',
            'center_corridor_keepout_filter',
        ]
        for node_pattern in ('/**/global_costmap', '/**/local_costmap'):
            params = self.payload[node_pattern]['ros__parameters']
            self.assertEqual(expected, params['filters'])

    def test_base_is_enabled_and_corridor_is_disabled_by_default(self):
        for node_pattern in ('/**/global_costmap', '/**/local_costmap'):
            params = self.payload[node_pattern]['ros__parameters']
            self.assertIs(params['base_keepout_filter']['enabled'], True)
            self.assertIs(
                params['center_corridor_keepout_filter']['enabled'], False
            )

    def test_both_filters_use_keepout_plugin_and_distinct_info_topics(self):
        for node_pattern in ('/**/global_costmap', '/**/local_costmap'):
            params = self.payload[node_pattern]['ros__parameters']
            base = params['base_keepout_filter']
            corridor = params['center_corridor_keepout_filter']
            self.assertEqual(
                'nav2_costmap_2d::KeepoutFilter', base['plugin']
            )
            self.assertEqual(
                'nav2_costmap_2d::KeepoutFilter', corridor['plugin']
            )
            self.assertNotEqual(
                base['filter_info_topic'], corridor['filter_info_topic']
            )

    def test_namespace_placeholder_resolves_for_each_robot(self):
        source = OVERLAY.read_text(encoding='utf-8')
        for robot_id in ('robot1', 'robot6'):
            rendered = source.replace('<robot_namespace>', f'/{robot_id}')
            payload = yaml.safe_load(rendered)
            for node_pattern in ('/**/global_costmap', '/**/local_costmap'):
                params = payload[node_pattern]['ros__parameters']
                for filter_name in params['filters']:
                    topic = params[filter_name]['filter_info_topic']
                    self.assertTrue(topic.startswith(f'/{robot_id}/keepout/'))
                    self.assertNotIn('<robot_namespace>', topic)

    def test_launch_description_constructs_with_installed_dependencies(self):
        spec = importlib.util.spec_from_file_location('amr_nav2_keepout', LAUNCH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source_share = ROOT / 'src/patrol_amr'
        turtlebot_share = Path(
            module.get_package_share_directory('turtlebot4_navigation')
        )
        module.get_package_share_directory = lambda package: str(
            source_share if package == 'patrol_amr' else turtlebot_share
        )
        with tempfile.TemporaryDirectory() as log_directory:
            os.environ['ROS_LOG_DIR'] = log_directory
            description = module.generate_launch_description()
        self.assertEqual(9, len(description.entities))
        self.assertEqual(4, len(module.FILTER_SERVER_NAMES))


if __name__ == '__main__':
    unittest.main()
