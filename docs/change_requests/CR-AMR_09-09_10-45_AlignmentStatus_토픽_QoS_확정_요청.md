# [AMR] AlignmentStatus 토픽·QoS 확정 요청

- 상태: AMR 결정·비전 검토 요청
- 최초 작성 시각: 2026-09-09 10:45 KST
- 요청자: 조정묵
- 요청 단위: AMR
- 대상 단위 및 로봇: 비전 / robot1·robot6
- 관련 TBD ID: TBD-IF-006, TBD-AMR-001
- 기준 문서·절: [공용 인터페이스](../interfaces.md), [비전팀 기존 요청서](CR-비전_09-08_11-13_DetectionCandidate_정렬상태_인터페이스.md)
- 결정 일자·근거: 2026-09-09 사용자 결정. 기존 메시지와 비전팀의 `/robot6/vision/alignment_status` 제안을 두 로봇 공통 namespace 규칙으로 일반화했다.
- 코드 변경 승인 근거·범위: 이번 요청은 계약 정리와 영향 팀 검토 요청이다. 비전 코드 변경 승인이 아니며 AMR 구현·시험 상태는 별도로 추적한다.

## 확정 요청 내용

| 항목 | AMR 결정안 |
|---|---|
| 토픽 | `/{robot}/vision/alignment_status` (`robot`은 `robot1` 또는 `robot6`) |
| 타입 | `patrol_interfaces/msg/AlignmentStatus` |
| 발행자 | 해당 로봇의 AMR 정렬 모듈 단일 발행자 |
| 구독자 | 해당 로봇의 비전 `detecting_node` |
| QoS | `RELIABLE / VOLATILE / KEEP_LAST(10)` |
| 상관관계 | `robot_id`는 namespace와 일치하고 `candidate_id`는 수신한 `DetectionCandidate.candidate_id`를 그대로 사용 |

`AlignmentStatus.msg`의 기존 wire 값은 변경하지 않는다.

- `ALIGNING=0`: 해당 candidate의 yaw 정렬 시작 시 1회 발행
- `ALIGNED_COMPLETE=1`: 정렬과 실제 정지 확인을 모두 마친 뒤 1회 발행
- `FAILED=2`: 후보 소실·정렬 timeout 등 일반 실패 시 1회 발행
- `SAFETY_ABORTED=3`: E-stop, token 상실, local safety 또는 센서·구동 장애로 중단될 때 1회 발행

`ALIGNED_COMPLETE`, `FAILED`, `SAFETY_ABORTED`는 한 candidate의 terminal 상태다. terminal 발행 후 같은 `candidate_id`를 `ALIGNING`으로 되돌리지 않는다. 새 정렬은 새 `candidate_id`로 시작한다. 과거 terminal 상태가 비전 노드 재시작 뒤 새 상태처럼 재전달되지 않도록 `TRANSIENT_LOCAL`은 사용하지 않는다.

## 영향과 요청 작업

| 단위 | 요청 작업 |
|---|---|
| 비전 | 위 토픽·QoS로 구독하고 현재 추적 중인 동일 `candidate_id`의 `ALIGNED_COMPLETE`에서만 1초 최종 검증을 시작한다. 과거·다른 candidate 상태는 폐기한다. |
| AMR | DetectionCandidate에서 받은 ID를 보존하고 위 상태 전이를 발행한다. 최종 `cmd_vel`은 계속 `local_safety_supervisor`만 발행한다. |
| 관제·System monitor | 이 내부 정렬 상태 경로의 직접 생산·소비자가 아니므로 코드 변경 불필요. |

## 완료 조건

- robot1·robot6 각각에서 namespace와 메시지 `robot_id`가 일치한다.
- 동일 candidate에 `ALIGNING` 뒤 terminal 상태가 최대 한 번 발생한다.
- `ALIGNED_COMPLETE`는 odometry 실제 정지 확인 전에는 발행되지 않는다.
- 안전 원인 중단은 `FAILED`가 아니라 `SAFETY_ABORTED`로 구분된다.
- 비전 노드는 yaw 속도, Nav2 goal 또는 최종 `cmd_vel`을 발행하지 않는다.
- 비전팀 회신과 양쪽 코드 반영 후 실제 ROS 통신으로 QoS·ID·상태 전이를 검증한다.

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-09 10:45 | 조정묵·AMR | 토픽, 발행·구독 책임, QoS와 candidate별 terminal 전이를 AMR 요청안으로 확정 | 사용자 결정 및 기존 비전 요청서와 충돌 없음 확인 |
