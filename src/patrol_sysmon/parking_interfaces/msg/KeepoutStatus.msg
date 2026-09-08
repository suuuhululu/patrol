std_msgs/Header header
string message_id
string transaction_id
string robot_id
uint8 state
bool global_enabled
bool local_enabled
uint16 reason_code
string detail

uint8 UNKNOWN=0
uint8 DISABLED=1
uint8 APPLIED=2
uint8 ROLLED_BACK=3
uint8 ROLLBACK_FAILED=4
