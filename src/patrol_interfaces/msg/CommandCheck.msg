# AMR -> 관제. MissionCommand 수락·실행 여부 확인.
# 토픽: /{robot}/command_check
# QoS: RELIABLE / VOLATILE / KEEP_LAST(10)
# check_state 정수 매핑 (TBD-IF-001, 2026-09-08 확정).

uint8 CHECK_UNKNOWN=0
uint8 CHECK_ACCEPTED=1
uint8 CHECK_EXECUTING=2
uint8 CHECK_REJECTED=3

std_msgs/Header header
string command_id
string mission_id
string robot_id
uint8 check_state
uint32 reason_code
string reason
string source_session_id
uint64 sequence
