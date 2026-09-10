# Control Server -> AMR local_safety_supervisor.
# 토픽: /{robot}/drive_token
# 빈 token은 권한 회수다. Token 수신만으로 자동 출발하지 않는다.
std_msgs/Header header
string token
string holder_robot_id
builtin_interfaces/Duration lease_duration
uint32 sequence
