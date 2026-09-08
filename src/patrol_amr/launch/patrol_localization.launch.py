"""Launch map_server and AMCL after DDS discovery has settled."""

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

from launch_ros.actions import Node, PushRosNamespace


LOCALIZATION_LIFECYCLE_NODES = ['map_server', 'amcl']


def _launch_setup(context):
    """Start localization inert, then activate it after a bounded delay."""
    namespace = LaunchConfiguration('namespace').perform(context).strip('/')
    nav2_bringup_share = get_package_share_directory('nav2_bringup')

    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            nav2_bringup_share, 'launch', 'localization_launch.py')),
        launch_arguments={
            'namespace': namespace,
            'map': LaunchConfiguration('map'),
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'params_file': LaunchConfiguration('params_file'),
            # Keep the included manager idle. The delayed manager below owns
            # the only activation attempt for map_server and AMCL.
            'autostart': 'false',
            'use_composition': 'False',
            'use_respawn': 'False',
            'log_level': LaunchConfiguration('log_level'),
        }.items(),
    )

    lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='patrol_lifecycle_manager_localization',
        output='screen',
        parameters=[{
            'autostart': True,
            'bond_timeout': 20.0,
            'node_names': LOCALIZATION_LIFECYCLE_NODES,
        }],
        arguments=[
            '--ros-args', '--log-level', LaunchConfiguration('log_level')],
    )

    return [GroupAction([
        PushRosNamespace(namespace),
        localization,
        TimerAction(
            period=LaunchConfiguration('lifecycle_start_delay'),
            actions=[lifecycle_manager],
        ),
    ])]


def generate_launch_description():
    """Declare the robot namespace, map, parameters, and activation delay."""
    mission_share = get_package_share_directory('patrol_amr')
    turtlebot_share = get_package_share_directory('turtlebot4_navigation')

    return LaunchDescription([
        DeclareLaunchArgument(
            'namespace',
            default_value='robot6',
            description='Physical robot namespace',
        ),
        DeclareLaunchArgument(
            'map',
            default_value=os.path.join(
                mission_share, 'config', 'final_project_map.yaml'),
        ),
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            choices=['true', 'false'],
        ),
        DeclareLaunchArgument(
            'params_file',
            default_value=os.path.join(
                turtlebot_share, 'config', 'localization.yaml'),
        ),
        DeclareLaunchArgument(
            'lifecycle_start_delay',
            default_value='10.0',
            description='DDS discovery settling time before AMCL activation',
        ),
        DeclareLaunchArgument('log_level', default_value='info'),
        OpaqueFunction(function=_launch_setup),
    ])
