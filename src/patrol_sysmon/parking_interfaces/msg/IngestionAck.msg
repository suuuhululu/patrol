std_msgs/Header header
string message_id
string robot_id
uint8 entity_type
string source_message_id
string entity_id
uint8 status
uint32[] missing_chunks
string detail

uint8 PATROL_VISIT=0
uint8 PATROL_REPORT=1
uint8 DETECTION_EVENT=2
uint8 EVIDENCE=3

uint8 STORED=0
uint8 DUPLICATE=1
uint8 INCOMPLETE=2
uint8 REJECTED=3
