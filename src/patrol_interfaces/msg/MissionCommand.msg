# Control server -> AMR mission request.
# Topic: /{robot}/mission_command
# QoS: RELIABLE / VOLATILE / KEEP_LAST(10)

uint8 STOP=0
uint8 START_PATROL=1
uint8 MOVE_TO_SAFE_ZONE=2
uint8 RESUME_PATROL=3
uint8 DOCK=4
uint8 CANCEL=5

std_msgs/Header header
string command_id
string mission_id
string robot_id
uint8 command
string target_id
geometry_msgs/PoseStamped target_pose
string issued_by
string parameters_json
