# CameraState.msg
# gate_cam.py / center_cam.py 가 발행하고 cam_master.py 가 구독하는 공통 계약.
# interfaces.md 6절 기준. TBD-IF-005(패키지·state 정수 매핑·camera_id·event_id 생성 규칙)는
# CR-관제_09-07_17-53_비전_CameraState와_permit_반영 반영으로 확정.
#
# gate topic(/vision/cctv/gate_event) 허용 state: STATE_ENTERING, STATE_EXITED
#   camera_id는 'gate_cam'만 허용한다.
# center topic(/vision/cctv/center_event) 허용 state: STATE_PARKED, STATE_EXITING
#   camera_id는 'center_cam'만 허용한다.
# 그 외 state 또는 camera_id가 들어오면 cam_master가 폐기하고 진단 로그를 남긴다 (vision.md 4절).
#
# source_session_id = <camera_id>-<YYYYMMDDTHHMMSS>-<restart_sequence>
# event_id           = cam-<source_session_id>-<state 소문자>-<source_sequence, 4자리 0채움>
# source_sequence는 노드 시작 후 1부터 증가하며 상태가 바뀌어도 초기화하지 않는다.
# 수신 로직(cam_master)은 event_id 문자열을 파싱하지 않고 별도 필드·enum만 사용한다.
#
# vehicle_track_id는 사용하지 않는다. 차량은 한 대만 존재한다 (vision.md 2절).
#
# 대시보드용 CCTV 영상 스트림(/vision/cctv/gate_image/compressed,
# /vision/cctv/center_image/compressed, sensor_msgs/CompressedImage)은 이 메시지와
# 별개의 독립된 토픽이며, 이 .msg 파일에는 영향이 없다
# (CR-비전_09-08_12-21_대시보드_CCTV_영상_스트림_추가 참고).

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