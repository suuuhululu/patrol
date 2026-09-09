"""Bring up the AMR nodes whose input contracts already exist.

Starts command_gateway, battery_monitor, local_safety_supervisor and
status_reporter for a
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

``push_namespace`` (default true) exists because namespaces compose. A
caller that already wraps this file in its own ``PushRosNamespace`` group
would otherwise get ``/robot1/robot1/cmd_vel`` -- and only partly, since
status_reporter publishes an absolute ``/<robot_id>/robot_status`` that
does not double. That mix is quiet and half-wrong, so a caller that pushes
its own namespace must pass ``push_namespace:=false``.

The two topic arguments below exist because those endpoints are owned by
code that is not in this repository yet. They default to the agreed
contract name and can be pointed elsewhere without editing this file:

* ``battery_state_topic`` -- the real battery driver's location is part of
  TBD-ARCH-001 (device placement), so it may not sit inside the robot
  namespace.
* ``candidate_topic`` -- TBD-IF-009 puts Nav2's collision_monitor output on
  the fixed ``cmd_vel_safe`` input path.
* ``odom_topic`` -- the drive base publishes odometry, and like the battery
  driver its placement is part of TBD-ARCH-001.
* ``pose_topic`` -- Nav2 AMCL's standard ``amcl_pose`` output. The argument
  keeps namespace/integration changes out of the node implementation.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace
from launch_ros.parameter_descriptions import ParameterValue


def _nodes(
    robot_id,
    source_session_id,
    battery_state_topic,
    battery_status_topic,
    candidate_topic,
    output_topic,
    odom_topic,
    pose_topic,
    drive_token_topic,
    heartbeat_topic,
    estop_topic,
    motion_allowed_topic,
    safety_state_topic,
    accepted_token_topic,
    database_path,
    mission_status_path,
    report_outbox_path,
):
    """Build a fresh set of node actions.

    Two GroupActions need the same four nodes under mutually exclusive
    conditions, and a launch action object cannot be reused across both,
    so this returns new ones each call.
    """
    return [
        Node(
            package='patrol_amr_safety',
            executable='command_gateway',
            name='command_gateway',
            output='screen',
            parameters=[{
                'robot_id': ParameterValue(robot_id, value_type=str),
                'source_session_id': ParameterValue(
                    source_session_id, value_type=str
                ),
                'database_path': ParameterValue(
                    database_path, value_type=str
                ),
            }],
        ),
        Node(
            package='patrol_amr_safety',
            executable='battery_monitor',
            name='battery_monitor',
            output='screen',
            remappings=[
                ('battery_state', battery_state_topic),
                ('battery_status', battery_status_topic),
            ],
        ),
        Node(
            package='patrol_amr_safety',
            executable='local_safety_supervisor',
            name='local_safety_supervisor',
            output='screen',
            parameters=[{
                'robot_id': ParameterValue(robot_id, value_type=str),
            }],
            remappings=[
                ('/control/drive_token', drive_token_topic),
                ('/control/heartbeat', heartbeat_topic),
                ('/control/estop', estop_topic),
                ('cmd_vel_safe', candidate_topic),
                ('cmd_vel', output_topic),
                ('odom', odom_topic),
                ('motion_allowed', motion_allowed_topic),
                ('safety_state', safety_state_topic),
                ('accepted_token_id', accepted_token_topic),
            ],
        ),
        Node(
            package='patrol_amr_safety',
            executable='status_reporter',
            name='status_reporter',
            output='screen',
            parameters=[{
                'robot_id': ParameterValue(robot_id, value_type=str),
                'source_session_id': ParameterValue(
                    source_session_id, value_type=str
                ),
                'safety_state': ParameterValue(safety_state, value_type=int),
            }],
            remappings=[
                ('battery_state', battery_state_topic),
                ('battery_status', battery_status_topic),
                ('odom', odom_topic),
                ('amcl_pose', pose_topic),
                ('safety_state', safety_state_topic),
                ('accepted_token_id', accepted_token_topic),
            ],
        ),
    ]


def generate_launch_description():
    robot_id = LaunchConfiguration('robot_id')
    source_session_id = LaunchConfiguration('source_session_id')
    battery_state_topic = LaunchConfiguration('battery_state_topic')
    battery_status_topic = LaunchConfiguration('battery_status_topic')
    candidate_topic = LaunchConfiguration('candidate_topic')
    output_topic = LaunchConfiguration('output_topic')
    odom_topic = LaunchConfiguration('odom_topic')
    pose_topic = LaunchConfiguration('pose_topic')
    drive_token_topic = LaunchConfiguration('drive_token_topic')
    heartbeat_topic = LaunchConfiguration('heartbeat_topic')
    estop_topic = LaunchConfiguration('estop_topic')
    motion_allowed_topic = LaunchConfiguration('motion_allowed_topic')
    safety_state_topic = LaunchConfiguration('safety_state_topic')
    accepted_token_topic = LaunchConfiguration('accepted_token_topic')
    database_path = LaunchConfiguration('database_path')
    mission_status_path = LaunchConfiguration('mission_status_path')
    report_outbox_path = LaunchConfiguration('report_outbox_path')

    push_namespace = LaunchConfiguration('push_namespace')

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
            'battery_state_topic',
            default_value='battery_state',
            description=(
                'Where the battery driver publishes sensor_msgs/BatteryState. '
                'Relative names resolve inside the robot namespace; pass an '
                'absolute name if the driver sits outside it (TBD-ARCH-001).'
            ),
        ),
        DeclareLaunchArgument(
            'battery_status_topic',
            default_value='battery_status',
            description='Internal classified battery status topic.',
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
            'output_topic',
            default_value='cmd_vel',
            description='Final velocity output; remap to a test sink off robot.',
        ),
        DeclareLaunchArgument(
            'drive_token_topic',
            default_value='/control/drive_token',
        ),
        DeclareLaunchArgument(
            'heartbeat_topic',
            default_value='/control/heartbeat',
        ),
        DeclareLaunchArgument(
            'estop_topic',
            default_value='/control/estop',
        ),
        DeclareLaunchArgument(
            'motion_allowed_topic',
            default_value='motion_allowed',
        ),
        DeclareLaunchArgument(
            'safety_state_topic',
            default_value='safety_state',
        ),
        DeclareLaunchArgument(
            'accepted_token_topic',
            default_value='accepted_token_id',
        ),
        DeclareLaunchArgument(
            'database_path',
            default_value='',
            description='Optional robot-specific command gateway SQLite path.',
        ),
        DeclareLaunchArgument(
            'mission_status_path',
            default_value='',
            description='Optional 3A mission_status.json path.',
        ),
        DeclareLaunchArgument(
            'report_outbox_path',
            default_value='',
            description='Optional 3A patrol_report_outbox.json path.',
        ),
        DeclareLaunchArgument(
            'push_namespace',
            default_value='true',
            description=(
                'Push /<robot_id> here. Pass false when the caller already '
                'wraps this file in its own PushRosNamespace, or the '
                'namespace is applied twice.'
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
        DeclareLaunchArgument(
            'pose_topic',
            default_value='amcl_pose',
            description=(
                'Where Nav2 AMCL publishes '
                'geometry_msgs/PoseWithCovarianceStamped.'
            ),
        ),
        GroupAction(
            [PushRosNamespace(robot_id), *_nodes(
                robot_id, source_session_id, safety_state,
                battery_state_topic, candidate_topic, odom_topic, pose_topic,
            )],
            condition=IfCondition(push_namespace),
        ),
        GroupAction(
            _nodes(
                robot_id, source_session_id, safety_state,
                battery_state_topic, candidate_topic, odom_topic, pose_topic,
            ),
            condition=UnlessCondition(push_namespace),
        ),
    ])
