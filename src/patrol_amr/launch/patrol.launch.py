"""Launch the mission supervisor for one robot namespace."""

from datetime import datetime
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    pkg_share = get_package_share_directory('patrol_amr')
    default_params = os.path.join(pkg_share, 'config', 'patrol_params.yaml')
    robot_id = LaunchConfiguration('robot_id')
    params_file = LaunchConfiguration('params_file')
    safety_path_ready = LaunchConfiguration('safety_path_ready')
    hardware_test_mode = LaunchConfiguration('hardware_test_mode')
    motion_enable_token = LaunchConfiguration('motion_enable_token')
    source_session_id = LaunchConfiguration('source_session_id')
    default_session = [
        robot_id,
        '-' + datetime.now().strftime('%Y%m%dT%H%M%S'),
        f'-{os.getpid()}',
    ]

    return LaunchDescription([
        DeclareLaunchArgument(
            'robot_id', default_value='robot1',
            choices=['robot1', 'robot6'],
            description='Contract robot_id and ROS namespace'),
        DeclareLaunchArgument(
            'params_file', default_value=default_params,
            description='Mission parameter file'),
        DeclareLaunchArgument(
            'safety_path_ready', default_value='false',
            choices=['true', 'false'],
            description='Set true only after final local_safety cmd_vel path verification'),
        DeclareLaunchArgument(
            'hardware_test_mode', default_value='false',
            choices=['true', 'false'],
            description='Use the stock TurtleBot4 Nav2 drive path for a test'),
        DeclareLaunchArgument(
            'motion_enable_token', default_value='',
            description='Must equal ENABLE_<ROBOT_ID>_MOTION to allow motion'),
        DeclareLaunchArgument(
            'source_session_id', default_value=default_session,
            description=(
                'Robot process session: '
                '<robot_id>-<YYYYMMDDTHHMMSS>-<restart_sequence>')),
        Node(
            package='patrol_amr',
            executable='mission_supervisor',
            namespace=robot_id,
            parameters=[params_file, {
                'robot_id': robot_id,
                'safety_path_ready': ParameterValue(
                    safety_path_ready, value_type=bool),
                'hardware_test_mode': ParameterValue(
                    hardware_test_mode, value_type=bool),
                'motion_enable_token': motion_enable_token,
                'source_session_id': source_session_id,
            }],
            output='screen',
        ),
    ])
