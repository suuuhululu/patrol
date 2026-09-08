# Safety Arbiter(관제) -> AMR·모니터. 비상정지 상태.
#
# 토픽 : /control/estop
# QoS  : RELIABLE / TRANSIENT_LOCAL, 발행자 하나. depth 는 9절이 TBD 로 남긴 상태다.
#
# interfaces.md 3.1절의 확정 의미 필드를 사용한다. reason enum 수치와 전체
# 대상 문자열은 TBD-IF-004라 이 메시지에서 임의 상수를 만들지 않는다.
# AMR은 활성 상태를 반영하며 비물리 자동 해제 3초 판정은 Safety Arbiter가 한다.

std_msgs/Header header
string target_robot_id                 # robot1 | robot6 | 전체 대상 값(TBD)
bool active
uint8 reason                            # enum 수치 TBD-IF-004
bool latched                            # 물리 E-stop은 수동 reset까지 true
uint64 sequence
