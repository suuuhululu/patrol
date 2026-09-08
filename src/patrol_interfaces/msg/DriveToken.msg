# 관제 -> AMR 로컬 안전. 주행 권한 토큰.
#
# 토픽 : /control/drive_token   (로봇별이 아니라 공통 토픽 하나다)
# QoS  : BEST_EFFORT / VOLATILE / KEEP_LAST(3), deadline 200 ms, lifespan 500 ms
# 발행 : 5 Hz, lease 1.0초, 경과는 AMR 로컬 monotonic 으로 측정  (Q-01)
#
# 전 필드가 [계약] 이다. interfaces.md 3절 전사.
#
# 수락 규칙 (interfaces.md 3절)
#   - token_id 가 빈 문자열이면 관제가 지정 holder 권한을 회수한 상태다.
#   - 다른 holder 의 토큰은 자신의 주행 권한으로 수락하지 않는다.
#   - control_session_id 또는 token_id 가 바뀌면 기존 token 을 즉시 무효화한다.
#   - 같은 control session 의 message_sequence 가 마지막 값 이하면 폐기한다.
#   - callback 수신 시각만으로 lease 를 연장하지 않는다.
#   - 만료·회수 시 신규 주행을 차단하고 안전 정지한다.
#   - 새 토큰 수신만으로 자동 출발하지 않는다.

std_msgs/Header header

string control_session_id
string token_id                           # 빈 문자열 = 지정 holder 권한 회수
string holder_robot_id                    # robot1 | robot6
builtin_interfaces/Duration lease_duration
uint64 message_sequence
