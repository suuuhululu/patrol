# AMR 내부 command gateway <-> mission supervisor 실행 수명 이벤트.
# 토픽: /{robot}/mission_execution_event
# QoS: RELIABLE / TRANSIENT_LOCAL / KEEP_LAST(20)

uint8 ADMITTED=1
uint8 REJECTED=2
uint8 STARTED=3
uint8 NONTERMINAL_STORED=4
uint8 RESULT_STORED=5

std_msgs/Header header
string command_id
string mission_id
string robot_id
uint8 event_type
string source_session_id
uint64 sequence
uint8 mission_state
uint32 reason_code
string reason

# RESULT_STORED일 때 Patrol.action Result를 평탄화해 보관한다.
# result_outcome, result_reason_code, result_reason의 값은 Patrol.action Result와 같다.
bool has_result
uint8 result_outcome
uint16 result_reason_code
string result_reason
