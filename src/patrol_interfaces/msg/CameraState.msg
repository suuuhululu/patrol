# CameraState.msg
# gate_cam.py / center_cam.py 가 발행하고 cam_master.py 가 구독하는 공통 계약.
# interfaces.md 6절 기준으로 맞춤. state 정수 매핑과 event_id 생성 규칙 자체는
# TBD-IF-005 (비전·관제 공동 결정)로, 아래 값은 비전팀 제안이며 관제팀 확정 전이다.
#
# gate topic(/vision/cctv/gate_event) 허용 state: STATE_ENTERING, STATE_EXITED
# center topic(/vision/cctv/center_event) 허용 state: STATE_PARKED, STATE_EXITING
# 그 외 state가 들어오면 cam_master가 폐기하고 진단 로그를 남긴다 (vision.md 4절).
#
# vehicle_track_id는 사용하지 않는다. 차량은 한 대만 존재한다 (vision.md 2절).

std_msgs/Header header
string event_id
string camera_id
uint8 state
float32 confidence

uint8 STATE_UNKNOWN=0
uint8 STATE_ENTERING=1
uint8 STATE_EXITED=2
uint8 STATE_PARKED=3
uint8 STATE_EXITING=4
