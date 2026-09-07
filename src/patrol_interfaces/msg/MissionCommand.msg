# 관제 -> AMR 임무 명령.
#
# 토픽 : /{robot}/mission_command   ({robot} = robot1 | robot6)
# QoS  : RELIABLE / VOLATILE / KEEP_LAST(10)          (interfaces.md 9절)
#
# 전 필드가 [계약] 이다. interfaces.md 2절 전사이며 AMR 이 제안한 필드는 없다.

# ---- 명령 enum (interfaces.md 2절) --------------------------------------
uint8 STOP=0              # 즉시 정지. 임무 보존, mission=MISSION_PAUSED. PatrolReport 없음 (CR-002)
uint8 START_PATROL=1
uint8 MOVE_TO_SAFE_ZONE=2
uint8 RESUME_PATROL=3     # last_completed_waypoint 다음부터. parameters_json 지정이 우선 (CR-002)
uint8 DOCK=4
uint8 CANCEL=5            # 임무 종료. PatrolReport result=CANCELED 발행 (CR-002)

std_msgs/Header header

# UUID v4. 같은 내용의 재전송은 같은 ID, 내용·목적이 바뀌면 새 ID.
# AMR 은 최근 24시간 또는 1,000개를 영속 저장하고 중복 실행하지 않는다 (Q-14).
# 두 보존 조건의 우선순위·삭제 정책은 TBD-IF-001.
string command_id

# robot1 | robot6. 수신 로봇의 namespace 와 일치해야 한다 (architecture.md 2절).
string robot_id

uint8 command

# command 별 필수 여부와 우선순위는 TBD-IF-001. 메시지 레이아웃만 합의된 상태다.
string target_id
geometry_msgs/PoseStamped target_pose

string issued_by

# 스키마는 TBD-IF-001. RESUME_PATROL 의 재개 지점 키 이름·타입도 여기에 포함된다 (CR-002).
string parameters_json
