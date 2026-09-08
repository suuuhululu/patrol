# [관제] System monitor E-stop UI·운영 상태 연계 검토 요청

- 상태: 초안
- 최초 작성 시각: 2026-09-08 15:15 KST
- 요청자: 관제 팀
- 요청 단위: 관제
- 대상 단위 및 로봇: System monitor / robot1·robot6·all 표시
- 관련 TBD ID: TBD-IF-003·004·011, TBD-CTRL-004, TBD-MON-003
- 기준 문서·절: [interfaces.md 3.1·4·10절](../interfaces.md), [control_server.md 3·6·7절](../control_server.md), [scenarios.md UC-07·08](../scenarios.md), [integration.md IT-10·11](../integration.md)
- 결정 일자·근거: 2026-09-08 사용자 확정. 물리 E-stop 대신 UI 운영자 정지만 구현하고 관제 판단과 System monitor 표시 책임을 분리하기 위함
- 코드 변경 승인 근거·범위: 미승인. 이 요청서는 System monitor 및 공용 `.msg` 변경 권한을 부여하지 않음

## 변경 이유

현재 System monitor는 읽기 전용 Dashboard가 기준이지만, 사용자는 하드웨어·물리 E-stop 없이 UI 정지와 해제 요청을 추가하기로 했다. 이는 기존 역할 경계를 바꾸므로 PM과 System monitor 팀의 명시적 검토가 필요하다. UI는 안전 판단자가 되지 않고 관제 소유 API에 요청만 전달해야 한다.

현재 공용·System monitor 코드에는 최신 계약과 겹치거나 충돌할 가능성이 있는 타입이 있다.

- `EStopState.msg`에는 `manual_reset_required`가 있고 `/control/estop`의 `EStop.msg`와 역할이 겹친다.
- `MissionCommandAck.msg`는 ACCEPTED/REJECTED/DUPLICATE를 정의해 정식 `CommandCheck`와 중복된다.
- `ControlHeartbeat.msg` 필드가 최신 `control_session_id/uint64 sequence` 계약과 다르다.
- System monitor safety model·service·schema가 `latched` 또는 `manual_reset_required`를 사용한다.

## 변경 전 → 변경 후

| 항목 | 현재 기준·구현 | 요청 계약 | 구분 |
|---|---|---|---|
| Dashboard 역할 | 읽기 전용 | 읽기 전용 유지 + 관제 API에 OPERATOR 정지·해제 요청을 보내는 제한된 UI 추가 | 제안, PM·System monitor 검토 필요 |
| E-stop 발행·판단 | 모니터 타입·service가 별도 상태를 가질 수 있음 | Safety Arbiter만 `/control/estop` 발행·해제 판단, UI 직접 발행 금지 | 결정 |
| 물리 E-stop | latched/manual reset 필드 존재 | 하드웨어·물리 E-stop 및 수동 reset 미구현, 관련 UI·필드 제거 | 결정 |
| UI 대상 | 미정 | `robot1`, `robot6`, `all` | 결정 |
| UI reason | 미정 | 정지 요청은 OPERATOR=1 | 결정 |
| 해제 | manual reset 가능성 | UI 해제는 OPERATOR 원인 clear 요청이며, 모든 원인 제거 3초는 관제가 판정 | 결정 |
| 원인 표시 | 단일 또는 manual reset 중심 | EStop 대표 reason 1개와 관제 디버깅용 활성 원인 집합을 구분해 표시 | 방향 결정, 전달 타입은 TBD-IF-011 |
| Heartbeat | message_id/source_id/boot_id/uint32 sequence | `ControlHeartbeat`: header/control_session_id/uint64 sequence | 결정 |
| 종료·재기동 | 표시 계약 없음 | CONTROL_SHUTDOWN과 새 session→게이트→새 token→별도 command 진행을 표시·기록 | 의미 결정, 토픽·필드는 TBD-IF-011 |
| 명령 ACK | MissionCommandAck 존재 | 외부 명령 확인의 canonical 타입은 CommandCheck; 중복 타입은 사용처 확인 후 폐기 검토 | 검토 요청 |

## 제안 UI 흐름

1. 운영자가 `robot1`, `robot6`, `all` 중 대상을 고르고 정지를 누른다.
2. System monitor는 인증·중복 방지 정보를 포함해 관제 소유 요청 API를 호출한다. 구체 API·request ID·응답 필드는 TBD-CTRL-004다.
3. 관제가 요청을 검증하고 OPERATOR 원인을 활성화한 뒤 Safety Arbiter가 EStop을 발행한다.
4. UI는 요청 접수 응답과 관제가 발행한 실제 E-stop 상태를 분리해 보여준다. 요청 성공만으로 정지 완료를 표시하지 않는다.
5. 해제 버튼은 OPERATOR 원인 clear만 요청한다. 관제는 다른 활성 원인과 3초 연속 제거 조건을 확인한다.
6. UI는 해제 대기, 다른 활성 원인, 대표 원인, 실제 `active=false`, 새 token·command 전 정지 유지 상태를 구분한다.

## 표시 의미

- E-stop reason은 UNKNOWN=0, OPERATOR=1, COMMUNICATION=2, TOKEN=3, OBSTACLE=4, KEEPOUT_FAILURE=5, SYSTEM_FAULT=6이다.
- `/control/estop`은 `SYSTEM_FAULT → UNKNOWN → OPERATOR → KEEPOUT_FAILURE → COMMUNICATION → OBSTACLE → TOKEN` 순서에서 가장 먼저 활성인 대표 원인 하나만 전달한다. 이는 v1.0 확정 계약이다.
- 전체 활성 원인 집합은 `uint8[] active_reasons` 의미의 관제 판단·디버깅 계약으로 별도 제공한다. System monitor가 토픽을 조합해 자체 원인 집합을 계산하지 않는다.
- RobotStatus `safety_state`는 UNKNOWN=0, NORMAL=1, STOPPING=2, STOPPED=3, ESTOPPED=4, ERROR=5다. 구체 원인은 reason_code를 표시하며 ESTOPPED만으로 실제 정지를 단정하지 않는다.
- `CONTROL_SHUTDOWN`, `COMMAND_CHECK_TIMEOUT`, `ACCEPTED_MISSING`은 E-stop reason이 아니라 관제 운영 이벤트다.

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| System monitor | 제한된 OPERATOR 정지·해제 UI가 읽기 전용 원칙의 허용 예외인지 PM과 검토 | Dashboard 역할·권한 | System monitor·PM |
| System monitor | 관제 API 호출만 수행하고 직접 `/control/estop` 발행·안전 판정을 하지 않도록 설계 | UI action/service client | System monitor |
| System monitor | 요청 접수·실제 활성·해제 대기·다른 원인·실제 정지 여부를 분리 표시 | Dashboard safety view | System monitor |
| System monitor | `manual_reset_required`, `latched` 의존 제거와 DB migration 필요 여부 제시 | `src/patrol_sysmon/app/models/safety.py`, `src/patrol_sysmon/app/ros/payloads.py`, `src/patrol_sysmon/app/schema.sql`, `src/patrol_sysmon/app/services/safety_service.py` | System monitor |
| System monitor | `EStopState.msg`의 유지·폐기·표시 전용 재정의안을 제시 | `src/patrol_interfaces/msg/EStopState.msg` 소비부 | System monitor |
| System monitor | `MissionCommandAck.msg` 사용처 확인 후 CommandCheck로 통합·폐기 여부 회신 | ROS payload/subscriber·DB | System monitor |
| System monitor | 새 ControlHeartbeat와 safety_state enum 소비·표시 영향 확인 | ROS subscriber/QoS/testkit | System monitor |
| System monitor | CONTROL_SHUTDOWN과 재기동 진행 상태의 표시·저장 요구 필드 제시 | TBD-IF-011 운영 상태·로그 | System monitor |
| 관제 | 요청 API, 응답, E-stop 판단, 전체 원인 집합·운영 상태 발행안을 제시 | TBD-CTRL-004·IF-011 | 관제 |
| AMR | E-stop·Heartbeat·상태 계약은 별도 요청서에서 검토 | [AMR 요청서](CR-관제_09-08_15-15_AMR_명령_Heartbeat_E-stop_상태_계약.md) | AMR |
| 비전 | 변경 불필요. 직접 송수신자가 아님 | 해당 없음 | 비전 |

## 영향과 적용 순서

1. PM·System monitor가 UI action을 읽기 전용 Dashboard의 제한된 예외로 허용할지 결정한다.
2. 관제 요청 API와 응답·권한·중복 요청 계약을 TBD-CTRL-004에서 합의한다.
3. EStopState·MissionCommandAck 중복 타입의 실제 사용처와 제거·migration 영향을 조사한다.
4. 공용 `.msg`, 관제 API, System monitor 소비·DB·UI를 호환되는 한 버전으로 반영한다.
5. mock 관제 API 단위시험 후 integration IT-10·11을 수행한다.

혼합 버전에서 UI가 직접 E-stop을 발행하거나 기존 manual-reset 상태를 해제로 해석하면 안전 상태가 분기될 수 있다. 공용 메시지 변경과 관제/System monitor 반영을 같은 배포 단위로 묶고, 구버전 UI에서는 정지·해제 버튼을 노출하지 않는다. DB 스키마 변경이 필요하면 별도 승인과 migration·rollback 계획을 받는다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | 미반영 | 별도 AMR 요청서 | 계약 검토·구현·시험 |
| AMR / robot6 | 미반영 | 별도 AMR 요청서 | 계약 검토·구현·시험 |
| 관제 | 문서 반영 | interfaces.md·control_server.md 2026-09-08 갱신 | API·상태 발행 코드 승인·구현 |
| System monitor | 계약 소비 반영 | 2026-09-08 `EStop` 구독 전환, `latched`·`manual_reset_required` 의존 제거, `safety_state` 저장·표시(patrol_sysmon 구현 로그 34) | UI 정지·해제 버튼은 PM 결정·TBD-CTRL-004 후, `active_reasons`·CONTROL_SHUTDOWN 표시는 TBD-IF-011 후 |
| 비전 | 변경 불필요 제안 | 직접 송수신 없음 | 검토 확인 |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: IT-10, IT-11
- 추가 시험·기대 결과:
  - UI 정지 클릭이 관제 API 요청만 발생시키고 `/control/estop` 직접 publisher가 없음을 확인한다.
  - 요청 접수와 실제 E-stop 활성, STOPPING, STOPPED를 구분해 표시한다.
  - robot1·robot6·all 대상과 중복 요청을 시험한다.
  - UI 해제 뒤 다른 원인이 남은 경우 active를 해제로 표시하지 않고, 전체 제거 3초 경계에서만 해제한다.
  - 물리 E-stop·manual reset UI와 DB 의존이 남지 않았는지 확인한다.
  - 대표 reason과 관제가 제공한 전체 원인 집합을 혼동하지 않는다.
  - CONTROL_SHUTDOWN, heartbeat/token timeout, 새 control session, 새 token, 별도 command 진행 상태를 순서대로 기록·표시한다.
- 실제 실행 결과와 증거: NOT_RUN. 문서 요청만 작성했으며 코드·DB·UI 시험은 수행하지 않음
- 미실행 또는 BLOCKED 항목: PM 역할 경계 결정, API·운영 상태 토픽 계약, 공용 `.msg` 및 System monitor 코드 변경 승인 전 BLOCKED

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-08 | 관제 | 공용 계약 반영 및 System monitor 검토 요청 초안 작성 | 사용자 승인·확정 내용 |
| 2026-09-08 | System monitor | `EStop`(target_robot_id·active·reason·sequence) 구독으로 전환하고 `EStopState`·`manual_reset_required`·`latched` 의존을 제거했다. E-stop 표는 대상별 최신 행으로 재구성하며 옛 기록은 `_legacy` 표로 보존한다(DB migration 자동). `MissionCommandAck`는 사용처가 없어 폐기에 동의한다. `EStopState.msg`는 소비처가 없어졌으므로 폐기 가능하다. `ControlHeartbeat`·`CommandCheck`는 구독하지 않아 영향 없음. 요청 접수와 실제 활성·정지 확인은 EStop 요약과 RobotStatus `safety_state`·`motion_stopped`로 분리 표시한다. UI 정지·해제 버튼은 PM 결정과 관제 API 계약 뒤 착수한다 | patrol_sysmon 구현 로그 34, 단위시험 통과 |
