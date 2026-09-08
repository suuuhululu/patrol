# AMR -> 관제·모니터. 임무 결과 보고.
#
# 토픽 : /{robot}/patrol_report
# QoS  : RELIABLE / VOLATILE / KEEP_LAST(20)
#
# result 는 3값 고정이다. UNREPORTED 를 추가하지 않는다 — 결과가 없는 임무는
# 관제가 UNREPORTED 로 유지하며 보고서를 대필하지 않는다 (interfaces.md 5절).
# 그래서 대필 표시 필드도 두지 않는다.
#
# STOP 은 보존형이라 보고서를 내지 않고 mission=MISSION_PAUSED 로만 표현한다.
# CANCEL 은 종료형이라 result=CANCELED 로 1회 발행한다.            (CR-002)
#
# 같은 report_id로 재전송하며 수신자는 중복 제거한다.

# ---- result : [계약] interfaces.md 5절 -----------------------------------
uint8 SUCCEEDED=0     # 목표 정상 달성
uint8 FAILED=1        # 자체 장애·주행 실패·위치 검증 또는 시스템 실패
uint8 CANCELED=2      # 관제 취소·명령 대체·정책 중단·역할 교대

# ---- reason_code : interfaces.md 6절 -------------------------------------
uint32 NONE=0
uint32 CONTROL_CANCELED=100
uint32 COMMAND_SUPERSEDED=101
uint32 SAFETY_POLICY_CANCELED=102
uint32 INVALID_COMMAND=200
uint32 INVALID_TARGET=201
uint32 UNSUPPORTED_COMMAND=202
uint32 COMMAND_ID_CONFLICT=203
uint32 INVALID_MISSION=204
uint32 INVALID_PARAMETERS=205
uint32 INVALID_STATE=206
uint32 NAV_NO_PATH=300
uint32 NAV_TIMEOUT=301
uint32 NAV_GOAL_REJECTED=302
uint32 NAV_GOAL_ABORTED=303
uint32 SAFE_ZONE_NOT_FOUND=400
uint32 KEEPOUT_APPLY_FAILED=401
uint32 KEEPOUT_ROLLBACK_FAILED=402
uint32 LOCALIZATION_INVALID=500
uint32 POSE_STALE=501
uint32 LIDAR_VERIFICATION_FAILED=502
uint32 DRIVE_TOKEN_MISSING=600
uint32 DRIVE_TOKEN_EXPIRED=601
uint32 COMMUNICATION_LOST=602
uint32 E_STOP_ACTIVE=700
uint32 OBSTACLE_BLOCKED=701
uint32 FIRE_DETECTED=702
uint32 BATTERY_LOW=800
uint32 BATTERY_CRITICAL=801
uint32 DOCKING_TIMEOUT=900
uint32 ROLE_HANDOFF=901
uint32 SENSOR_ERROR=1000
uint32 INTERNAL_ERROR=1001

std_msgs/Header header
string report_id
string robot_id
string source_session_id
string command_id
string mission_id
uint8 result
uint32 reason_code
string reason
builtin_interfaces/Time started_at
builtin_interfaces/Time finished_at
string final_waypoint_id
string[] related_event_ids
