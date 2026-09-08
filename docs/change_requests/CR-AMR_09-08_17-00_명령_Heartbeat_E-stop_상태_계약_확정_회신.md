# [AMR] 명령·Heartbeat·E-stop·상태 계약 확정 회신

- 상태: 반영 중
- 최초 작성 시각: 2026-09-08 17:00 KST
- 요청자: AMR 팀
- 요청 단위: AMR
- 대상 단위 및 로봇: AMR robot1·robot6, 관제, System monitor
- 관련 TBD ID: TBD-IF-001·003·004·011, TBD-AMR-005·006
- 기준 문서·절: [interfaces.md 2~5·9~10절](../interfaces.md), [관제 요청서](CR-관제_09-08_15-15_AMR_명령_Heartbeat_E-stop_상태_계약.md)
- 결정 일자·근거: 2026-09-08 사용자가 6개 검토 항목을 순차적으로 확정
- 코드 변경 승인 근거·범위: 2026-09-08 17:00 KST 사용자 승인. `patrol_interfaces`, `patrol_amr`, `patrol_amr_safety`, 관련 테스트·문서

## 변경 이유

관제 요청서의 미정 항목을 AMR 측에서 확정하고 현재 코드와 공용 wire 계약을 동일한 기준으로 맞춘다. 기존 command ID 기록은 보존하면서 제거된 필드 의존성을 없애고, heartbeat·E-stop 이상 시 로봇이 자동 재출발하지 않도록 한다.

## 변경 전 → 변경 후

| 항목 | 변경 전 | 확정 내용 |
|---|---|---|
| `target_pose` | MOVE_TO_SAFE_ZONE 실행 좌표로 사용 | wire 필드는 유지하되 모든 명령에서 기본값만 허용, 비어 있지 않으면 `INVALID_PARAMETERS(205)` |
| ACCEPTED 누락 | 재전송 중단 미정 | ID 3종이 일치하는 EXECUTING을 실행 시작 증거로 수락하고 관제 재전송 중단 |
| `parameters_json` | msg·parser·fingerprint·DB에 존재 | 공용 msg와 AMR 코드에서 삭제. 기존 DB 행은 보존하고 legacy 컬럼만 transaction migration으로 제거 |
| patrol plan | 고정 waypoint에 plan ID 없음 | robot1=`robot1_default`, robot6=`robot6_default` |
| MOVE_TO_SAFE_ZONE | 관제 전달 pose 사용 | AMR safe-zone selector가 실측 후보를 선택. 후보가 없으면 `SAFE_ZONE_NOT_FOUND(400)` |
| E-stop 원인 | AMR local latch·manual reset | 관제가 활성 원인·우선순위를 관리해 대표 reason 하나를 발행. AMR은 `robot1/robot6/all`을 소비하고 latch/reset을 사용하지 않음 |
| Heartbeat·token | 실행 경로 미연결 | 1초 timeout으로 로컬 안전 정지, 새 control session이면 이전 token 폐기, 복구만으로 자동 재개 금지 |

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| AMR | 명령 필수값, plan ID, STOP/CANCEL, safe-zone selector 반영 | `patrol_amr` mission·navigation | AMR |
| AMR | heartbeat timeout·session token 폐기, E-stop `all`·대표 reason 소비 | `patrol_amr_safety` | AMR |
| AMR | CommandCheck·reason code·command store migration 반영 | command gateway·store·report | AMR |
| 관제 | 일치하는 EXECUTING 수신 후 재전송 중단, robot별 plan ID 송신 | MissionCommand·CommandCheck 송수신 | 관제 |
| System monitor | 신규 enum·EStop 타입 소비 호환성 확인 | ROS registry·payload mapper | System monitor |
| 비전 | 변경 불필요 | 직접 송수신자가 아님 | 비전 |

## 영향과 적용 순서

1. 공용 msg enum·필드와 AMR parser·fingerprint를 같은 commit에서 반영한다.
2. 기존 SQLite command store를 transaction으로 migration하고 command ID 기록·완료 report를 보존한다.
3. mission·safety 소비 로직과 robot1·robot6 설정을 반영한다.
4. 단위시험·빌드 후 공용 msg 송신자와 소비자를 같은 버전으로 배포한다.

`MissionCommand`/`ControlHeartbeat`/`EStop`은 wire 레이아웃이 바뀐다. 혼합 버전을 운영하지 않는다. 롤백할 때도 공용 msg와 소비 코드를 함께 되돌린다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | 반영 중 | 본 요청서와 코드 변경 | 단위·통합 검증 |
| AMR / robot6 | 반영 중 | 본 요청서와 코드 변경 | 단위·통합 검증 |
| 관제 | 검토 요청 | 관제 원 요청서에 대한 AMR 회신 | 송신·재전송 로직 반영 |
| System monitor | 검토 요청 | 공용 타입 영향 | EStop 타입 통일 |
| 비전 | 변경 불필요 | 직접 영향 없음 | 없음 |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: IT-02, IT-03, IT-04, IT-10, IT-11, IT-12
- 추가 시험·기대 결과: 명령 조합·DB migration·Heartbeat 1초 timeout·session 교체·E-stop `all`·reason enum·STOP/CANCEL 경계를 단위시험한다.
- 실제 실행 결과와 증거: commit 전 자동시험·colcon build 결과를 갱신한다.
- 미실행 또는 BLOCKED 항목: 실물 robot1·robot6 주행과 관제·System monitor 통합 시험은 배포 환경에서 수행한다.

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-08 | 사용자·AMR | `target_pose` 유지·빈 값 강제, EXECUTING 후 재전송 중단 | 순차 질문 1·2 확정 |
| 2026-09-08 | 사용자·AMR | `parameters_json` 삭제·DB migration | 순차 질문 3 확정 |
| 2026-09-08 | 사용자·AMR | robot별 default plan ID | 순차 질문 4 확정 |
| 2026-09-08 | 사용자·AMR | safe-zone 동적 selector, 무후보 400 | 순차 질문 5 확정 |
| 2026-09-08 | 사용자·AMR | 관제 대표 E-stop reason, AMR 소비 전용 | 순차 질문 6 확정 |
