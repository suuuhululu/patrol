std_msgs/Header header
string message_id
string event_id
string robot_id
uint8 event_type
geometry_msgs/PoseWithCovariance pose
bool location_valid
builtin_interfaces/Time detected_at
string evidence_id

uint8 FIRE=0
uint8 LEAK=1
uint8 OBSTACLE=2