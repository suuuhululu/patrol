"""Launch TurtleBot4 localization/Nav2 with two map-aligned KeepoutFilters.

The base (red) filter is always enabled.  The center-corridor (yellow)
filter starts disabled and is the only filter that control may toggle after
it consumes /vision/cctv/patrol_allowed.  This AMR launch intentionally does
not subscribe to the vision topic: the control server owns that decision and
the global/local parameter transaction.
"""

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace, SetParametersFromFile
from launch_ros.parameter_descriptions import ParameterValue
from nav2_common.launch import ReplaceString


FILTER_SERVER_NAMES = [
    'base_keepout_mask_server',
    'base_keepout_filter_info_server',
    'center_corridor_keepout_mask_server',
    'center_corridor_filter_info_server',
]


def _mask_server(name, yaml_filename, topic_prefix, use_sim_time):
    return Node(
        package='nav2_map_server',
        executable='map_server',
        name=name,
        output='screen',
        parameters=[{
            'yaml_filename': yaml_filename,
            'topic_name': 'mask',
            'frame_id': 'map',
            'use_sim_time': use_sim_time,
        }],
        remappings=[
            ('mask', f'keepout/{topic_prefix}/mask'),
            ('map_metadata', f'keepout/{topic_prefix}/map_metadata'),
        ],
    )


def _filter_info_server(
    name, topic_prefix, robot_id, use_sim_time
):
    return Node(
        package='nav2_map_server',
        executable='costmap_filter_info_server',
        name=name,
        output='screen',
        parameters=[{
            'type': 0,
            'filter_info_topic': ParameterValue(
                ['/', robot_id, f'/keepout/{topic_prefix}/filter_info'],
                value_type=str,
            ),
            # This value is carried inside CostmapFilterInfo and later used by
            # costmap nodes in deeper namespaces.  It must be absolute.
            'mask_topic': ParameterValue(
                ['/', robot_id, f'/keepout/{topic_prefix}/mask'],
                value_type=str,
            ),
            'base': 0.0,
            'multiplier': 1.0,
            'use_sim_time': use_sim_time,
        }],
    )


def generate_launch_description():
    patrol_share = get_package_share_directory('patrol_amr')
    turtlebot_share = get_package_share_directory('turtlebot4_navigation')

    robot_id = LaunchConfiguration('robot_id')
    use_sim_time = LaunchConfiguration('use_sim_time')
    autostart = LaunchConfiguration('autostart')
    map_yaml = LaunchConfiguration('map')
    localization_params = LaunchConfiguration('localization_params_file')
    nav2_params = LaunchConfiguration('nav2_params_file')

    base_mask_yaml = f'{patrol_share}/maps/base_keepout_mask.yaml'
    corridor_mask_yaml = (
        f'{patrol_share}/maps/center_corridor_keepout_mask.yaml'
    )
    overlay = ReplaceString(
        source_file=f'{patrol_share}/config/nav2_keepout_filters.yaml',
        replacements={'<robot_namespace>': ('/', robot_id)},
    )

    filter_servers = GroupAction([
        PushRosNamespace(robot_id),
        _mask_server(
            'base_keepout_mask_server', base_mask_yaml, 'base', use_sim_time
        ),
        _filter_info_server(
            'base_keepout_filter_info_server',
            'base',
            robot_id,
            use_sim_time,
        ),
        _mask_server(
            'center_corridor_keepout_mask_server',
            corridor_mask_yaml,
            'center_corridor',
            use_sim_time,
        ),
        _filter_info_server(
            'center_corridor_filter_info_server',
            'center_corridor',
            robot_id,
            use_sim_time,
        ),
        Node(
            package='nav2_lifecycle_manager',
            executable='lifecycle_manager',
            name='keepout_lifecycle_manager',
            output='screen',
            parameters=[{
                'autostart': autostart,
                'node_names': FILTER_SERVER_NAMES,
                'use_sim_time': use_sim_time,
            }],
        ),
    ])

    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            f'{turtlebot_share}/launch/localization.launch.py'
        ),
        launch_arguments={
            'namespace': robot_id,
            'map': map_yaml,
            'params': localization_params,
            'use_sim_time': use_sim_time,
        }.items(),
    )

    navigation = GroupAction([
        SetParametersFromFile(overlay),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                f'{turtlebot_share}/launch/nav2.launch.py'
            ),
            launch_arguments={
                'namespace': robot_id,
                'params_file': nav2_params,
                'use_sim_time': use_sim_time,
            }.items(),
        ),
    ])

    return LaunchDescription([
        DeclareLaunchArgument(
            'robot_id',
            choices=['robot1', 'robot6'],
            description='Robot identity and namespace',
        ),
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            choices=['true', 'false'],
        ),
        DeclareLaunchArgument(
            'autostart',
            default_value='true',
            choices=['true', 'false'],
            description='Autostart the four Keepout lifecycle servers',
        ),
        DeclareLaunchArgument(
            'map',
            default_value=f'{patrol_share}/maps/final_project_map.yaml',
            description='Localization map YAML',
        ),
        DeclareLaunchArgument(
            'localization_params_file',
            default_value=f'{turtlebot_share}/config/localization.yaml',
        ),
        DeclareLaunchArgument(
            'nav2_params_file',
            default_value=f'{turtlebot_share}/config/nav2.yaml',
            description='Existing TurtleBot4 Nav2 parameters to overlay',
        ),
        filter_servers,
        localization,
        navigation,
    ])
