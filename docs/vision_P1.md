# 비전 P1 권장안

상태: 권장안 · 작성일: 2026-09-07 · 대상: 비전·관제·시스템 모니터

이 문서는 P0 구현 요구사항이 아니라 P0 완료 이후 검토할 개선안만 정리한다. 채택 전에는 공용 인터페이스나 비전 코드의 구현 계약으로 사용하지 않는다. P0 확정 사항과 비전팀 요청 범위는 [비전 수정 요청서](change_requests/CR-관제_09-07_17-53_비전_CameraState와_permit_반영.md)를 따른다.

## P1-1. permit 전용 메시지 도입

현재 `/vision/cctv/patrol_allowed`의 `std_msgs/msg/Bool`은 값만 전달하므로 cam_master 재시작, 메시지 역순, 발행 누락을 구분할 수 없다. 향후 아래 의미를 가진 `patrol_interfaces` 전용 메시지로 교체하거나 상태 토픽을 병행하는 방안을 권장한다.

~~~text
std_msgs/Header header
bool patrol_allowed
string source_session_id
uint64 publish_sequence
string cause_event_id
~~~

- source_session_id는 cam_master 프로세스가 시작될 때 생성하고 재시작하면 변경한다.
- publish_sequence는 같은 세션에서 상태 변경·주기 발행을 모두 포함해 매 발행마다 증가시킨다.
- 관제 정상 복구는 같은 source_session_id, 증가하는 publish_sequence, 3회 연속 수신을 함께 확인한다.
- 정확한 메시지명, 토픽 전환 방식, 구버전 Bool 병행 기간은 공용 인터페이스 합의 후 결정한다.

## P1-2. cam_master 재시작 복구

마지막 permit, 마지막으로 반영한 source별 sequence와 event_id 중복 캐시를 영속 저장하는 방안을 권장한다. 재시작 직후 무조건 true로 초기화하는 현재 방식과의 전환 규칙, 저장 손상 시 안전한 초기 상태, 보존 기간은 별도 합의가 필요하다.

## P1-3. 이벤트 순서 판정 강화

전체 카메라 이벤트를 하나의 header timestamp로만 비교하지 않고 camera_id·source_session_id별 source_sequence를 우선 검증하는 방안을 권장한다. 서로 다른 카메라의 시계 오차 때문에 정상 이벤트가 폐기되는 문제를 줄일 수 있다. 세션 전환과 늦게 도착한 이전 세션 이벤트의 처리 규칙은 시험 fixture로 확정한다.

## P1-4. 비전 상태·장애 전달

프레임 읽기 실패, 모델 로드 실패, 추론 정지, 카메라 복구를 관제와 시스템 모니터에 구조화해 전달하는 상태 메시지를 권장한다. camera_id, source_session_id, 상태, 원인, 발생 시각, 마지막 정상 프레임 시각을 후보 필드로 하며 토픽·enum·QoS는 공용 계약 검토 후 정한다.

## P1-5. 설정과 자동 시험

- 카메라 장치, 모델 경로, ROI, confidence, PARKED 시간, 이벤트 cooldown, 디버그 화면을 ROS parameter/YAML로 분리한다.
- 녹화 영상 또는 고정 fixture로 0.2초 경계, FPS 변동, 미검출, ROI 흔들림, 재시작·역순·중복을 자동 회귀 시험한다.
- 실환경 측정 결과를 남기고 설정 버전과 모델 checksum을 진단 로그에 연결한다.

## 채택 조건

각 권장안은 영향받는 개발 단위가 공용 메시지·호환성·배포 순서를 합의하고 별도 수정 요청서와 코드 승인을 받은 뒤 P0 계약으로 승격한다.
