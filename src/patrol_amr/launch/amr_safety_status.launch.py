"""Bring up the AMR nodes whose input contracts already exist.

Starts battery_monitor, local_safety_supervisor and status_reporter for a
single robot. Every launch argument is mandatory on purpose:

* ``robot_id`` differs per robot, so no default is assumed here.
* ``source_session_id`` must change on every run so that consumers can
  tell one status_reporter run from the next.
* ``safety_state`` carries an enum whose numbers are still TBD-IF-003,
  so this file transports the operator's value instead of inventing one.

The nodes keep the root-namespace relative topics that stages 2, 6 and 8
were verified with. Running two robots on one ROS domain would need a
namespace or topic contract that has not been agreed yet.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    robot_id = LaunchConfiguration('robot_id')
    source_session_id = LaunchConfiguration('source_session_id')
    safety_state = LaunchConfiguration('safety_state')

    return LaunchDescription([
        DeclareLaunchArgument(
            'robot_id',
            description='Robot identity: robot1 or robot6',
        ),
        DeclareLaunchArgument(
            'source_session_id',
            description='Identifies this status_reporter run; change on restart',
        ),
        DeclareLaunchArgument(
            'safety_state',
            description='uint8 safety state to transport (enum TBD-IF-003)',
        ),
        Node(
            package='patrol_amr',
            executable='battery_monitor',
            name='battery_monitor',
            output='screen',
        ),
        Node(
            package='patrol_amr',
            executable='local_safety_supervisor',
            name='local_safety_supervisor',
            output='screen',
            parameters=[{
                'robot_id': ParameterValue(robot_id, value_type=str),
            }],
        ),
        Node(
            package='patrol_amr',
            executable='status_reporter',
            name='status_reporter',
            output='screen',
            parameters=[{
                'robot_id': ParameterValue(robot_id, value_type=str),
                'source_session_id': ParameterValue(
                    source_session_id, value_type=str
                ),
                'safety_state': ParameterValue(
                    safety_state, value_type=int
                ),
            }],
        ),
    ])
