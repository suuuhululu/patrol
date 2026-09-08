"""Bring up the AMR nodes whose input contracts already exist.

Starts battery_monitor, local_safety_supervisor and status_reporter for a
single robot inside that robot's namespace. Every identity argument is
mandatory on purpose:

* ``robot_id`` differs per robot, so no default is assumed here.
* ``source_session_id`` must change on every run so that consumers can
  tell one status_reporter run from the next.
* ``safety_state`` carries an enum whose numbers are still TBD-IF-003,
  so this file transports the operator's value instead of inventing one.

Namespace (13단계): the nodes run under ``/<robot_id>``. architecture.md
2절 fixes robot1 -> /robot1 and robot6 -> /robot6, and both robots share
one ROS_DOMAIN_ID, so without a namespace their cmd_vel/odom/scan would
collide. It is derived from ``robot_id`` rather than taken as its own
argument precisely so the two cannot disagree.

The two topic arguments below exist because those endpoints are owned by
code that is not in this repository yet. They default to the agreed
contract name and can be pointed elsewhere without editing this file:

* ``battery_state_topic`` -- the real battery driver's location is part of
  TBD-ARCH-001 (device placement), so it may not sit inside the robot
  namespace.
* ``candidate_topic`` -- TBD-IF-009 puts Nav2's collision_monitor output on
  ``cmd_vel_safe``, but 관제's launch has not been merged and confirmed yet.
* ``odom_topic`` -- the drive base publishes odometry, and like the battery
  driver its placement is part of TBD-ARCH-001.
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
    battery_state_topic = LaunchConfiguration('battery_state_topic')
    candidate_topic = LaunchConfiguration('candidate_topic')
    odom_topic = LaunchConfiguration('odom_topic')

    # 노드 namespace 는 robot_id 그대로다. 별도 인자로 두면 둘이 어긋날 수
    # 있고, architecture.md 가 매핑을 이미 고정해 두어 선택의 여지가 없다.
    namespace = robot_id

    return LaunchDescription([
        DeclareLaunchArgument(
            'robot_id',
            description='Robot identity and namespace: robot1 or robot6',
        ),
        DeclareLaunchArgument(
            'source_session_id',
            description='Identifies this status_reporter run; change on restart',
        ),
        DeclareLaunchArgument(
            'safety_state',
            description='uint8 safety state to transport (enum TBD-IF-003)',
        ),
        DeclareLaunchArgument(
            'battery_state_topic',
            default_value='battery_state',
            description=(
                'Where the battery driver publishes sensor_msgs/BatteryState. '
                'Relative names resolve inside the robot namespace; pass an '
                'absolute name if the driver sits outside it (TBD-ARCH-001).'
            ),
        ),
        DeclareLaunchArgument(
            'candidate_topic',
            default_value='cmd_vel_safe',
            description=(
                'Arbitrated drive candidate input (TwistStamped). TBD-IF-009 '
                'points Nav2 collision_monitor cmd_vel_out_topic here.'
            ),
        ),
        DeclareLaunchArgument(
            'odom_topic',
            default_value='odom',
            description=(
                'Where the drive base publishes nav_msgs/Odometry. '
                'status_reporter uses it for linear/angular_velocity and the '
                'motion_stopped judgment of interfaces.md 3절.'
            ),
        ),
        Node(
            package='patrol_amr',
            executable='battery_monitor',
            name='battery_monitor',
            namespace=namespace,
            output='screen',
            remappings=[('battery_state', battery_state_topic)],
        ),
        Node(
            package='patrol_amr',
            executable='local_safety_supervisor',
            name='local_safety_supervisor',
            namespace=namespace,
            output='screen',
            parameters=[{
                'robot_id': ParameterValue(robot_id, value_type=str),
            }],
            remappings=[('cmd_vel_safe', candidate_topic)],
        ),
        Node(
            package='patrol_amr',
            executable='status_reporter',
            name='status_reporter',
            namespace=namespace,
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
            remappings=[
                ('battery_state', battery_state_topic),
                ('odom', odom_topic),
            ],
        ),
    ])
