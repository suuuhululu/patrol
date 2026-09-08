# AMR -> control server command admission and execution state.
# Topic: /{robot}/command_check
# QoS: RELIABLE / VOLATILE / KEEP_LAST(10)
# check_state numeric values remain TBD-IF-001 and are intentionally not
# declared as constants here.

std_msgs/Header header
string command_id
string mission_id
string robot_id
uint8 check_state
uint32 reason_code
string reason
string source_session_id
uint64 sequence
