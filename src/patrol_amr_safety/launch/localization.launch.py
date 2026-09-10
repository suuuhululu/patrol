"""Forward patrol localization settings to TurtleBot 4 localization."""

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution


def generate_launch_description():
    pkg_turtlebot4_navigation = get_package_share_directory('turtlebot4_navigation')

    return LaunchDescription([
        DeclareLaunchArgument(
            'map',
            description='Full path to the patrol map YAML file to load'),
        DeclareLaunchArgument(
            'namespace', default_value='',
            description='Robot namespace'),
        DeclareLaunchArgument(
            'use_sim_time', default_value='false',
            choices=['true', 'false'],
            description='Use sim time'),
        DeclareLaunchArgument(
            'params',
            default_value=PathJoinSubstitution([
                pkg_turtlebot4_navigation, 'config', 'localization.yaml']),
            description='Localization parameters'),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    pkg_turtlebot4_navigation, 'launch', 'localization.launch.py'])),
            launch_arguments={
                'namespace': LaunchConfiguration('namespace'),
                'map': LaunchConfiguration('map'),
                'use_sim_time': LaunchConfiguration('use_sim_time'),
                'params': LaunchConfiguration('params'),
            }.items()),
    ])
