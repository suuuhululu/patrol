"""Launch patrol Nav2 without managing the unused route server."""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    OpaqueFunction,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

from launch_ros.actions import Node, PushRosNamespace, SetRemap


# The patrol sends one NavigateToPose goal at a time and docks after W7. The
# Nav2 route and waypoint servers are separate APIs and are not used here.
PATROL_LIFECYCLE_NODES = [
    'controller_server',
    'smoother_server',
    'planner_server',
    'behavior_server',
    'velocity_smoother',
    'collision_monitor',
    'bt_navigator',
    'docking_server',
]


def _launch_setup(context):
    """Start upstream nodes inert, then manage only patrol dependencies."""
    namespace = LaunchConfiguration('namespace').perform(context).strip('/')
    namespace_absolute = f'/{namespace}' if namespace else ''
    turtlebot_share = get_package_share_directory('turtlebot4_navigation')

    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(turtlebot_share, 'launch', 'navigation_launch.py')),
        launch_arguments={
            'namespace': namespace_absolute,
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'params_file': LaunchConfiguration('params_file'),
            # Leave the included lifecycle manager idle. The manager below
            # starts the smaller node set without route_server.
            'autostart': 'false',
            'use_composition': 'False',
            'use_respawn': 'False',
            'log_level': LaunchConfiguration('log_level'),
        }.items(),
    )

    lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='patrol_lifecycle_manager_navigation',
        output='screen',
        parameters=[{
            'autostart': True,
            'bond_timeout': 20.0,
            'node_names': PATROL_LIFECYCLE_NODES,
        }],
        arguments=[
            '--ros-args', '--log-level', LaunchConfiguration('log_level')],
    )

    return [GroupAction([
        PushRosNamespace(namespace),
        SetRemap(
            f'{namespace_absolute}/global_costmap/scan',
            f'{namespace_absolute}/scan',
        ),
        SetRemap(
            f'{namespace_absolute}/local_costmap/scan',
            f'{namespace_absolute}/scan',
        ),
        navigation,
        TimerAction(
            period=LaunchConfiguration('lifecycle_start_delay'),
            actions=[lifecycle_manager],
        ),
    ])]


def generate_launch_description():
    """Declare a portable, namespaced patrol Nav2 launch description."""
    mission_share = get_package_share_directory('patrol_amr')

    return LaunchDescription([
        DeclareLaunchArgument(
            'namespace',
            default_value='robot6',
            description='Physical robot namespace',
        ),
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            choices=['true', 'false'],
        ),
        DeclareLaunchArgument(
            'params_file',
            default_value=os.path.join(
                mission_share, 'config', 'patrol_nav2.yaml'),
        ),
        DeclareLaunchArgument(
            'lifecycle_start_delay',
            default_value='10.0',
            description='DDS discovery settling time before Nav2 activation',
        ),
        DeclareLaunchArgument('log_level', default_value='info'),
        OpaqueFunction(function=_launch_setup),
    ])
