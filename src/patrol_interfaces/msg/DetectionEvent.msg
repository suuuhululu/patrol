std_msgs/Header header
string message_id
string event_id
string robot_id
uint8 event_type
float32 confidence
uint8 risk_level
geometry_msgs/PoseWithCovariance pose
bool location_valid
builtin_interfaces/Time detected_at
string evidence_id

uint8 EVENT_UNKNOWN=0
uint8 FIRE=1
uint8 LEAK=2
uint8 OBSTACLE=3
uint8 LIGHTING=4
uint8 FACILITY_DAMAGE=5

uint8 RISK_UNKNOWN=0
uint8 RISK_LOW=1
uint8 RISK_MEDIUM=2
uint8 RISK_HIGH=3
