# [AMR] yaw 정렬 수치와 Nav2 후보 중재 확정

- 상태: AMR 내부 결정·구현 대기
- 최초 작성 시각: 2026-09-09 10:53 KST
- 요청자: 조정묵
- 요청 단위: AMR
- 대상 단위 및 로봇: AMR / robot1·robot6
- 관련 TBD ID: TBD-AMR-001, TBD-IF-006, TBD-IF-009
- 기준 문서·절: [AMR 설계](../amr.md), [공용 인터페이스](../interfaces.md), [DetectionCandidate 요청안](CR-AMR_09-09_10-49_DetectionCandidate_토픽_QoS_확정_요청.md), [AlignmentStatus 요청안](CR-AMR_09-09_10-45_AlignmentStatus_토픽_QoS_확정_요청.md)
- 결정 일자·근거: 2026-09-09 사용자 권장안 승인. 불명확한 후보 동시 입력은 fail-safe 정지하고 실제 정지 확인 뒤에만 정렬 완료를 알린다.
- 코드 변경 승인 근거·범위: 이 문서는 AMR 내부 계약 확정이다. 조정묵 안전 중재와 박성현 mission 정렬 생산부의 실제 코드 반영·시험 상태는 구분해 추적한다.

## 확정 조건

| 항목 | 결정값 |
|---|---|
| Candidate 수락 confidence | `0.70 이상` |
| 정렬 완료 오차 | `abs(horizontal_error) <= 0.05` |
| 오차 유지시간 | `0.5초 연속` |
| yaw 각속도 | 절댓값 최소 `0.08 rad/s`, 최대 `0.25 rad/s` |
| yaw timeout | 정렬 시작 후 `10초` |
| Candidate 단절 | 마지막 유효 후보 이후 `0.6초` 초과 시 `FAILED` |
| 후보 신선도 | 기존 Q-17에 따라 각 TwistStamped age `0.5초 이하` |

## 실행·중재 순서

1. AMR mission 정렬부가 유효한 DetectionCandidate를 선택하고 `ALIGNING`을 발행한다.
2. 활성 Nav2 goal을 취소하고 odometry 실제 정지를 확인한다.
3. 정지 확인 전에는 yaw 후보를 내지 않는다.
4. yaw 후보는 `linear.x=0`이며 `angular.z`만 사용한다. 회전 방향은 horizontal error의 부호 계약에 맞춘다.
5. local safety는 `cmd_vel_safe`와 `cmd_vel_yaw` 중 하나만 신선할 때 그 후보를 기존 token·heartbeat·E-stop 게이트에 넣는다.
6. 두 후보가 동시에 신선하면 선택을 추측하지 않고 최종 `cmd_vel`을 0으로 만든다.
7. 안전 조건이 깨지면 즉시 0을 출력하고 `SAFETY_ABORTED`로 종료한다.
8. 오차 조건을 0.5초 연속 충족하면 yaw 출력을 0으로 만들고 odometry 실제 정지를 다시 확인한 뒤 `ALIGNED_COMPLETE`를 발행한다.
9. Candidate가 0.6초 넘게 끊기거나 10초 timeout이면 `FAILED`를 발행한다.
10. terminal 상태 뒤 Nav2를 자동 재개하지 않는다. mission 상태와 새 실행 조건을 다시 확인한다.

## 책임 경계

| 책임 | 담당 |
|---|---|
| Candidate 선택, Nav2 goal 취소, yaw 후보 생산, AlignmentStatus 생산 | 박성현 mission 정렬부 |
| 두 속도 후보 신선도·동시성 판정, 안전 게이트, 유일한 최종 `cmd_vel` | 조정묵 local safety |
| DetectionCandidate 생산과 AlignmentStatus 소비 | 비전 detecting node |

## 완료 조건

- Nav2 취소와 실제 정지 확인 전 yaw 회전이 시작되지 않는다.
- 두 후보 동시 입력, stale 후보, 안전 권한 상실에서 최종 출력은 0이다.
- 정렬 완료는 오차 유지와 회전 정지 확인 뒤에만 한 번 발행된다.
- timeout·후보 단절은 FAILED, 안전 차단은 SAFETY_ABORTED로 구분된다.
- robot1·robot6에서 로컬 ROS 시험 후 실제 OAK-D·odom·Nav2 저속 시험을 별도로 수행한다.

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-09 10:53 | 조정묵·AMR | confidence·오차·속도·timeout·단절과 fail-safe 후보 중재를 권장안대로 확정 | 사용자 승인 |
