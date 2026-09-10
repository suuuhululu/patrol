# [관제] patrol_interfaces v2 전환

- 상태: 반영 중
- 최초 작성 시각: 2026-09-10 15:26 KST
- 요청자: 사용자
- 요청 단위: 관제
- 대상 단위 및 로봇: AMR(robot1·robot6), 관제, System monitor, 비전
- 관련 TBD ID: 해당 없음
- 기준 문서·절: [공용 인터페이스](../interfaces.md)
- 결정 일자·근거: 2026-09-10 사용자 확정
- 코드 변경 승인 근거·범위: 2026-09-10 사용자 요청으로 `src/patrol_interfaces` 전면 변경 승인

## 변경 이유

기본 순찰 시나리오에 필요한 인터페이스만 유지하고 순찰 명령·상태·방문·결과를 하나의 Action으로 통합한다. 로봇별 주행 권한, AMR 내부 감지 Action, 시스템 모니터 감지 보고 Service를 새 기준으로 사용한다.

## 변경 전 → 변경 후

- 외부 순찰 명령·상태·방문·결과는 `/{robot}/patrol_action`의 Goal·Feedback·Result로 통합한다.
- 안전구역 이동과 재개는 `/{robot}/patrol_command`로 전달한다.
- 주행 권한은 단순화한 `/{robot}/drive_token`으로 전달한다.
- AMR 내부 감지·정렬은 `/{robot}/detect_event` Action으로 처리한다.
- 확정 사건과 사진은 `/system_monitor/report_detection` Service로 저장한다.
- CCTV `CameraState`와 `patrol_allowed`는 유지한다.
- `/control/estop` 타입은 예약하지만 현재 동작을 구현하지 않는다.
- `patrol_interfaces` 버전은 호환 불가 변경을 반영해 `2.0.0`으로 올린다.

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| AMR | Patrol Action Server, PatrolCommand·DriveToken 소비, DetectEvent Action과 ReportDetection Client 반영 | `patrol_amr`, `patrol_amr_safety`, AMR 감지 노드 | AMR |
| 관제 | Patrol Action Client, PatrolCommand·DriveToken 발행, Action Feedback·Result 처리 | `src/patrol_control` | 관제 |
| System monitor | ReportDetection Service 유지, 제거 타입 import·구독·저장 경로 정리 | `src/patrol_sysmon` | System monitor |
| 비전 | CameraState wire schema 호환 확인. PC 4 CCTV에는 그 외 변경 없음 | `src/patrol_vision` CCTV 노드 | 비전 |

## 영향과 적용 순서

`2.0.0`은 이전 wire schema와 호환되지 않는다. 공용 패키지를 먼저 배포한 상태에서 기존 소비 노드를 실행하면 import 또는 타입 지원 오류가 발생한다. 각 단위의 소비 코드를 같은 Git commit 기준으로 갱신하고 빌드한 뒤 통합 실행한다. 소비 코드 전환 전에는 실제 주행시험을 하지 않는다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | 미반영 | - | v2 Action·메시지 소비 코드 전환 |
| AMR / robot6 | 미반영 | - | v2 Action·메시지 소비 코드 전환 |
| 관제 | 반영 | `patrol_interfaces 2.0.0`, `patrol_control 0.2.0`; 빌드·단위시험·노드 생성 smoke test PASS | 실제 AMR·CCTV 종단시험 |
| System monitor | 일부 반영 | ReportDetection 서버 기존 구현 | 제거 타입 의존성 정리·재빌드 |
| 비전 | 검토 필요 | CameraState 유지 | v2 패키지 재빌드·CCTV 호환 확인 |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: 새 인터페이스 기준으로 추후 갱신
- 추가 시험·기대 결과: 공용 패키지 빌드, Action·메시지·Service 타입 조회, 각 단위 종단 통신
- 실제 실행 결과와 증거: 2026-09-10 임시 build/install/log 경로에서 `colcon build --packages-select patrol_interfaces` 성공. `colcon test`의 copyright·lint_cmake·xmllint 3개 통과. 소스·설치 타입 검증 PASS, v2 manifest SHA-256 `4237fb14a28817517384d9a189b16f3e13b226675f91cc3d79ee37a761020805`.
- 미실행 또는 BLOCKED 항목: 소비 노드 전환 및 실제 장비 통합시험

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-10 | 사용자·관제 | 기본 인터페이스 트리와 `ReportDetection.srv`를 기준으로 공용 패키지 전면 전환 승인 | 사용자 대화 |
