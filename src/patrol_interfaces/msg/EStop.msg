# Safety Arbiter(관제) -> AMR·시스템 모니터. 비상정지 상태.
#
# 토픽 : /control/estop
# QoS  : RELIABLE / TRANSIENT_LOCAL, 발행자 하나(Safety Arbiter). depth 는 9절 기준.
#
# interfaces.md 3.1절(2026-09-08 결정)을 그대로 옮긴다.
# - 하드웨어·물리 E-stop 과 수동 reset 은 구현 범위 밖이므로 latched 필드가 없다.
# - 관제는 대상별 활성 원인 집합을 내부에 두고 여기에는 v1.0 우선순위
#   SYSTEM_FAULT > UNKNOWN > OPERATOR > KEEPOUT_FAILURE > COMMUNICATION >
#   OBSTACLE > TOKEN 에서 가장 먼저 활성인 대표 원인 하나만 싣는다.
#   전체 집합(active_reasons)은 차기 버전 TBD-IF-011 별도 계약이다.
# - 해제(active=false)는 모든 활성 원인이 3초 연속 사라진 뒤에만 발행한다. 해제
#   뒤에도 AMR 은 새 Drive Token 과 별도 MissionCommand 를 모두 받은 뒤 이동한다.
# - 원인별 상세 활성·해제 조건은 차기 버전 TBD-IF-004 로 남아 있다.

# ---- reason : [계약] interfaces.md 3.1절 ---------------------------------
uint8 ESTOP_REASON_UNKNOWN=0          # 원인을 신뢰할 수 없거나 아직 분류하지 못함
uint8 ESTOP_REASON_OPERATOR=1         # 시스템 모니터 UI 를 통한 운영자 정지 요청
uint8 ESTOP_REASON_COMMUNICATION=2    # 관제·AMR 안전 통신 상실 또는 timeout
uint8 ESTOP_REASON_TOKEN=3            # Drive Token 누락·만료·회수로 주행 권한이 없음
uint8 ESTOP_REASON_OBSTACLE=4         # 로컬 장애물 안전 차단
uint8 ESTOP_REASON_KEEPOUT_FAILURE=5  # Keepout 적용·확인·rollback 실패
uint8 ESTOP_REASON_SYSTEM_FAULT=6     # 센서·구동·안전 감독 등 시스템 고장

# ---- target : [계약] interfaces.md 3.1절 ---------------------------------
string TARGET_ALL="all"               # robot1·robot6 모두 대상

std_msgs/Header header
string target_robot_id                 # robot1 | robot6 | all
bool active
uint8 reason                            # ESTOP_REASON_* 대표 원인 하나
uint64 sequence
