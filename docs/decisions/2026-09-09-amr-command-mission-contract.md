# AMR 공동 구현 계약 v1

- 결정일: 2026-09-09
- 대상: 조정묵 `patrol_amr_safety`, 박성현 `patrol_amr`
- 상태: AMR 내부 합의안 · 조정묵 검토 대기
- 구현 상태: 단계별 반영 중
- 외부 확인: System monitor ACK 계약 및 공용 메시지 추가 승인 필요
- 기준 문서: `docs/amr_patrol_safety_flowchart.md`, `docs/interfaces.md`
- 문서 목적: `command_gateway`와 `mission_supervisor` 사이의 공동 구현 기준을 고정하고, 담당 범위와 통합시험 조건을 명확히 한다.
- 주의: 이 문서는 구현 계약을 정리한 것이며, 모든 코드와 통합시험이 완료됐다는 뜻은 아니다.

## 1. 역할과 명령 진입점

명령 처리 구조는 다음과 같이 확정한다.

```text
관제
  → /{robot}/mission_command
  → patrol_interfaces/MissionCommand
  → command_gateway
  → /{robot}/mission_dispatch
  → patrol_interfaces/MissionCommand
  → mission_supervisor
```

- 공개 `mission_command`는 `command_gateway`만 구독한다.
- `mission_supervisor`는 공개 명령을 직접 구독하지 않는다.
- gateway는 `command_id` 문자열이 아니라 `MissionCommand` 전체를 전달한다.
- 외부 `CommandCheck` 발행자는 `command_gateway` 하나로 고정한다.
- mission은 실제 임무 실행, Nav2·Dock Action, checkpoint, 상태 및 결과 생성을 담당한다.

## 2. ACCEPTED 발행 시점

`CommandCheck.ACCEPTED`는 gateway가 SQLite에 저장했다는 의미만으로 사용하지 않는다. 공식 의미인 “형식·상태 검증을 통과하고 실행 대기열에 진입함”을 만족하도록 다음 순서를 사용한다.

```text
1. gateway가 공개 MissionCommand 수신
2. 기본 형식·robot ID·command ID·중복 검사
3. SQLite에 PENDING 상태로 저장
4. mission_dispatch로 전체 MissionCommand 발행
5. mission이 현재 mission 상태와 실제 수용 가능 여부 확인
6. mission이 ADMITTED 또는 REJECTED 내부 이벤트 발행
7. ADMITTED이면 gateway가 ACCEPTED 발행
8. worker가 실제 실행을 시작하면 STARTED 이벤트 발행
9. gateway가 EXECUTING 발행
```

이 순서는 mission이 실행되지 않았는데 gateway가 먼저 `ACCEPTED`를 보내는 문제를 방지한다.

gateway는 mission의 admission 응답을 기다리는 동안 동일 명령을 재전달할 수 있다. 최초 수신 후 4초까지 응답이 없으면 다음과 같이 종료한다.

```text
CommandCheck.check_state = CHECK_REJECTED
CommandCheck.reason_code = INVALID_STATE(206)
CommandCheck.reason = MISSION_DISPATCH_TIMEOUT
```

4초가 지난 명령은 mission이 뒤늦게 기동하더라도 실행하지 않는다.

## 3. 내부 토픽과 QoS

| 토픽 | 메시지 타입 | QoS |
|---|---|---|
| `/{robot}/mission_dispatch` | `patrol_interfaces/MissionCommand` | RELIABLE / TRANSIENT_LOCAL / KEEP_LAST(10) |
| `/{robot}/mission_execution_event` | `patrol_interfaces/MissionExecutionEvent` | RELIABLE / TRANSIENT_LOCAL / KEEP_LAST(20) |
| `/{robot}/motion_allowed` | `std_msgs/Bool` | RELIABLE / TRANSIENT_LOCAL / KEEP_LAST(1) |

토픽은 robot1·robot6 namespace 안에서 상대 이름으로 생성한다.

`mission_dispatch`를 TRANSIENT_LOCAL로 두는 이유는 gateway보다 mission이 늦게 기동하더라도 마지막 명령을 받을 수 있게 하기 위해서다. 이 방식에서는 이전 명령이 다시 전달될 수 있으므로 mission의 영속 중복 방지가 반드시 필요하다.

## 4. MissionExecutionEvent 내부 메시지

gateway와 mission 사이에 다음 의미의 신규 내부 메시지를 사용한다.

```text
uint8 ADMITTED=1
uint8 REJECTED=2
uint8 STARTED=3
uint8 NONTERMINAL_STORED=4
uint8 RESULT_STORED=5

std_msgs/Header header
string command_id
string mission_id
string robot_id

uint8 event_type
string source_session_id
uint64 sequence

uint8 mission_state
uint32 reason_code
string reason

bool has_report
patrol_interfaces/PatrolReport report
```

이 메시지는 외부 관제용이 아니라 AMR 내부 연결용이다.

| 이벤트 | mission 발생 시점 | gateway 처리 |
|---|---|---|
| `ADMITTED` | 검증·중복 확인·worker queue 예약 완료 | SQLite를 ACCEPTED로 바꾸고 외부 ACCEPTED 발행 |
| `REJECTED` | 현재 상태에서 해당 명령을 수용할 수 없음 | SQLite를 REJECTED로 바꾸고 외부 REJECTED 발행 |
| `STARTED` | worker가 실제 실행 시작 | SQLite를 EXECUTING으로 바꾸고 외부 EXECUTING 발행 |
| `NONTERMINAL_STORED` | PAUSED·안전구역 대기 등 비종료 상태 저장 완료 | command 처리 완료, PatrolReport 없음 |
| `RESULT_STORED` | 최종 결과를 outbox에 안전하게 저장 완료 | SQLite 완료 처리 및 report payload 보관 |

`RESULT_STORED` 이벤트는 `has_report=true`여야 한다. 내부 `report`의 `robot_id`, `command_id`, `mission_id`는 이벤트의 세 ID와 모두 일치해야 한다.

같은 이벤트가 반복돼도 한 번만 적용하도록 다음 조합을 멱등성 키로 사용한다.

```text
command_id + event_type + report_id
```

완료 상태를 과거 상태로 되돌리는 이벤트는 무시하고 경고를 기록한다.

## 5. 명령 중재 규칙

공식 우선순위를 그대로 사용한다.

```text
STOP
  > MOVE_TO_SAFE_ZONE
  > DOCK
  > CANCEL
  > RESUME_PATROL
  > START_PATROL
```

실행 중 새 명령을 받았을 때의 처리 기준은 다음과 같다.

- 더 높은 우선순위 명령은 현재 Action을 취소하고 새 명령으로 교체한다.
- 같은 우선순위의 다른 command ID는 `REJECTED / INVALID_STATE`로 처리한다.
- 더 낮은 우선순위 명령은 대기열에 남기지 않고 `REJECTED / INVALID_STATE`로 처리한다.
- 같은 command ID와 같은 내용은 현재 상태만 다시 응답하고 재실행하지 않는다.
- 같은 command ID에 내용이 다르면 `REJECTED / COMMAND_ID_CONFLICT`로 처리한다.
- 오래된 이동 명령이 나중에 실행되는 것을 방지하기 위해 낮은 우선순위 명령을 FIFO로 보관하지 않는다.
- 교체된 이전 command는 gateway 내부에서 `SUPERSEDED`로 기록한다. mission 전체가 종료되지 않았다면 별도 PatrolReport를 만들지 않는다.

## 6. 명령별 처리 계약

| 명령 | 허용 조건 | 처리 결과 |
|---|---|---|
| `STOP` | 항상 허용 | Action 취소, `MISSION_PAUSED`, checkpoint 보존, PatrolReport 없음 |
| `START_PATROL` | 활성 mission 없음 | 새 mission ID로 W1부터 순찰 시작 |
| `MOVE_TO_SAFE_ZONE` | 동일한 활성 mission ID | 기존 이동 취소, 안전구역 이동, 도착 후 `MISSION_WAITING_SAFE_ZONE` |
| `RESUME_PATROL` | PAUSED 또는 WAITING_SAFE_ZONE이며 checkpoint 존재 | 동일 mission ID로 순찰 재개 |
| `DOCK` | 동일한 활성 mission 또는 idle 상태의 신규 mission | 지정된 자기 로봇 dock으로 이동하고 성공 시 mission 종료 |
| `CANCEL` | 동일한 활성 mission 존재 | Action 취소, checkpoint 삭제, CANCELED 결과 저장 |

### 6.1 STOP

활성 mission이 없어도 안전한 no-op으로 수락한다.

```text
ADMITTED
  → STARTED
  → NONTERMINAL_STORED
  → RobotStatus.MISSION_PAUSED
  → PatrolReport 없음
```

STOP은 재개 가능한 상태를 보존한다. motion 권한 복구만으로 자동 재출발하지 않으며 별도 `RESUME_PATROL` 명령이 필요하다.

### 6.2 RESUME_PATROL

`resume_policy`는 `next_waypoint`로 고정한다. checkpoint에는 다음에 방문할 waypoint index를 저장한다.

- W2로 이동 중 정지했다면 W2부터 다시 실행한다.
- W2 도착 후 checkpoint까지 저장한 뒤 정지했다면 W3부터 실행한다.
- 완료된 waypoint를 임의로 다시 방문하지 않는다.
- CANCEL된 mission은 재개할 수 없다.

### 6.3 MOVE_TO_SAFE_ZONE

- 반드시 현재 활성 mission과 같은 mission ID를 사용한다.
- 안전구역 도착 후 `MISSION_WAITING_SAFE_ZONE`을 저장한다.
- 도착 후 순찰을 자동 재개하지 않는다.
- 다시 순찰하려면 별도 `RESUME_PATROL`이 필요하다.
- 안전구역 탐색 또는 이동에 실패하면 mission을 FAILED로 종료하고 PatrolReport를 생성한다.

### 6.4 CANCEL

- 활성 mission이 없거나 mission ID가 다르면 `REJECTED / INVALID_MISSION(204)`이다.
- 취소 성공 시 checkpoint를 삭제한다.
- `PatrolReport.result=CANCELED`를 사용한다.
- `reason_code=CONTROL_CANCELED(100)`을 사용한다.
- 다시 시작하려면 새 mission ID의 `START_PATROL`이 필요하다.

## 7. 안전 권한 상실

`motion_allowed=false`는 모든 MissionCommand보다 우선한다.

```text
motion_allowed=false
  → 활성 Nav2·Dock Action 즉시 취소
  → mission CANCELED
  → checkpoint 삭제
  → CANCELED PatrolReport를 outbox에 저장
  → 자동 재출발 금지
```

mission은 `Bool`만으로 token·heartbeat·E-stop 중 정확한 원인을 알 수 없으므로 공통 결과를 사용한다.

```text
reason_code = SAFETY_POLICY_CANCELED(102)
reason = LOCAL_SAFETY_REVOKED
```

세부 안전 원인은 `RobotStatus`의 safety state와 reason에서 확인한다. `motion_allowed=true`로 복구되더라도 새 DriveToken과 새 MissionCommand가 모두 오기 전에는 이동하지 않는다.

## 8. 중복 실행과 재시작

gateway SQLite와 mission 실행 ledger의 역할을 분리한다.

```text
gateway SQLite
  = 외부 command 상태의 기준
  = PENDING / ACCEPTED / EXECUTING / REJECTED / COMPLETED

mission 실행 ledger
  = 실제 Nav2·Dock side effect 중복 방지
  = command fingerprint / 실행 여부 / checkpoint
```

두 저장소를 사용하는 이유는 책임을 중복하기 위해서가 아니라, gateway의 재전달이나 프로세스 재시작으로 실제 Action이 두 번 실행되는 것을 막기 위해서다.

### 8.1 gateway 재시작

- SQLite에서 PENDING·ACCEPTED·EXECUTING 상태를 복구한다.
- PENDING이며 최초 수신 후 4초가 지나지 않은 명령만 다시 전달한다.
- 완료·거절·만료된 명령은 재전달하지 않는다.
- 동일 command ID의 기존 상태는 새로운 command로 만들지 않는다.

### 8.2 mission 재시작

- TRANSIENT_LOCAL `mission_dispatch`를 다시 수신한다.
- 실행 ledger에서 command ID와 fingerprint를 확인한다.
- 이미 처리한 명령은 다시 실행하지 않는다.
- 저장된 현재 상태 또는 결과 이벤트만 다시 발행한다.

### 8.3 이벤트 순서 역전

gateway가 허용하는 상태 방향은 다음과 같다.

```text
PENDING
  → ACCEPTED
  → EXECUTING
  → COMPLETED 또는 NONTERMINAL 완료
```

`STARTED`가 `ADMITTED`보다 먼저 도착하면 gateway는 내부적으로 ACCEPTED를 먼저 기록하고 외부에도 다음 순서로 발행한다.

```text
ACCEPTED
  → EXECUTING
```

완료 상태에서 도착한 과거 이벤트는 무시하고 프로토콜 경고만 기록한다.

## 9. 영속 저장 경로와 소유자

기본 경로는 로봇별로 분리한다.

```text
~/.local/state/patrol_amr/robot1/command_store.sqlite3
~/.ros/patrol_amr/robot1/mission_execution_store.json
~/.ros/patrol_amr/robot1/mission_status.json
~/.ros/patrol_amr/robot1/patrol_report_outbox.json
```

robot6도 동일한 구조를 사용한다.

| 저장소 | 작성자 | 소비자 |
|---|---|---|
| `command_store.sqlite3` | command gateway | command gateway |
| `mission_execution_store.json` | mission supervisor·worker | mission supervisor·worker |
| `mission_status.json` | mission 실행부 | status reporter |
| `patrol_report_outbox.json` | mission 결과 생산부 | status reporter |

- 같은 로봇의 mission과 status reporter에는 동일한 절대 경로를 전달한다.
- JSON 저장은 임시 파일 작성, flush, `fsync`, 원자 교체를 사용한다.
- outbox의 동시 접근은 파일 잠금으로 보호한다.
- JSON 문법이나 schema version이 손상되면 빈 파일로 자동 덮어쓰지 않는다.
- 손상된 원본을 보존하고 관련 기능을 fail-closed 처리한다.

## 10. PatrolReport outbox와 ACK

AMR 구현에서는 다음 원칙을 사용한다.

```text
ROS publish 호출 성공
  ≠ 수신 애플리케이션 저장 성공
```

따라서 production에서는 publish 호출 성공만으로 outbox를 삭제하지 않는 방향을 채택한다.

현재 존재하는 `IngestionAck`를 다음 기준으로 사용하는 안을 System monitor에 확인 요청한다.

```text
토픽: /{robot}/ingestion_ack
타입: patrol_interfaces/IngestionAck

entity_type = PATROL_REPORT
source_message_id = report_id
status = STORED 또는 DUPLICATE
```

outbox 삭제 조건은 다음과 같다.

```text
robot_id 일치
AND entity_type == PATROL_REPORT
AND source_message_id == pending report_id
AND status in {STORED, DUPLICATE}
```

다음 응답에서는 삭제하지 않는다.

```text
INCOMPLETE
REJECTED
ID 불일치
다른 robot ID
```

- ACK가 오기 전까지 같은 report ID로 1초 간격 재발행한다.
- 30초 이후에는 경고를 남기되 결과를 삭제하지 않는다.
- 재전송을 위해 새로운 report ID를 만들지 않는다.
- System monitor가 이미 같은 report ID를 저장해 `DUPLICATE`를 반환한 경우에는 전달 완료로 판단할 수 있다.

ACK 발행 주체와 필드 의미는 System monitor가 포함되는 공용 계약이다. AMR 내부 방침은 위와 같이 정하되, 최종 production 적용은 System monitor의 계약 확인 후 진행한다.

## 11. 개발 담당 분리

### 11.1 조정묵 담당

- `command_gateway`를 `mission_dispatch/MissionCommand`로 변경
- gateway SQLite에 PENDING·REJECTED·비보고 완료 상태 추가
- `MissionExecutionEvent` 구독 및 검증
- 외부 ACCEPTED·EXECUTING·REJECTED 발행
- dispatch timeout·재전송·재시작 복구
- status reporter의 IngestionAck 수신 및 outbox 삭제 조건 적용
- Nav2·Dock·readiness·motion permission 어댑터와 ROS smoke test

### 11.2 박성현 담당

- mission의 `MissionExecutionEvent` 발행부 구현
- 명령별 admission과 우선순위 중재
- worker 시작 직전에 STARTED 발행
- STOP·안전구역 대기 시 NONTERMINAL_STORED 발행
- outbox 저장 성공 후 RESULT_STORED 발행
- `next_waypoint` 재개 정책 구현
- mission 실행 ledger와 checkpoint 관리
- mission 상태·최종 결과의 단위시험

### 11.3 공동 담당

- 신규 메시지 정의 검토
- gateway와 mission의 robot·command·mission ID 일치 검증
- 같은 ID 중복·충돌 시험
- gateway/mission 개별 재시작 시험
- STOP·CANCEL·우선순위 교체 시험
- `motion_allowed=false` 안전 취소 시험
- outbox ACK·재전송·손상 파일 시험

## 12. 구현 및 병합 순서

1. 현재 양쪽 완료 커밋을 확인해 공통 기준점을 정한다.
2. `MissionExecutionEvent.msg` 계약을 별도 공통 커밋으로 먼저 반영한다.
3. `RobotStatus.msg`의 중복 `SAFETY_*` 상수를 제거하고 interfaces 빌드를 확인한다.
4. 정묵님이 gateway를 `mission_dispatch/MissionCommand`로 변경한다.
5. 성현님이 mission event publisher와 중재 로직을 구현한다.
6. 양쪽 단위시험과 로컬 ROS smoke test를 각각 통과한다.
7. gateway·mission·status reporter를 같은 ROS domain에서 연결한다.
8. System monitor와 IngestionAck 저장 시험을 수행한다.
9. 바퀴 비접지 상태에서 안전 차단 시험을 수행한다.
10. 마지막 단계에서만 통제된 공간의 저속 실주행을 수행한다.

권장 작업 브랜치는 다음과 같다.

```text
공통 계약 커밋
├── feature/amr-mission-core       박성현
└── feature/amr-navigation-gateway 조정묵
```

같은 파일을 동시에 수정하지 않는다. 공용 메시지, package metadata, launch 통합 파일은 한 사람이 먼저 별도 커밋으로 반영한 뒤 상대 브랜치에서 가져온다.

## 13. 공동 합격 기준

- 공개 `mission_command` 구독자는 gateway 하나다.
- `mission_dispatch`의 publisher와 subscriber 타입이 모두 `MissionCommand`다.
- 같은 command ID가 실제 Action을 두 번 발생시키지 않는다.
- 잘못된 robot·mission·target 조합은 Nav2 goal을 만들지 않는다.
- ACCEPTED 전에 mission admission이 확인된다.
- 실제 worker 시작 전에는 EXECUTING을 발행하지 않는다.
- STOP은 checkpoint를 보존하고 PatrolReport를 만들지 않는다.
- CANCEL은 checkpoint를 삭제하고 CANCELED 결과를 저장한다.
- `motion_allowed=false`이면 Action 취소와 최종 `cmd_vel=(0,0)`이 모두 확인된다.
- 안전 상태 복구만으로 자동 출발하지 않는다.
- gateway·mission·status reporter 재시작 후에도 명령과 결과가 중복되지 않는다.
- outbox는 전달 완료 조건을 만족하기 전에 삭제되지 않는다.
- `/robotN/cmd_vel`의 최종 publisher는 local safety 하나다.

## 14. 아직 외부 확인이 필요한 사항

다음 항목은 AMR 두 사람의 구현 방향은 정할 수 있지만, 공용 계약 확정에는 다른 담당자의 확인이 필요하다.

1. System monitor의 `IngestionAck`를 PatrolReport 최종 저장 ACK로 공식 채택할지 여부
2. `source_message_id=report_id` 사용 여부와 `entity_id`의 정확한 의미
3. System monitor ACK 하나로 outbox를 삭제할지, 관제의 별도 ACK까지 요구할지 여부
4. 신규 `MissionExecutionEvent.msg`를 공용 `patrol_interfaces`에 추가하는 변경 승인

외부 확인 전에는 임의로 “관제와 System monitor 모두 전달 완료”라고 판단하지 않는다.
