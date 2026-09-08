# AMR -> 관제. MissionCommand 수락·실행 여부 확인.
# 토픽: /{robot}/command_check
# QoS: RELIABLE / VOLATILE / KEEP_LAST(10)
#
# check_state 수치·전이는 interfaces.md 2.1절(2026-09-08 결정)을 따른다.
# 정상 전이는 ACCEPTED -> EXECUTING 이며 역방향은 관제가 폐기한다.
# 관제는 정의되지 않은 수치를 폐기하고 프로토콜 경고를 기록한다.

uint8 CHECK_UNKNOWN=0     # 초기·해석 불가. 정상 응답으로 쓰지 않는다
uint8 CHECK_ACCEPTED=1    # 형식·상태 검증 통과, 실행 대기열 진입
uint8 CHECK_EXECUTING=2   # 실제 command 실행 시작
uint8 CHECK_REJECTED=3    # command 를 실행하지 않음. reason_code 200~206 등

std_msgs/Header header
string command_id
string mission_id
string robot_id
uint8 check_state
uint32 reason_code
string reason
string source_session_id
uint64 sequence
