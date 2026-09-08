# 관제 -> AMR 임무 명령.
#
# 토픽 : /{robot}/mission_command   ({robot} = robot1 | robot6)
# QoS  : RELIABLE / VOLATILE / KEEP_LAST(10)          (interfaces.md 9절)
#
# interfaces.md 2절의 확정 의미 필드를 그대로 사용한다.

# ---- 명령 enum (interfaces.md 2절) --------------------------------------
uint8 STOP=0              # 정지. 임무 보존, mission_state=MISSION_PAUSED. PatrolReport 없음
uint8 START_PATROL=1
uint8 MOVE_TO_SAFE_ZONE=2
uint8 RESUME_PATROL=3     # last_completed_waypoint 다음부터
uint8 DOCK=4
uint8 CANCEL=5            # 임무 종료. PatrolReport result=CANCELED 발행 (CR-002)

std_msgs/Header header

# 사람이 식별 가능한 세션·sequence 기반 ID. 같은 내용의 재전송은 같은 ID다.
# AMR 은 24시간 이내 전체와 그보다 오래된 항목 중 최신 1,000개를 유지한다.
string command_id

# 같은 순찰의 대피·재개·복귀·도킹은 이 ID를 유지한다.
string mission_id

# robot1 | robot6. 수신 로봇의 namespace 와 일치해야 한다 (architecture.md 2절).
string robot_id

uint8 command

# command 별 target 필수 여부는 interfaces.md 2절을 따른다.
string target_id
geometry_msgs/PoseStamped target_pose

string issued_by
