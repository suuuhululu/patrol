# CCTV gate_cam / center_cam -> cam_master.
# gate_event는 ENTERING/EXITED, center_event는 PARKED/EXITING만 허용한다.

std_msgs/Header header
string event_id
string camera_id
string source_session_id
uint64 source_sequence
uint8 state
float32 confidence

uint8 STATE_UNKNOWN=0
uint8 STATE_ENTERING=1
uint8 STATE_EXITED=2
uint8 STATE_PARKED=3
uint8 STATE_EXITING=4