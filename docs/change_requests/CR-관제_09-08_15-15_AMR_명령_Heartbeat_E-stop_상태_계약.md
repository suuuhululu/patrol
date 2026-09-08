# [관제] AMR 명령·Heartbeat·E-stop·상태 계약 반영 요청

- 상태: 초안
- 최초 작성 시각: 2026-09-08 15:15 KST
- 요청자: 관제 팀
- 요청 단위: 관제
- 대상 단위 및 로봇: AMR / robot1·robot6
- 관련 TBD ID: TBD-IF-001·002·003·004·011, TBD-AMR-005·006, TBD-CTRL-001·002·004
- 기준 문서·절: [interfaces.md 2~5·9~10절](../interfaces.md), [control_server.md 2·3·6~8절](../control_server.md), [integration.md IT-02·03·04·10·11·12](../integration.md)
- 결정 일자·근거: 2026-09-08 사용자 확정. 공용 메시지와 현재 AMR 구현의 계약 차이를 AMR 팀과 함께 반영·검증하기 위함
- 코드 변경 승인 근거·범위: 미승인. 이 요청서는 AMR 및 공용 `.msg` 변경 권한을 부여하지 않음

## 변경 이유

관제 1단계 구현 전에 CommandCheck 상태 전이, 명령별 target, Heartbeat, E-stop, RobotStatus 안전 상태의 wire 계약을 고정해야 한다. 현재 `patrol_interfaces`와 AMR 코드는 이전 TBD 기준으로 이미 일부 구현되어 있어 최신 공용 계약과 다음 차이가 있다.

- `MissionCommand.msg`와 AMR command fingerprint·parser가 `parameters_json`을 사용한다.
- `CommandCheck.msg`에 check_state 상수가 없고 전이 복구 규칙이 계약화되지 않았다.
- `ControlHeartbeat.msg`가 `message_id/source_id/boot_id/uint32 sequence`를 사용한다.
- `EStop.msg`와 AMR `estop_guard`가 물리 E-stop latch·수동 reset을 전제로 한다.
- `RobotStatus.msg`에 safety_state 상수가 없고 AMR 상태 생산 규칙이 확정 enum과 연결되지 않았다.
- `PatrolReport.msg`에 reason code 203~206이 없다.

이 문서는 기존 AMR 요청서를 덮어쓰지 않는다. [기존 명령 중재 요청](CR-AMR_09-07_18-58_명령_중재_세부_계약_검토.md), [DriveToken 요청](CR-AMR_09-07_15-12_DriveToken_sequence_epoch와_holder_교체.md), [PatrolReport ACK 요청](CR-AMR_09-08_10-42_PatrolReport_ACK와_큐_삭제_조건_검토.md)은 해당 범위의 이력으로 유지한다.

## 변경 전 → 변경 후

| 항목 | 현재 구현·이전 계약 | 2026-09-08 공용 계약 | 구분 |
|---|---|---|---|
| CommandCheck | 의미 상태만 있고 정수 상수·전이 예외 미정 | UNKNOWN=0, ACCEPTED=1, EXECUTING=2, REJECTED=3; 미정의 숫자 폐기; 역방향 전이 폐기 | 결정 |
| ACCEPTED 누락 | 명시 계약 없음 | 관제 내부 `WAITING → EXECUTING`; 동일 command_id·mission_id·robot_id의 EXECUTING만 복구 수락, `ACCEPTED_MISSING` 관제 경고 | 결정. 이후 재전송 중단은 AMR 검토 |
| 최종 결과 | 중간 Check를 전제로 해석 가능 | 중간 Check 일부 누락 시에도 유효 ID의 PatrolReport 수락, 경고만 기록 | 결정 |
| reason code | 0, 100~202, 300 이상 | 203 COMMAND_ID_CONFLICT, 204 INVALID_MISSION, 205 INVALID_PARAMETERS, 206 INVALID_STATE 추가 | 결정 |
| timeout 분류 | reason code와 혼동 가능 | `COMMAND_CHECK_TIMEOUT`은 관제 운영 이벤트이며 AMR reason code가 아님 | 결정 |
| MissionCommand 확장 | `parameters_json` 필드·JSON 검증 사용 | `parameters_json` 제거 | 결정 |
| target_pose | `.msg`와 fingerprint에 포함 | 현재 합의된 모든 command에서 미사용 | 결정. 필드 제거는 검토 요청 |
| Heartbeat | message_id, source_id, boot_id, uint32 sequence | `header`, `control_session_id`, `uint64 sequence`; 5 Hz, timeout 1초, BEST_EFFORT/VOLATILE/KEEP_LAST(3) | 결정 |
| E-stop | 물리 reason·latched·수동 reset 구현 | 물리/하드웨어 경로와 latch/manual reset 제거; UI 정지는 OPERATOR | 결정 |
| E-stop 원인 | enum 수치 미정 | UNKNOWN=0, OPERATOR=1, COMMUNICATION=2, TOKEN=3, OBSTACLE=4, KEEPOUT_FAILURE=5, SYSTEM_FAULT=6 | 결정 |
| E-stop 대상·발행 | 전체 대상 미정 | `robot1`, `robot6`, `all`; AMR에는 최고 우선순위 대표 원인 하나만 발행 | 결정. 우선순위는 검토 요청 |
| E-stop 해제 | 물리는 manual reset, 비물리 3초 | 모든 활성 원인이 사라진 상태 3초 연속 후 관제 해제 가능 | 결정 |
| safety_state | 수치 TBD | UNKNOWN=0, NORMAL=1, STOPPING=2, STOPPED=3, ESTOPPED=4, ERROR=5 | 결정 |
| 관제 종료 | 별도 계약 없음 | 정상 Ctrl+C/SIGINT=`CONTROL_SHUTDOWN`; best-effort token 회수 후 heartbeat/token 중단; 안전 보장은 AMR timeout | 결정 |

### 명령별 mission·target

| command | mission_id | target_id | target_pose | AMR 처리 |
|---|---|---|---|---|
| STOP | 활성 mission이 있으면 사용, 없으면 빈 값 허용 | 빈 값 | 미사용 | 활성 mission이 없어도 no-op ACCEPTED, 재개 상태 보존 |
| START_PATROL | 새 ID 필수 | `patrol_plan_id` 필수 | 미사용 | plan ID로 순찰 계획 시작 |
| MOVE_TO_SAFE_ZONE | 기존 활성 ID 필수 | 빈 값 | 미사용 | AMR이 map·안전영역에서 가장 가까운 유효 좌표를 동적 계산 |
| RESUME_PATROL | 기존 ID 필수 | 빈 값 | 미사용 | CANCEL된 mission 재개 금지 |
| DOCK | 기존 또는 신규 ID 필수 | robot1=`dock_1`, robot6=`dock_6` | 미사용 | target_id만 사용 |
| CANCEL | 활성 mission ID 필수 | 빈 값 | 미사용 | mission 전체 취소·재개 상태 제거; 없거나 종료됨=`REJECTED/INVALID_MISSION` |

START_PATROL의 plan ID 명명·저장·waypoint 구성은 TBD-AMR-005다. MOVE_TO_SAFE_ZONE의 계산 결과·도착 보고 계약도 AMR 제시가 필요하다.

### E-stop reason 의미와 우선순위 검토

| reason | 의미 |
|---|---|
| UNKNOWN | 원인을 신뢰할 수 없거나 분류하지 못한 상태 |
| OPERATOR | System monitor UI가 관제 API로 요청한 운영자 정지 |
| COMMUNICATION | 관제·AMR 안전 통신 상실 또는 timeout |
| TOKEN | Drive Token 누락·만료·회수 |
| OBSTACLE | AMR 로컬 장애물 안전 차단 |
| KEEPOUT_FAILURE | Keepout 적용·확인·rollback 실패 |
| SYSTEM_FAULT | 센서·구동·안전 감독 시스템 고장 |

관제는 활성 원인 집합을 내부에 유지하고 `uint8[] active_reasons` 의미의 디버깅·표시 계약으로 별도 제공하며, EStop wire 메시지에는 대표 원인 하나만 싣는다. AMR 팀은 안전 심각도, 로컬 원인 생산자, 동시에 활성화될 때의 우선순위, 각 원인의 clear 확인 조건을 제시해 달라. 합의 전에는 관제가 임의 우선순위를 구현하지 않는다.

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| AMR | 명령별 필수값·mission 상태 검증, STOP no-op, CANCEL 종료 의미 반영 | `src/patrol_amr/patrol_amr/mission_command_parser.py`, mission supervisor·명령 중재 | AMR |
| AMR | `parameters_json` 의존 제거와 command fingerprint migration 방안 제시 | `command_store.py`, `mission_types.py`, 기존 영속 command store | AMR |
| AMR | CommandCheck enum·전이·중복 응답·reason 203~206 반영 | command parser/store, CommandCheck publisher | AMR |
| AMR | ACCEPTED 누락 EXECUTING 수신 후 관제 재전송 중단 가능 여부 회신 | CommandCheck 재발행·중복 처리 계약 | AMR |
| AMR | START_PATROL plan ID 규칙과 MOVE_TO_SAFE_ZONE 좌표 계산·결과 보고안 제시 | TBD-AMR-005, navigation/mission supervisor | AMR |
| AMR | ControlHeartbeat 새 session 수락·이전 token 폐기·1초 timeout 반영 | local safety/heartbeat guard | AMR |
| AMR | 물리 E-stop latch·manual reset 제거, 새 reason·`all` 처리, 대표 원인 소비 반영 | `estop_guard.py`, `local_safety_supervisor.py`, readiness | AMR |
| AMR | safety_state 0~5 생산 규칙과 reason_code 분리 반영 | RobotStatus publisher, local safety | AMR |
| AMR | 정상·비정상 관제 종료와 재기동 시 이전 권한 폐기·무자동재개 확인 | token/heartbeat/mission gate | AMR |
| 관제 | 송신·검증·상태 전이·운영 이벤트 구현 | 관제 노드(별도 승인 후) | 관제 |
| System monitor | 이 요청서에서는 구현 요청하지 않음. 별도 요청서 참조 | [System monitor 요청서](CR-관제_09-08_15-15_System_monitor_E-stop_UI_운영상태_연계.md) | System monitor |
| 비전 | 변경 불필요. 이 계약의 직접 송수신자가 아님 | 해당 없음 | 비전 |

공용 `.msg` 변경은 AMR·관제·System monitor 합의 후 별도의 명시적 코드 변경 승인을 받아 수행한다.

## 영향과 적용 순서

1. AMR·관제·System monitor가 공용 enum과 필드 변경, 제거할 legacy 필드를 검토한다.
2. `target_pose` 제거 여부, E-stop reason 우선순위·clear 조건, ACCEPTED 누락 뒤 재전송 중단을 합의한다.
3. 같은 기준 버전에서 `patrol_interfaces`를 수정하고 AMR·관제·System monitor 의존 코드를 함께 반영한다.
4. robot1·robot6 단위시험 후 integration IT-02·03·04·10·11·12를 수행한다.

혼합 버전에서는 MissionCommand 직렬화, Heartbeat 필드, EStop 필드가 달라 통신 또는 빌드가 실패할 수 있다. 특히 기존 command store의 fingerprint에서 `parameters_json`을 제거하면 재시작 후 같은 command ID 비교 결과가 달라질 수 있으므로, 저장 형식 버전·기존 항목 처리 방안을 구현 전에 합의한다. 롤백은 공용 메시지와 세 단위 소비 코드를 같은 계약 버전으로 함께 되돌리는 방식으로만 수행한다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | 미반영 | 기존 코드가 이전 TBD 기준으로 존재 | 검토·코드 승인·구현·시험 |
| AMR / robot6 | 미반영 | 기존 코드가 이전 TBD 기준으로 존재 | 검토·코드 승인·구현·시험 |
| 관제 | 문서 반영 | interfaces.md·control_server.md 2026-09-08 갱신 | 코드 승인·구현·시험 |
| System monitor | 미반영 | 별도 요청서 | UI 경계·표시 계약 검토 |
| 비전 | 변경 불필요 제안 | 직접 송수신 없음 | 검토 확인 |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: IT-02, IT-03, IT-04, IT-10, IT-11, IT-12
- 추가 시험·기대 결과:
  - check_state 미정의 값·역방향 전이 폐기, ID 일치 복구 예외, 최종 report 수락을 확인한다.
  - 모든 command의 mission·target 조합과 INVALID_MISSION/PARAMETERS/STATE를 경계값으로 시험한다.
  - 기존 `parameters_json` 포함 command store 재시작·중복 처리 migration을 시험한다.
  - Heartbeat session 변경·1초 timeout·이전 token 폐기와 무자동재개를 시험한다.
  - 물리/manual reset 경로가 없고 새 E-stop enum·`all`·대표 원인이 양 로봇에 동일하게 적용되는지 확인한다.
  - safety_state와 motion_stopped·reason_code가 독립적으로 올바르게 보고되는지 확인한다.
  - 정상 Ctrl+C와 강제 종료 각각에서 AMR이 lease/heartbeat timeout으로 정지하고, 재기동 뒤 새 token·command 전 이동하지 않는지 확인한다.
- 실제 실행 결과와 증거: NOT_RUN. 문서 요청만 작성했으며 코드·장비 시험은 수행하지 않음
- 미실행 또는 BLOCKED 항목: 공용 `.msg` 및 AMR 코드 변경 승인, 우선순위·clear 조건·migration 합의 전 BLOCKED

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-08 | 관제 | 공용 계약 반영 및 AMR 검토 요청 초안 작성 | 사용자 승인·확정 내용 |
