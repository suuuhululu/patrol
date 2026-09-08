# Safety Arbiter(관제) -> AMR·모니터. 비상정지 상태.
#
# 토픽 : /control/estop
# QoS  : RELIABLE / TRANSIENT_LOCAL, 발행자 하나. depth 는 9절이 TBD 로 남긴 상태다.
#
# interfaces.md 3.1절의 2026-09-08 확정 의미를 사용한다.
# AMR은 robot1/robot6/all 대상의 대표 reason 하나를 반영하고,
# 해제 3초 판정은 Safety Arbiter가 한다.

uint8 ESTOP_REASON_UNKNOWN=0
uint8 ESTOP_REASON_OPERATOR=1
uint8 ESTOP_REASON_COMMUNICATION=2
uint8 ESTOP_REASON_TOKEN=3
uint8 ESTOP_REASON_OBSTACLE=4
uint8 ESTOP_REASON_KEEPOUT_FAILURE=5
uint8 ESTOP_REASON_SYSTEM_FAULT=6

std_msgs/Header header
string target_robot_id                 # robot1 | robot6 | all
bool active
uint8 reason                            # ESTOP_REASON_*
uint64 sequence
