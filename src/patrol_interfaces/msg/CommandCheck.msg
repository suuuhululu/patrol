# AMR -> 관제. MissionCommand 수락·실행 여부 확인.
# 토픽: /{robot}/command_check
# QoS: RELIABLE / VOLATILE / KEEP_LAST(10)
# check_state 정수 매핑은 TBD-IF-001이므로 상수를 임의로 정의하지 않는다.

std_msgs/Header header
string command_id
string mission_id
string robot_id
uint8 check_state
uint32 reason_code
string reason
string source_session_id
uint64 sequence
