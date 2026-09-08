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
uint8 RESUME_PATROL=3     # 재개할 기존 mission ID 필수. CANCEL 된 mission 은 재개 불가
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

# command 별 필수값 (interfaces.md 2절, 2026-09-08 결정). 빈 값은 타입 기본값이다.
#   STOP              mission_id: 활성 mission 있으면 해당 ID   target_id: 빈 값
#   START_PATROL      mission_id: 새 ID 필수                   target_id: patrol_plan_id 필수
#   MOVE_TO_SAFE_ZONE mission_id: 활성 mission ID 필수         target_id: 빈 값
#   RESUME_PATROL     mission_id: 재개할 mission ID 필수       target_id: 빈 값
#   DOCK              mission_id: 기존 또는 신규 ID 필수       target_id: dock_1 | dock_6
#   CANCEL            mission_id: 취소할 활성 mission ID 필수  target_id: 빈 값
string target_id

# 합의된 명령에서는 사용하지 않는다. 필드 제거는 AMR 검토 후 결정하므로 유지한다.
geometry_msgs/PoseStamped target_pose

string issued_by

# parameters_json 은 2026-09-08 계약에서 제거됐다. 명령별 값 오류는 INVALID_PARAMETERS(205)다.
