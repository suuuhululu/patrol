"""Bring up map localization, Nav2, and an explicitly armed patrol node."""

from datetime import datetime
import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    """Build a robot6-ready launch that remains inert without an arm token."""
    mission_share = get_package_share_directory('patrol_amr')
    turtlebot_share = get_package_share_directory('turtlebot4_navigation')
    robot_id = LaunchConfiguration('robot_id')
    use_sim_time = LaunchConfiguration('use_sim_time')
    start_localization = LaunchConfiguration('start_localization')
    start_nav2 = LaunchConfiguration('start_nav2')
    start_local_safety = LaunchConfiguration('start_local_safety')
    start_status_reporter = LaunchConfiguration('start_status_reporter')
    motion_enable_token = LaunchConfiguration('motion_enable_token')
    source_session_id = LaunchConfiguration('source_session_id')
    safety_state = LaunchConfiguration('safety_state')

    local_safety = Node(
        package='patrol_amr',
        executable='local_safety_supervisor',
        name='local_safety_supervisor',
        namespace=robot_id,
        condition=IfCondition(start_local_safety),
        parameters=[{
            'robot_id': ParameterValue(robot_id, value_type=str),
        }],
        output='screen',
    )

    status_reporter = Node(
        package='patrol_amr',
        executable='status_reporter',
        name='status_reporter',
        namespace=robot_id,
        condition=IfCondition(start_status_reporter),
        parameters=[{
            'robot_id': ParameterValue(robot_id, value_type=str),
            'source_session_id': ParameterValue(
                source_session_id, value_type=str),
            'safety_state': ParameterValue(safety_state, value_type=int),
        }],
        output='screen',
    )

    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                mission_share, 'launch', 'patrol_localization.launch.py')),
        condition=IfCondition(start_localization),
        launch_arguments={
            'namespace': robot_id,
            'map': os.path.join(
                mission_share, 'config', 'final_project_map.yaml'),
            'params_file': LaunchConfiguration('localization_params_file'),
            'use_sim_time': use_sim_time,
            'lifecycle_start_delay': '10.0',
        }.items(),
    )
    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(mission_share, 'launch', 'patrol_nav2.launch.py')),
        condition=IfCondition(start_nav2),
        launch_arguments={
            'namespace': robot_id,
            'params_file': LaunchConfiguration('nav2_params_file'),
            'use_sim_time': use_sim_time,
            'lifecycle_start_delay': '20.0',
        }.items(),
    )
    mission = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(mission_share, 'launch', 'patrol.launch.py')),
        launch_arguments={
            'robot_id': robot_id,
            'params_file': LaunchConfiguration('mission_params_file'),
            'safety_path_ready': 'true',
            'hardware_test_mode': 'false',
            'motion_enable_token': motion_enable_token,
            'source_session_id': source_session_id,
        }.items(),
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'robot_id',
            default_value='robot6',
            choices=['robot1', 'robot6'],
            description='Physical robot namespace and contract robot_id',
        ),
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            choices=['true', 'false'],
        ),
        DeclareLaunchArgument(
            'start_localization',
            default_value='true',
            choices=['true', 'false'],
            description='False when namespaced AMCL is already running',
        ),
        DeclareLaunchArgument(
            'start_nav2',
            default_value='true',
            choices=['true', 'false'],
            description=(
                'False when the namespaced Nav2 stack is already running'),
        ),
        DeclareLaunchArgument(
            'start_local_safety',
            default_value='true',
            choices=['true', 'false'],
            description=(
                'False only when this robot local_safety_supervisor is '
                'already running'),
        ),
        DeclareLaunchArgument(
            'start_status_reporter',
            default_value='true',
            choices=['true', 'false'],
            description='False only when status_reporter is already running',
        ),
        DeclareLaunchArgument(
            'source_session_id',
            default_value=(
                'amr-' + datetime.now().strftime('%Y%m%dT%H%M%S')
                + f'-{os.getpid()}'),
            description='AMR process session; changes on every launch',
        ),
        DeclareLaunchArgument(
            'safety_state',
            default_value='0',
            description='Transported uint8; enum meaning remains TBD-IF-003',
        ),
        DeclareLaunchArgument(
            'motion_enable_token',
            default_value='',
            description='Explicit arm token, for example ENABLE_ROBOT6_MOTION',
        ),
        DeclareLaunchArgument(
            'mission_params_file',
            default_value=os.path.join(
                mission_share, 'config', 'patrol_params.yaml'),
        ),
        DeclareLaunchArgument(
            'localization_params_file',
            default_value=os.path.join(
                turtlebot_share, 'config', 'localization.yaml'),
        ),
        DeclareLaunchArgument(
            'nav2_params_file',
            default_value=os.path.join(
                mission_share, 'config', 'patrol_nav2.yaml'),
        ),
        local_safety,
        status_reporter,
        localization,
        nav2,
        mission,
    ])
