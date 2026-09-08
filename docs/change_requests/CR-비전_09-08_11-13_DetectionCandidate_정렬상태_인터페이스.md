# [비전] DetectionCandidate 및 정렬 상태 인터페이스

- 상태: 초안
- 최초 작성 시각: 2026-09-08 11:13 KST
- 요청자: 비전팀
- 요청 단위: 비전
- 대상 단위 및 로봇: AMR / robot1·robot6
- 관련 TBD ID: TBD-IF-006, TBD-IF-009
- 기준 문서·절: docs/interfaces.md 1절·9절, 관제 AMR 비전 Detection과 yaw 정렬 계약
- 결정 일자·근거: 2026-09-08, 비전·AMR 연계 협의 및 robot6 DetectionCandidate 단위 시험
- 코드 변경 승인 근거·범위: 미승인

## 변경 이유

비전 detecting node가 OAK-D 영상에서 YOLO로 fire, leak, obstacle 후보를 탐지한 뒤 AMR이 해당 후보를 향해 yaw 정렬할 수 있도록 비전 → AMR 후보 인터페이스가 필요하다.

robot6에서 DetectionCandidate 발행 단위 시험을 수행했으며 candidate_id, event_type, confidence, horizontal_error가 정상 발행되는 것을 확인했다.

또한 AMR 정렬 완료 후 비전이 동일 candidate를 대상으로 1초 최종 검증을 시작하려면 AMR → 비전 정렬 상태 인터페이스가 필요하다.

비전 노드는 cmd_vel, Nav2 goal 또는 직접적인 회전 명령을 발행하지 않으며 실제 yaw 정렬과 정지 확인은 AMR이 담당한다.

## 변경 전 → 변경 후

### 1. DetectionCandidate

변경 전:

- DetectionCandidate의 구체적인 공용 메시지 필드가 미확정 상태였다.
- 비전과 AMR 사이의 수평 정렬 오차 전달 형식이 미확정 상태였다.

변경 후 비전팀 제안:

~~~text
std_msgs/Header header

string robot_id
string candidate_id

uint8 FIRE=0
uint8 LEAK=1
uint8 OBSTACLE=2
uint8 event_type

float32 confidence
float32 horizontal_error
~~~

토픽 제안:

~~~text
/robot6/vision/detection_candidate
~~~

horizontal_error 의미:

~~~text
negative : target is left
0.0      : target is center
positive : target is right
~~~

화면 중심을 기준으로 정규화한 수평 오차를 사용한다.

현재 Candidate 생성 기준:

- YOLO confidence threshold: 0.70
- 0.3초 이내 동일 event type 2회 이상 검출 시 Candidate 생성
- 일시적인 미검출 시 기존 candidate를 최대 0.6초 유지
- candidate_id는 비전에서 생성하며 AMR은 변경하지 않는다.

event_type 정수값과 horizontal_error 계약은 영향 단위 검토 후 공용 계약으로 확정한다.

### 2. AlignmentStatus

변경 전:

- AMR → 비전 정렬 완료·실패·안전 중단 통지의 구체적인 메시지와 토픽이 미확정 상태였다.

변경 후 비전·AMR 협의안:

~~~text
std_msgs/Header header

string robot_id
string candidate_id

uint8 ALIGNING=0
uint8 ALIGNED_COMPLETE=1
uint8 FAILED=2
uint8 SAFETY_ABORTED=3

uint8 state
~~~

토픽 제안:

~~~text
/robot6/vision/alignment_status
~~~

상태 의미:

- `ALIGNING=0`: AMR이 해당 candidate를 대상으로 yaw 정렬 중
- `ALIGNED_COMPLETE=1`: 목표 정렬 및 실제 정지 확인 완료. 비전은 동일 candidate_id에 대해 최종 1초 검증을 시작한다.
- `FAILED=2`: 후보 소실, 정렬 timeout 등 일반적인 정렬 실패
- `SAFETY_ABORTED=3`: E-stop, Drive Token, local safety, 센서·구동계 장애 등 안전 원인으로 정렬 중단

AMR은 DetectionCandidate에서 받은 candidate_id를 변경하지 않고 AlignmentStatus에 그대로 반환한다.

### 3. 후속 DetectionEvent·Evidence

DetectionEvent, DetectionEvidence 및 정렬 완료 후 1초 검증 결과 인터페이스는 이번 변경에서 확정하지 않는다.

DetectionCandidate → AlignmentStatus 연계를 우선 단위 검증한 뒤 후속 변경 요청에서 DetectionEvent와 증적 이미지 전송 계약을 확정한다.

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| AMR | DetectionCandidate 구독 및 horizontal_error 부호·단위 검토 | yaw 정렬 입력 | AMR |
| AMR | AlignmentStatus 필드·토픽 검토 및 정렬 결과 발행 구현 | AMR 정렬 모듈 | AMR |
| 관제 | event_type enum 값 및 TBD-IF-006 영향 검토 | Detection 계약 | 관제 |
| System monitor | 이번 단계 직접 변경 없음. 후속 DetectionEvent/Evidence 계약에서 검토 | 해당 없음 | System monitor |
| 비전 | DetectionCandidate 발행 구현 및 robot6 단위 시험 | detecting_node | 비전 |
| 비전 | AlignmentStatus 수신 후 동일 candidate_id 검증 로직 후속 구현 | detecting_node | 비전 |

## 영향과 적용 순서

1. 비전팀 DetectionCandidate 메시지 및 발행 구현을 기준으로 AMR팀이 필드와 horizontal_error 계약을 검토한다.
2. AMR팀이 AlignmentStatus 메시지와 토픽을 동일 인터페이스 버전으로 반영한다.
3. 비전팀이 AlignmentStatus 구독을 추가한다.
4. DetectionCandidate의 candidate_id와 AlignmentStatus의 candidate_id가 동일하게 유지되는지 확인한다.
5. ALIGNED_COMPLETE 수신 후 1초 최종 검증 로직을 후속 적용한다.
6. 이후 DetectionEvent 및 DetectionEvidence 계약을 별도 확정한다.

공용 patrol_interfaces를 사용하는 비전과 AMR은 동일 버전을 사용해야 한다. 혼합 버전에서는 실제 yaw 정렬 시험을 진행하지 않는다.

인터페이스 불일치 발생 시 실제 회전 연동을 중단하고 DetectionCandidate 단독 시험 상태로 복구한다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | 미반영 | | DetectionCandidate 수신 및 AlignmentStatus 적용 |
| AMR / robot6 | 미반영 | | DetectionCandidate 수신 및 AlignmentStatus 적용 |
| 관제 | 검토 대기 | TBD-IF-006 | event_type 등 공용 계약 검토 |
| System monitor | 변경 불필요 | Candidate·Alignment 내부 연계 단계 | 후속 Event/Evidence 검토 |
| 비전 | 부분 반영 | robot6 DetectionCandidate 단위 시험 성공 | AlignmentStatus 수신 및 1초 검증 추가 |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: IT-14, IT-16
- DetectionCandidate가 robot6에서 정상 발행된다.
- 동일 candidate가 유지되는 동안 candidate_id가 변경되지 않는다.
- horizontal_error가 대상의 좌·우 이동에 따라 음수 → 0 → 양수 방향으로 변화한다.
- AMR이 동일 candidate_id를 사용하여 AlignmentStatus를 반환한다.
- ALIGNED_COMPLETE는 AMR의 정렬 및 실제 정지 확인 이후에만 발행된다.
- FAILED와 SAFETY_ABORTED가 구분된다.
- 비전 노드는 cmd_vel, Nav2 goal 또는 직접 회전 명령을 발행하지 않는다.
- 실제 실행 결과와 증거: robot6에서 DetectionCandidate 발행 및 ros2 topic echo 확인 완료
- 미실행 또는 BLOCKED 항목: AlignmentStatus 연동 및 실제 yaw 정렬 시험은 AMR 반영 전 BLOCKED. DetectionEvent·DetectionEvidence는 후속 계약 대상.

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-08 | 비전 | DetectionCandidate robot6 단위 시험 성공 | 실제 OAK-D + YOLO + ROS topic 시험 |
| 2026-09-08 | 비전 | Candidate 생성 기준을 confidence 0.70, 0.3초 내 동일 event 2회 검출로 적용 | 회전 중 이벤트 검출 실험 |
| 2026-09-08 | 비전·AMR 협의 | AlignmentStatus에 robot_id, candidate_id, state를 사용하고 ALIGNING/ALIGNED_COMPLETE/FAILED/SAFETY_ABORTED 상태를 구분하는 안 제시 | yaw 정렬 연계 협의 |
