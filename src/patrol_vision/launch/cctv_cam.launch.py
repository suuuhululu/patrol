from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='patrol_vision',
            executable='gate_cam',
            name='gate_cam',
            output='screen',
        ),

        Node(
            package='patrol_vision',
            executable='center_cam',
            name='center_cam',
            output='screen',
        ),

        Node(
            package='patrol_vision',
            executable='cam_master',
            name='cam_master',
            output='screen',
        ),
    ])