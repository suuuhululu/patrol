# Control Server -> AMR mission_supervisor.
# 실행 중인 Patrol Action을 종료하지 않고 내부 상태를 변경한다.

uint8 MOVE_TO_SAFE_ZONE=1
uint8 RESUME_PATROL=2

std_msgs/Header header
string command_id
string robot_id
uint8 command
