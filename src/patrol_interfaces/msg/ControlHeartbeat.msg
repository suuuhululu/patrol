# 관제 -> 각 AMR 로컬 안전. 관제 생존 신호.
#
# 토픽 : /control/heartbeat
# QoS  : BEST_EFFORT / VOLATILE / KEEP_LAST(3)
# 발행 : 5 Hz. AMR 은 1초 미수신을 timeout 으로 판단해 로컬 안전 정지한다.
#
# interfaces.md 3.1절(2026-09-08 결정)을 그대로 옮긴다. 새 control_session_id 를
# 받으면 AMR 은 이전 heartbeat·token 상태를 무효화한다. heartbeat 복구만으로
# 자동 재출발하지 않는다.

std_msgs/Header header
string control_session_id
uint64 sequence
