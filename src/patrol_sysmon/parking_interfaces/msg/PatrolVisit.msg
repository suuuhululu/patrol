std_msgs/Header header
string message_id
string visit_id
string command_id
string mission_id
string patrol_id
string robot_id
string waypoint_id
geometry_msgs/PoseStamped pose
uint8 result
uint16 reason_code
string reason
builtin_interfaces/Time arrived_at
builtin_interfaces/Time completed_at

uint8 SUCCEEDED=0
uint8 SKIPPED=1
uint8 FAILED=2
