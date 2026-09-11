# [AMR] 실제 정지에 근거한 safety_state 판정

- 상태: AMR 로컬 구현·자동시험 완료 / 수신 단위 검토 요청 초안
- 최초 작성 시각: 2026-09-08 23:02 KST
- 요청자·요청 단위: AMR
- 대상 단위 및 로봇: AMR robot1·robot6, 관제, System monitor
- 관련 TBD ID: 신규 공용 계약 없음. 로컬 판단 주체는 [flowchart 3.2절](../amr_patrol_safety_flowchart.md#32-local_safety_supervisorpy)의 미정 사항을 이번 결정으로 해소한다.
- 기준: [interfaces.md 3·4절](../interfaces.md), [관제 v1.0](../decisions/2026-09-08-control-interface-baseline.md)
- 결정 일자·근거: 2026-09-08 사용자 답변 `local_safety_supervisor가 odom으로 판단`
- 코드 변경 승인: 사용자 요청의 `patrol_amr_safety` 코드 완성 범위 및 위 판단 주체 결정. 타 담당 코드 수정은 포함하지 않는다.

## 변경 이유와 반영 내용

기존 local_safety_supervisor는 E-stop이 비활성이고 주행 권한이 없으면 실제 측정 없이 SAFETY_STOPPED를 발행했다. 이는 출력 차단과 실제 정지 확인을 구분하는 기존 공용 계약과 다르다.

**결정:** local_safety_supervisor가 odom을 직접 구독하고 safety_state의 단일 발행자로 유지된다. E-stop 활성은 ESTOPPED, 후보 출력 통과는 NORMAL, 출력 차단 시 실제 정지 확인 전은 STOPPING, 확인 후만 STOPPED다. 정지 확인 이후 odom이 오래되거나 다시 움직이면 STOPPING으로 돌아간다. motion_allowed는 기존 heartbeat·token·E-stop 주행 권한 판단을 유지한다.

측정 기준은 RobotStatusState의 기존 공통 구현을 재사용한다. 새 enum·토픽·QoS·시간 정책을 만들지 않는다. status_reporter는 safety_state를 수신해 그대로 보고하고, 별도 motion_stopped 필드는 같은 공통 측정 기준으로 계산한다. 두 노드의 수신 시점은 다를 수 있으므로 두 필드가 모든 메시지에서 동시에 전이한다고 가정하지 않는다.

## 요청 작업과 단위별 상태

| 단위 | 작업·근거 | 현재 상태 |
|---|---|---|
| AMR robot1·robot6 | safety supervisor odom 구독·공통 정지 판정·launch remap·자동시험 | 구현·두 namespace 로컬 ROS 통과, 실물 미실행 |
| 관제 | 기존 STOPPING/STOPPED 구분과 별도 motion_stopped 확인 유지 여부 검토 | 검토 요청 초안, 실제 전달·회신 없음 |
| System monitor | 수신 safety_state 표시 유지 여부 검토. 별도 정지 판단 추가 불필요 | 검토 요청 초안, 실제 전달·회신 없음 |
| 비전 | 메시지·입출력 변경 없음 | 변경 불필요 |

관제·System monitor의 코드 변경은 **기존 계약을 준수한다면 불필요**하다. enum 값·wire 필드·토픽·QoS가 그대로이기 때문이다. 실제 수신 코드 대조·상대 확인 없이 변경 불필요 합의 완료라고 처리하지 않는다.

## 영향·적용·검증

AMR만 먼저 적용할 수 있으며, 구형 AMR은 실제 정지를 확인하지 않은 STOPPED를 계속 발행할 수 있다. 관제는 기존 별도 실제 정지 조건 확인을 생략하면 안 된다. 센서 미수신은 STOPPING으로 유지되며 자동 주행 재개 조건은 변경하지 않는다. 기존 Onboard/Offboard Discovery 설정은 유지한다.

- 단위시험: odom 미수신, 속도 경계, 연속 유지, stale·재수신, 재이동, E-stop 우선, 후보 stale와 권한 분리.
- ROS 시험: robot1·robot6에서 odom→safety_state→RobotStatus와 기존 최종 속도 차단 회귀.
- 관련 통합시험: integration.md IT-03·IT-10. 실제 관제·로봇 통합 결과와 구분한다.
- 실제 실행 결과: 전체 단위시험 360개 통과, robot1·robot6 격리 ROS에서 미측정 STOPPED 없음·정지 유지 후 STOPPED·stale 후 STOPPING 확인. 상세 로그는 flowchart 7.0절 후속 체크포인트 참조. 로봇 시험은 2026-09-09 오전 사용자 확인 예정·미실행.

## 검토·결정 이력

| 일자 | 단위 | 내용 | 근거 |
|---|---|---|---|
| 2026-09-08 | AMR 사용자 | 판단 주체를 local_safety_supervisor로 확정 | 현재 대화의 명시적 선택 답변 |
