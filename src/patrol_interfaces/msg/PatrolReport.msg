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
# 결과 재전송·중복 수신·복구 전달은 TBD-IF-003.

# ---- result : [계약] interfaces.md 5절 -----------------------------------
uint8 SUCCEEDED=0     # 목표 정상 달성
uint8 FAILED=1        # 자체 장애·주행 실패·위치 검증 또는 시스템 실패
uint8 CANCELED=2      # 관제 취소·명령 대체·정책 중단·역할 교대

# ---- reason_code : [계약] interfaces.md 5절 29종 -------------------------
# FAILED·CANCELED 는 필수다. 최대값이 1001 이라 uint16 이다.
uint16 NONE=0
uint16 CONTROL_CANCELED=100
uint16 COMMAND_SUPERSEDED=101
uint16 SAFETY_POLICY_CANCELED=102
uint16 INVALID_COMMAND=200
uint16 INVALID_TARGET=201
uint16 UNSUPPORTED_COMMAND=202
uint16 NAV_NO_PATH=300
uint16 NAV_TIMEOUT=301
uint16 NAV_GOAL_REJECTED=302
uint16 NAV_GOAL_ABORTED=303
uint16 SAFE_ZONE_NOT_FOUND=400
uint16 KEEPOUT_APPLY_FAILED=401
uint16 KEEPOUT_ROLLBACK_FAILED=402
uint16 LOCALIZATION_INVALID=500
uint16 POSE_STALE=501
uint16 LIDAR_VERIFICATION_FAILED=502
uint16 DRIVE_TOKEN_MISSING=600
uint16 DRIVE_TOKEN_EXPIRED=601
uint16 COMMUNICATION_LOST=602
uint16 E_STOP_ACTIVE=700
uint16 OBSTACLE_BLOCKED=701
uint16 FIRE_DETECTED=702
uint16 BATTERY_LOW=800
uint16 BATTERY_CRITICAL=801
uint16 DOCKING_TIMEOUT=900
uint16 ROLE_HANDOFF=901
uint16 SENSOR_ERROR=1000
uint16 INTERNAL_ERROR=1001

std_msgs/Header header
string robot_id        # [계약]
string command_id      # [TBD 충전] 5절 "command_id 연결"
string report_id       # [TBD 충전] 5절 "report ID 연결"
uint32 patrol_id       # [TBD 충전] 5절 "mission/patrol ID 연결"
uint8  result          # [계약] SUCCEEDED | FAILED | CANCELED
uint16 reason_code     # [계약] 위 29종. FAILED·CANCELED 필수
string reason          # [계약] 구체적 진단값
