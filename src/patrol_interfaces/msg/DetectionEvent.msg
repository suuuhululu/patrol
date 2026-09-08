std_msgs/Header header

string event_id
string source_session_id
uint64 source_sequence

string robot_id
string mission_id
string command_id

uint8 FIRE=0
uint8 LEAK=1
uint8 OBSTACLE=2
uint8 event_type

float32 confidence
string evidence_id

sensor_msgs/CompressedImage image
