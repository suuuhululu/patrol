# AMR -> 관제·모니터. 로봇 상태 보고.
#
# 토픽 : /{robot}/robot_status
# QoS  : RELIABLE / VOLATILE / KEEP_LAST(5), deadline 500 ms
# 발행 : 정기 2 Hz. mission·safety·battery enum 또는 pose_valid 가 바뀌면 즉시,
#        변경 발행은 최대 10 Hz 로 제한한다.                         (Q-02)
#
# 필드 등급 (CR-001)
#   [계약]     interfaces.md 에 필드·타입·enum 이 그대로 적힌 것
#   [TBD 충전] 4절 마지막 문장이 지목했으나 타입이 TBD 로 남은 것
#   [제안]     동작 요구에서 도출했으나 필드로 명시된 적 없는 것 — 관제 검토 필요
#
# STALE 은 관제가 수신 신선도로 판정하는 상태다(Q-03). 아래 어느 enum 에도 넣지 않는다.

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

# ---- safety : [제안] ------------------------------------------------------
# 4절이 "safety enum과 필드 구조는 아직 미정"이라 축만 지정했다.
# 원인 목록은 amr.md 3절(token·heartbeat·장애물), 7절 보존 로그, TBD-AMR-006 에서 도출.
uint8 SAFETY_UNKNOWN=0
uint8 SAFETY_OK=1
uint8 SAFETY_ESTOP_ACTIVE=2
uint8 SAFETY_TOKEN_INVALID=3
uint8 SAFETY_COMM_LOST=4           # heartbeat 계약(TBD-IF-004) 확정 전까지 미사용
uint8 SAFETY_OBSTACLE_BLOCKED=5
uint8 SAFETY_SENSOR_FAULT=6

# ---- scan_state : [제안] --------------------------------------------------
# 회전 횟수·완료 판정 기준은 TBD-AMR-005. 여기서는 값만 정한다.
uint8 SCAN_NONE=0
uint8 SCAN_IN_PROGRESS=1
uint8 SCAN_COMPLETED=2

std_msgs/Header header
string robot_id                                          # [계약] robot1 | robot6

# ---- 상태 축 -------------------------------------------------------------
uint8 operational                                        # [계약] OP_*
uint8 mission                                            # [계약] MISSION_*
uint8 docking                                            # [계약] DOCK_*
uint8 battery                                            # [계약] UNKNOWN..FULL
uint8 safety                                             # [제안] SAFETY_*

# ---- 위치 : 4절이 요구하는 3요소(map frame·측정 시각·covariance) ---------
geometry_msgs/PoseWithCovarianceStamped pose             # [계약]
bool pose_valid                                          # [계약]
# pose_valid=false 여도 아래를 보존한다. 이를 현재 유효 위치로 사용하지 않는다.
geometry_msgs/PoseWithCovarianceStamped last_valid_pose  # [계약]
builtin_interfaces/Time last_valid_pose_stamp            # [계약]
builtin_interfaces/Duration last_valid_pose_age          # [계약]

# ---- 순찰 진행 -----------------------------------------------------------
uint32 patrol_id                                         # [TBD 충전] 순찰 ID
uint32 visit_id                                          # [TBD 충전] 방문 ID
# 값은 waypoint 번호(WP1..WP7)다. 경로 상의 몇 번째 단계인지가 아니다.
# 경로가 같은 waypoint 를 두 번 지나면(예: 1-2-3-4-5-6-3-7-1 의 WP3) 이 값만으로는
# 재개 지점이 하나로 정해지지 않는다. AMR 은 내부 단계 번호로 재개하고 관제는
# parameters_json 으로 덮어쓸 수 있다(CR-002). 필드 추가 여부는 CR-004.
uint8  current_waypoint                                  # [TBD 충전] waypoint
uint8  last_completed_waypoint                           # [TBD 충전] waypoint
builtin_interfaces/Time last_visit_stamp                 # [TBD 충전] 방문 시각
uint8  scan_state                                        # [TBD 충전] scan 상태

# ---- 명령·안전·부속 ------------------------------------------------------
string command_id                                        # [제안] 수행 중인 명령
bool   motion_stopped                                    # [제안] 정지 요청이 아니라 실제 정지 관측
bool   estop_physical_latched                            # [제안] 물리 latch 유지 여부 (Q-10)
bool   alarm_active                                      # [제안] 화재 부저 상태
bool   keepout_applied                                   # [제안] 자기 costmap read-back
geometry_msgs/Pose safe_zone_goal                        # [제안] 선택한 대피 지점
float32 battery_percentage                               # [제안] SOC 원본. 관제의 가용 로봇 순위용
