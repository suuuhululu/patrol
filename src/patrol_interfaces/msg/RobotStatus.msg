# AMR -> control server and system monitor state snapshot.
# Topic: /{robot}/robot_status
# QoS: RELIABLE / VOLATILE / KEEP_LAST(5), deadline 500 ms.

uint8 OP_UNKNOWN=0
uint8 OP_INITIALIZING=1
uint8 OP_READY=2
uint8 OP_MOVING=3
uint8 OP_STOPPED_SAFETY=4
uint8 OP_CHARGING=5
uint8 OP_ERROR=6

uint8 MISSION_NONE=0
uint8 MISSION_UNDOCKING=1
uint8 MISSION_PATROLLING=2
uint8 MISSION_MOVING_TO_SAFE_ZONE=3
uint8 MISSION_WAITING_SAFE_ZONE=4
uint8 MISSION_RETURNING_TO_DOCK=5
uint8 MISSION_DOCKING=6
uint8 MISSION_PAUSED=7
uint8 MISSION_COMPLETED=8
uint8 MISSION_FAILED=9
uint8 MISSION_CANCELED=10

uint8 DOCK_UNKNOWN=0
uint8 DOCK_UNDOCKED=1
uint8 DOCK_UNDOCKING=2
uint8 DOCK_DOCKING=3
uint8 DOCK_DOCKED=4
uint8 DOCK_FAILED=5

uint8 UNKNOWN=0
uint8 CRITICAL=1
uint8 LOW=2
uint8 NORMAL=3
uint8 CHARGING=4
uint8 PATROL_READY=5
uint8 FULL=6

std_msgs/Header header
string robot_id
string source_session_id
uint64 status_sequence
uint8 operational_state
uint8 mission_state
uint8 docking_state
uint8 battery_state
uint8 safety_state
string active_command_id
string active_mission_id
geometry_msgs/PoseWithCovarianceStamped pose
bool pose_valid
geometry_msgs/PoseWithCovarianceStamped last_valid_pose
float32 linear_velocity
float32 angular_velocity
bool motion_stopped
string accepted_token_id
bool token_valid
float32 battery_soc
builtin_interfaces/Time battery_timestamp
string current_waypoint_id
string scan_state
uint32 reason_code
string reason
