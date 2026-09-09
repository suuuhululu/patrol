# 비전 detecting node가 정렬 후 1초 검증의 종결 결과를 AMR에 알린다.
# candidate_id는 DetectionCandidate와 AlignmentStatus에서 받은 값을 유지한다.
# CONFIRMED는 DetectionEvent와 EvidenceChunk를 로컬 재전송 큐에 등록한 뒤 발행한다.
# System monitor의 IngestionAck 수신은 이 결과와 AMR 내부 재개의 선행 조건이 아니다.

std_msgs/Header header
string robot_id
string candidate_id
string event_id

uint8 CONFIRMED=0
uint8 VERIFY_FAILED=1
uint8 INTERNAL_ERROR=2
uint8 result

# 사람용 진단 설명이다. AMR 제어 분기는 result를 기준으로 한다.
string detail
