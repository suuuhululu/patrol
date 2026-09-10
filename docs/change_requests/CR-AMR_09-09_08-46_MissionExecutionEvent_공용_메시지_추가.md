# [AMR] MissionExecutionEvent 공용 메시지 추가

- 상태: 반영 중
- 최초 작성 시각: 2026-09-09 08:46 KST
- 요청자: 조정묵 작업 범위 사용자 승인
- 요청 단위: AMR
- 대상 단위 및 로봇: AMR / robot1·robot6
- 관련 TBD ID: TBD-AMR-005, TBD-IF-003
- 기준 문서·절: `docs/amr_patrol_safety_flowchart.md` 1.1·3.4·4.1절, 2026-09-09 `AMR 공동 구현 계약 v1`
- 결정 일자·근거: 2026-09-09, command gateway의 ACCEPTED 시점을 mission admission 이후로 고정
- 코드 변경 승인 근거·범위: 2026-09-09 사용자 지시 “내 작업 범위라면 승인”; 조정묵 gateway 구현에 필요한 `MissionExecutionEvent` 추가 포함

## 변경 이유

현행 `mission_lifecycle/std_msgs/String`은 실행 시작과 최종 완료만 표현한다. gateway가 mission의 실제 수용 여부를 알기 전에 ACCEPTED를 발행하는 문제를 막고, PAUSED 같은 비종료 저장 완료와 최종 outbox 저장 완료를 구분하려면 구조화된 내부 이벤트가 필요하다.

## 변경 전 → 변경 후

- 변경 전: `/{robot}/mission_lifecycle`, `std_msgs/String`, `executing/completed` JSON
- 변경 후: `/{robot}/mission_execution_event`, `patrol_interfaces/MissionExecutionEvent`, ADMITTED·REJECTED·STARTED·NONTERMINAL_STORED·RESULT_STORED
- QoS: RELIABLE / TRANSIENT_LOCAL / KEEP_LAST(20)
- 멱등성 키: `command_id + event_type + report_id`
- 외부 `CommandCheck` 발행자는 계속 command gateway 하나다.

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| AMR | 메시지 정의·gateway 구독/검증·상태 저장·시험 | `patrol_interfaces`, `patrol_amr_safety`, gateway SQLite | 조정묵 |
| AMR | admission·worker·저장 완료 이벤트 생산 | `patrol_amr` mission 실행부 | 박성현 |
| 관제 | 변경 불필요. 외부 `CommandCheck` 계약 유지 확인 | 명령 수신 상태기계 | 관제 |
| System monitor | 변경 불필요. AMR 내부 이벤트를 직접 구독하지 않음 | 해당 없음 | System monitor |
| 비전 | 변경 불필요 | 해당 없음 | 비전 |

## 영향과 적용 순서

메시지와 gateway 소비부를 먼저 반영한 뒤 mission 생산부를 병합한다. 혼합 버전에서는 gateway가 새 admission 이벤트를 받지 못하므로 명령을 실행하지 않고 4초 뒤 `REJECTED / INVALID_STATE / MISSION_DISPATCH_TIMEOUT`으로 종료해야 한다. 과거 retained dispatch가 재수신돼도 mission 실행 ledger가 실제 Action 중복을 막아야 한다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | gateway 반영·mission 미연결 | 공용 메시지·gateway 소비부·ROS probe | mission event 생산부와 TRANSIENT_LOCAL 구독 통합 |
| AMR / robot6 | gateway 반영·mission 미연결 | 공용 메시지·gateway 소비부 | mission event 생산부와 TRANSIENT_LOCAL 구독 통합 |
| 관제 | 변경 불필요 검토 요청 | 외부 CommandCheck 타입 불변 | 실제 수신 회귀 |
| System monitor | 변경 불필요 검토 요청 | 내부 토픽 비구독 | IngestionAck는 별도 TBD-IF-003 |
| 비전 | 변경 불필요 | AMR 내부 경계 | 없음 |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: IT-03, IT-04, IT-13
- 추가 시험·기대 결과: admission 전 ACCEPTED 없음, 4초 timeout, 이벤트 순서 역전 복구, 중복 이벤트 1회 적용, gateway/mission 개별 재시작, robot1·robot6 namespace 분리
- 실제 실행 결과와 증거: 구현 후 기록
- 미실행 또는 BLOCKED 항목: 박성현 mission 이벤트 생산부, 실제 로봇·관제 통합

2026-09-09 pull 후 확인: `mission_supervisor.py`는 기존 `command_lifecycle` 호출이 남았지만 import가 없어 실행 시 실패하며, `mission_dispatch` 구독이 VOLATILE이다. 성현님 코드 수정 범위에서 D17 producer 교체와 QoS 변경이 함께 필요하다.

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-09 | 사용자·AMR | 조정묵 작업 범위에 필요한 공용 메시지 구현 승인 | 현재 대화의 명시적 승인 |
