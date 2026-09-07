# Safety Arbiter(관제) -> AMR·모니터. 비상정지 상태.
#
# 토픽 : /control/estop
# QoS  : RELIABLE / TRANSIENT_LOCAL, 발행자 하나. depth 는 9절이 TBD 로 남긴 상태다.
#
# 전 필드가 [제안] 이다. interfaces.md 1절이 "전체 정의 TBD"로만 남긴 항목이다.
#
# AMR 의 역할은 반영뿐이다. 활성화는 즉시 반영하고, 자동 해제 조건 3초 연속의
# 판정 주체는 관제다(Q-10). 물리 E-stop 은 수동 reset 까지 latch 한다.
# E-stop 해제 부저는 없다 — 화재 부저와 정책을 혼용하지 않는다 (amr.md 7절).

uint8 CAUSE_UNKNOWN=0
uint8 CAUSE_PHYSICAL_BUTTON=1
uint8 CAUSE_OPERATOR=2
uint8 CAUSE_COMM_LOST=3
uint8 CAUSE_TOKEN_INVALID=4
uint8 CAUSE_OBSTACLE=5
uint8 CAUSE_SENSOR_FAULT=6

std_msgs/Header header

bool   active
uint8  cause                                    # CAUSE_*
bool   physical                                 # true = 수동 reset 까지 latch 대상 (Q-10)
string source                                   # 최초 원인 노드
uint32 sequence                                 # 상태 변경 일련번호. 재수신·역순 구분용

builtin_interfaces/Time activated_at
# 관제가 해제 조건 연속 유지를 시작했다고 판정한 시각. AMR 은 자체 타이머를 두지 않고
# 이 값을 그대로 기록한다 (amr.md 7절 E_STOP_RELEASE_CONDITION_STARTED / IT-11).
builtin_interfaces/Time release_condition_started_at
