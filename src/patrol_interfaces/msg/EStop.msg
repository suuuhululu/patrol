# 향후 Safety Arbiter -> AMR 비상정지 예약 인터페이스.
# 토픽: /control/estop
# 현재 기본 구현에는 publisher, subscriber, 상태 판단을 포함하지 않는다.
std_msgs/Header header
string target_robot_id
bool active
uint8 reason
uint64 sequence
