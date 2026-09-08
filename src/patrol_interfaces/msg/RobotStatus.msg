# AMR -> 관제·모니터. 로봇 상태 보고.
#
# 토픽 : /{robot}/robot_status
# QoS  : RELIABLE / VOLATILE / KEEP_LAST(5), deadline 500 ms
# 발행 : 정기 2 Hz. mission·safety·battery enum 또는 pose_valid 가 바뀌면 즉시,
#        변경 발행은 최대 10 Hz 로 제한한다.                         (Q-02)
#
# interfaces.md 4절의 의미 필드와 이름을 사용한다. STALE은 관제가 수신
# 신선도로 판정하므로 아래 operational enum에 추가하지 않는다.

# ---- operational : [계약] interfaces.md 4절 ------------------------------
uint8 OP_UNKNOWN=0
uint8 OP_INITIALIZING=1
uint8 OP_READY=2
uint8 OP_MOVING=3
uint8 OP_STOPPED_SAFETY=4
uint8 OP_CHARGING=5
uint8 OP_ERROR=6

# ---- mission : [계약] interfaces.md 4절 ----------------------------------
uint8 MISSION_NONE=0
uint8 MISSION_UNDOCKING=1
uint8 MISSION_PATROLLING=2
uint8 MISSION_MOVING_TO_SAFE_ZONE=3
uint8 MISSION_WAITING_SAFE_ZONE=4
uint8 MISSION_RETURNING_TO_DOCK=5
uint8 MISSION_DOCKING=6
uint8 MISSION_PAUSED=7             # STOP 이 생산한다 (CR-002)
uint8 MISSION_COMPLETED=8
uint8 MISSION_FAILED=9
uint8 MISSION_CANCELED=10

# ---- docking : [계약] interfaces.md 4절 ----------------------------------
uint8 DOCK_UNKNOWN=0
uint8 DOCK_UNDOCKED=1
uint8 DOCK_UNDOCKING=2
uint8 DOCK_DOCKING=3
uint8 DOCK_DOCKED=4
uint8 DOCK_FAILED=5

# ---- battery : [계약] interfaces.md 8절 ----------------------------------
# 접두사 없는 이름은 8절 표기를 그대로 옮긴 것이다. 임의로 바꾸지 않는다.
#   방전 <0.10 CRITICAL / 0.10~0.20 LOW / >=0.20 NORMAL
#   충전 <0.50 CHARGING / 0.50~0.80 PATROL_READY / >=0.80 FULL
#   무효·미수신 UNKNOWN.  CRITICAL 즉시, 나머지 3초 연속 유지 후 전이 (Q-11)
uint8 UNKNOWN=0
uint8 CRITICAL=1
uint8 LOW=2
uint8 NORMAL=3
uint8 CHARGING=4
uint8 PATROL_READY=5
uint8 FULL=6

# ---- safety : [계약] interfaces.md 4절 -----------------------------------
uint8 SAFETY_UNKNOWN=0
uint8 SAFETY_NORMAL=1
uint8 SAFETY_STOPPING=2
uint8 SAFETY_STOPPED=3
uint8 SAFETY_ESTOPPED=4
uint8 SAFETY_ERROR=5

std_msgs/Header header
string robot_id
string source_session_id
uint64 status_sequence

# ---- 상태 축 -------------------------------------------------------------
uint8 operational_state                                  # OP_*
uint8 mission_state                                      # MISSION_*
uint8 docking_state                                      # DOCK_*
uint8 battery_state                                      # UNKNOWN..FULL
uint8 safety_state                                       # SAFETY_*

string active_command_id
string active_mission_id

# ---- 위치 : 4절이 요구하는 3요소(map frame·측정 시각·covariance) ---------
geometry_msgs/PoseWithCovarianceStamped pose
bool pose_valid
geometry_msgs/PoseWithCovarianceStamped last_valid_pose

float32 linear_velocity
float32 angular_velocity
bool motion_stopped

string accepted_token_id
bool token_valid

float32 battery_soc
builtin_interfaces/Time battery_timestamp

string current_waypoint_id
string scan_state
uint32 reason_code
string reason
