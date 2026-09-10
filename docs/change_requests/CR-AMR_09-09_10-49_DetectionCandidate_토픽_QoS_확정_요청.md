# [AMR] DetectionCandidate 토픽·QoS 확정 요청

- 상태: AMR 결정·비전 검토 요청
- 최초 작성 시각: 2026-09-09 10:49 KST
- 요청자: 조정묵
- 요청 단위: AMR
- 대상 단위 및 로봇: 비전 / robot1·robot6
- 관련 TBD ID: TBD-IF-006, TBD-AMR-001
- 기준 문서·절: [공용 인터페이스](../interfaces.md), [비전팀 기존 요청서](CR-비전_09-08_11-13_DetectionCandidate_정렬상태_인터페이스.md), [AlignmentStatus 요청안](CR-AMR_09-09_10-45_AlignmentStatus_토픽_QoS_확정_요청.md)
- 결정 일자·근거: 2026-09-09 사용자 결정. 기존 비전팀의 `/robot6/vision/detection_candidate` 제안을 두 로봇 공통 namespace 규칙으로 일반화했다.
- 코드 변경 승인 근거·범위: 이번 요청은 계약 정리와 영향 팀 검토 요청이다. 비전 코드 변경 승인이 아니며 AMR 구현·시험 상태는 별도로 추적한다.

## 확정 요청 내용

| 항목 | AMR 결정안 |
|---|---|
| 토픽 | `/{robot}/vision/detection_candidate` (`robot`은 `robot1` 또는 `robot6`) |
| 타입 | `patrol_interfaces/msg/DetectionCandidate` |
| 발행자 | 해당 로봇의 비전 `detecting_node` 단일 발행자 |
| 구독자 | 해당 로봇의 AMR 정렬 모듈 |
| QoS | `RELIABLE / VOLATILE / KEEP_LAST(10)` |
| 상관관계 | `robot_id`는 namespace와 일치하고 `candidate_id`는 비전이 생성해 한 후보의 수명 동안 유지 |

`DetectionCandidate.msg`의 기존 wire 값과 부호는 변경하지 않는다.

- `event_type`: 기존 `FIRE=0`, `LEAK=1`, `OBSTACLE=2`를 사용한다.
- `horizontal_error`: 음수는 대상이 화면 중심의 왼쪽, 0은 중앙, 양수는 오른쪽이다.
- AMR은 `candidate_id`를 파싱하거나 변경하지 않고 `AlignmentStatus.candidate_id`에 그대로 반환한다.
- terminal `AlignmentStatus`가 발생한 후보 ID는 새 후보에 재사용하지 않는다.
- 과거 후보가 비전 또는 AMR 재시작 뒤 새 후보처럼 전달되지 않도록 `TRANSIENT_LOCAL`은 사용하지 않는다.

confidence 기준, 정렬 허용 오차, 후보 단절 유지시간, yaw 속도·timeout과 Nav2/yaw 중재는 이 요청에서 확정하지 않고 TBD-AMR-001의 다음 결정으로 남긴다.

## 영향과 요청 작업

| 단위 | 요청 작업 |
|---|---|
| 비전 | 위 토픽·QoS로 발행하고 후보 추적 중에는 같은 `candidate_id`를 유지하며 종료 뒤 ID를 재사용하지 않는다. |
| AMR | namespace·robot ID와 입력값을 검증하고 같은 candidate ID로 정렬 상태를 반환한다. |
| 관제·System monitor | 이 내부 후보 경로의 직접 생산·소비자가 아니므로 코드 변경 불필요. |

## 완료 조건

- robot1·robot6 각각에서 namespace와 메시지 `robot_id`가 일치한다.
- 비전 노드 하나만 해당 로봇의 후보 토픽을 발행한다.
- 같은 후보를 추적하는 동안 candidate ID가 바뀌지 않는다.
- AMR이 동일 candidate ID를 AlignmentStatus에 반환한다.
- 비전팀 회신과 양쪽 코드 반영 후 실제 ROS 통신으로 QoS·ID·부호를 검증한다.

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-09 10:49 | 조정묵·AMR | 토픽, 발행·구독 책임, QoS, ID 수명과 horizontal error 부호를 AMR 요청안으로 확정 | 사용자 결정 및 기존 비전 요청서와 충돌 없음 확인 |
