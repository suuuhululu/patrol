# AMR 기능 설계

상태: 설계 초안 · 담당: AMR 팀 · 통합 실행 위치: PC 1·2 · 공통 계약: [interfaces.md](interfaces.md)

## 1. 책임과 경계

AMR1(robot1)과 AMR2(robot6)은 이 문서를 공유한다. 각 로봇은 명령 수신·임무 실행, Nav2·AMCL, 로컬 안전, 배터리·도킹, 감지·증적 생성을 담당한다. 식별 차이는 [architecture.md](architecture.md)에 둔다.

관제는 임무·주행 권한을 결정하고 AMR은 실행과 로컬 안전을 담당한다. PC 4 CCTV 이벤트 생성은 AMR 책임이 아니다. 기능 구분은 실제 ROS 노드 분할을 확정하지 않는다.

| 기능 | 입력 | 출력·역할 |
|---|---|---|
| mission_supervisor | MissionCommand, 로컬 상태 | 내부 Nav2 Action, 임무 진행·결과 |
| local_safety_supervisor | token, heartbeat, E-stop, 장애물, 주행 후보 | 최종 로봇별 속도 출력 |
| navigation/localization | 지도, LiDAR, odometry 등 | 경로 실행, map pose·유효성 |
| battery_monitor | SOC·충전 상태 | Battery enum |
| docking 기능 | 도킹 임무·센서 | 도킹 상태·결과 |
| 로컬 Detection·증적 | OAK-D 영상 | 후보, 확정 이벤트, 증적 |
| 상태·결과 발행 | 위 기능 상태 | RobotStatus, PatrolReport |

## 1.1 시나리오별 코드 분리와 개발 단위

**개발 기준:** AMR 팀은 시나리오별 동작 코드를 별도 파일·모듈로 분리하여 개발한다. 하나의 파일에 모든 시나리오를 누적하지 않는다. AMR1·AMR2는 같은 시나리오 구현을 공유하고 robot_id·namespace·장비 차이는 설정으로 구분한다. 코드 분리는 독립 ROS 노드·패키지·프로세스를 시나리오마다 생성한다는 뜻이 아니다.

아래는 분리할 동작 범위이며 파일명·패키지명은 구현 시 실제 저장소 구조에 맞춰 정한다. 통합 시나리오의 관제 판단과 AMR 실행을 구분한다.

| 시나리오 모듈 | AMR 구현 범위 | 연계·미정 기준 |
|---|---|---|
| 정상 순찰 | START_PATROL에 따른 waypoint 이동·방문·스캔·완료 처리 | W-01, TBD-AMR-005 |
| 안전구역 대피 | MOVE_TO_SAFE_ZONE 실행·도착·실패 보고 | W-02, TBD-CTRL-002, TBD-INT-003 |
| 순찰 재개 | RESUME_PATROL 수신 후 합의된 재개 지점에서 실행 | W-02·04, TBD-AMR-005 |
| 도킹 | DOCK 실행·센서 확인·timeout·결과 보고 | W-03, Q-09, TBD-AMR-004 |
| 감지·증적 | 후보 처리·yaw 정렬·확정 이벤트·증적 생성 | W-06, TBD-AMR-001, TBD-IF-006·007 |
| 중단·복구 대응 | STOP/CANCEL·안전 중단에 대한 실행 상태 정리, 복구 후 관제 명령 대기 | W-04·05, TBD-AMR-005·006, TBD-CTRL-001 |

역할 교대 대상 선정, Keepout 조정, 주행 재개·E-stop 해제 결정은 관제 책임이다. AMR의 중단·복구 모듈이 이를 대신 판단하거나 통신 복구만으로 재출발하지 않는다. 화재 후 후속 임무 순서는 TBD-INT-004를 따른다.

공통 기능은 다음과 같이 한 곳에서 관리한다.

- `mission_supervisor`: 명령 검증·중복 제거·시나리오 선택·전환 및 공통 임무 수명 관리. STOP/CANCEL/대체 의미는 관련 TBD를 따른다.
- `local_safety_supervisor`: 모든 시나리오에 공통으로 적용되는 로컬 안전과 최종 속도 출력. 시나리오 모듈이 직접 최종 cmd_vel을 발행하지 않는다.
- Nav2 연결·위치·배터리·상태/결과 발행: 공통 모듈을 사용하며 시나리오별로 복제하지 않는다. 감지 모듈의 주행 후보도 같은 안전 경로를 통과한다.

각 모듈은 진입·종료 조건, 입력 명령·필요 상태, 정상·실패·취소 결과와 전환 시 자원 정리 책임을 문서화한다. 콜백·타이머·Nav2 목표가 종료된 시나리오에 남아 중복 동작하지 않도록 처리하며, 미정 전환 규칙은 구현 전에 해당 TBD에서 합의한다.

## 1.2 코드별 Flowchart 작성

각 시나리오 모듈과 공통 동작 모듈에 별도의 Mermaid flowchart를 작성한다. 실제 코드가 추가되면 아래 대응표를 모듈별로 채우고 그림을 같은 절에 추가한다. 표의 미작성 상태는 구현 완료를 뜻하지 않는다.

| 대상 코드·모듈 | 코드 경로·진입 함수 | Flowchart·대조 상태 |
|---|---|---|
| 정상 순찰 | `src/patrol_amr/patrol_amr/scenarios/start_patrol.py:start_patrol`, `scenarios/patrol.py:PatrolScenario.run` | [미션·내비게이션 구현 대조](../src/patrol_amr/docs/mission_navigation.md#시나리오) · IT-02·07 |
| 안전구역 대피 | `src/patrol_amr/patrol_amr/scenarios/safe_zone.py:move_to_safe_zone` | [미션·내비게이션 구현 대조](../src/patrol_amr/docs/mission_navigation.md#시나리오) · 실제 후보 공급 TBD-CTRL-002 · IT-07·09 |
| 순찰 재개 | `src/patrol_amr/patrol_amr/scenarios/resume_patrol.py:resume_patrol` | [미션·내비게이션 구현 대조](../src/patrol_amr/docs/mission_navigation.md#시나리오) · 기본 비활성, TBD-AMR-005 |
| 도킹 | `src/patrol_amr/patrol_amr/scenarios/docking.py:dock`, `docking_runner.py:DockingRunner` | [미션·내비게이션 구현 대조](../src/patrol_amr/docs/mission_navigation.md#nav2와-도킹) · 센서 의미 TBD-AMR-004 · IT-13 |
| 감지·증적 | `src/patrol_amr/patrol_amr/fire_event_registry.py:FireEventRegistry`, `audio_note_sequence_adapter.py:AudioNoteSequenceAdapter` | [이벤트 기초 모듈 구현 대조](../src/patrol_amr/docs/mission_navigation.md#이벤트-기능-기초) · 상세 계약 TBD-AMR-001·TBD-IF-006·007 |
| 중단·복구 대응 | `src/patrol_amr/patrol_amr/scenarios/interruption.py:interrupt_navigation`, `mission_arbiter.py:MissionArbiter` | [미션·내비게이션 구현 대조](../src/patrol_amr/docs/mission_navigation.md#명령-콜백과-실행-수명) · STOP/CANCEL 차이 TBD-AMR-005 |
| mission_supervisor | `src/patrol_amr/patrol_amr/mission_supervisor.py:MissionSupervisor`, `mission_command_callback.py:MissionCommandCallback`, `mission_worker.py:MissionWorker`, `mission_controller.py:MissionController` | [미션·내비게이션 구현 대조](../src/patrol_amr/docs/mission_navigation.md#명령-콜백과-실행-수명) · CommandCheck 세부 TBD-IF-001 |
| command_store.py | [src/patrol_amr/patrol_amr/command_store.py](../src/patrol_amr/patrol_amr/command_store.py) · `CommandStore.register`·`mark_executing`·`complete`·`prune` | [2.1절](#21-command_storepy--구현-대조-완료-순수-모듈) 구현 대조 완료 (ROS 연결 대기) |
| mission_command_store.py | [src/patrol_amr/patrol_amr/mission_command_store.py](../src/patrol_amr/patrol_amr/mission_command_store.py) · `CommandStore.claim`·`finish`·`save_checkpoint` | [미션 내부 상태와 영속성](../src/patrol_amr/docs/mission_navigation.md#내부-상태와-영속성) 구현 대조 완료 |
| drive_token_guard.py | [src/patrol_amr/patrol_amr/drive_token_guard.py](../src/patrol_amr/patrol_amr/drive_token_guard.py) · `DriveTokenGuard.observe`·`authority` | [3.1절](#31-drive_token_guardpy--구현-대조-완료) 구현 대조 완료 |
| estop_guard.py | [src/patrol_amr/patrol_amr/estop_guard.py](../src/patrol_amr/patrol_amr/estop_guard.py) · `EStopGuard.observe`·`stopped` | [3.2절](#32-estop_guardpy--구현-대조-완료) 구현 대조 완료 |
| motion_guard.py | [src/patrol_amr/patrol_amr/motion_guard.py](../src/patrol_amr/patrol_amr/motion_guard.py) · `MotionGuard.evaluate` | [3.3절](#33-motion_guardpy--구현-대조-완료) 구현 대조 완료 (축소 범위) |
| local_safety_supervisor.py | [src/patrol_amr/patrol_amr/local_safety_supervisor.py](../src/patrol_amr/patrol_amr/local_safety_supervisor.py) · `SafetyGate`·`LocalSafetySupervisor` | [3.4절](#34-local_safety_supervisorpy--구현-대조-완료-축소-범위) 구현 대조 완료 (축소 범위) |
| heartbeat_guard.py | [src/patrol_amr/patrol_amr/heartbeat_guard.py](../src/patrol_amr/patrol_amr/heartbeat_guard.py) · `HeartbeatGuard.observe`·`state` | [3.5절](#35-heartbeat_guardpy--구현-대조-완료-순수-모듈) 구현 대조 완료 (ROS 연결 대기) |
| battery_monitor.py | [src/patrol_amr/patrol_amr/battery_monitor.py](../src/patrol_amr/patrol_amr/battery_monitor.py) · `classify_observation`·`BatteryStateModel.update` | [5.1절](#51-battery_monitorpy--구현-대조-완료) 구현 대조 완료 |
| robot_status_state.py | [src/patrol_amr/patrol_amr/robot_status_state.py](../src/patrol_amr/patrol_amr/robot_status_state.py) · `RobotStatusState.update_states`·`observe_pose`·`observe_odometry`·`snapshot` | [7.1절](#71-robot_status_statepy--구현-대조-완료) 구현 대조 완료 |
| Nav2 pose 실행 | `src/patrol_amr/patrol_amr/navigation_adapter.py:NavigationAdapter`, `nav2_goal_runner.py:Nav2GoalRunner` | [Nav2와 도킹](../src/patrol_amr/docs/mission_navigation.md#nav2와-도킹) 구현 대조 완료 · IT-16 |
| 실기 구동 gate | `motion_authorization.py`, `robot_readiness.py`, `robot_readiness_callbacks.py`, `motion_gate.py`, `launch/hardware_patrol.launch.py` | [ROS 구성과 설정](../src/patrol_amr/docs/mission_navigation.md#ros-구성과-설정) 구현 대조 완료 |
| 미션 내부 상태 | `src/patrol_amr/patrol_amr/mission_state.py:MissionStateTracker`, `mission_status_store.py:MissionStatusStore` | [내부 상태와 영속성](../src/patrol_amr/docs/mission_navigation.md#내부-상태와-영속성) 구현 대조 완료 |
| status_reporter.py | [src/patrol_amr/patrol_amr/status_reporter.py](../src/patrol_amr/patrol_amr/status_reporter.py) · `PublicationGate`·`StatusReporter` | [7.2절](#72-status_reporterpy--구현-대조-완료) RobotStatus·PatrolReport 결합 구현 대조 완료 |
| patrol_report.py | [src/patrol_amr/patrol_amr/patrol_report.py](../src/patrol_amr/patrol_amr/patrol_report.py) · `PatrolReportFactory` | [7.3절](#73-patrol_reportpy--구현-대조-완료) 순수 계약 모듈 구현 대조 완료 |
| 공통 Nav2 연결·위치·결과 발행 | 위 `navigation_adapter.py`·`nav2_goal_runner.py`·`scenarios/patrol.py`·`robot_status_state.py`·`status_reporter.py` 행으로 분리 | 실제 mission 경로 연결 완료, robot1·robot6 실기 검증 대기 |

각 그림에는 시작 조건, 함수·콜백 호출 순서, 조건별 분기, 외부 Action·토픽 송수신, 성공·실패·취소·안전 중단, 종료·복구 대기 경로를 표시한다. timeout·재시도 수치와 enum을 복제하지 않고 Q-ID·TBD-ID를 참조한다. 구현 대조 시 코드 버전과 관련 통합시험 ID를 기록한다.

아래는 **시나리오 분리 구조의 설계 개요**이며 코드별 상세 flowchart를 대체하지 않는다.

~~~mermaid
flowchart TD
    CMD[관제 MissionCommand] --> MS[mission_supervisor 공통 검증·중복 제거]
    MS --> VALID{유효한 명령인가}
    VALID -->|아니오| REJECT[계약에 따른 거부·진단 / TBD-IF-001]
    VALID -->|예| SELECT[명령·상태에 따른 시나리오 선택 / TBD-AMR-005]
    SELECT --> PATROL[정상 순찰]
    SELECT --> EVAC[안전구역 대피]
    SELECT --> RESUME[순찰 재개]
    SELECT --> DOCK[도킹]
    SELECT --> STOP[중단·복구 대응]
    PATROL -. 감지 연계 / TBD-AMR-001 .-> DETECT[감지·증적]
    PATROL --> NAV[공통 Nav2 연결]
    EVAC --> NAV
    RESUME --> NAV
    DOCK --> NAV
    NAV --> SAFE[local_safety_supervisor 공통 안전]
    DETECT -->|yaw 주행 후보| SAFE
    INPUT[토큰·heartbeat·E-stop·로컬 센서] --> SAFE
    SAFE --> OUTPUT[최종 속도 출력]
    SAFE -->|안전 중단 통지| STOP
    STOP --> WAIT[관제 명령·재개 조건 대기]
~~~

## 2. 명령과 임무 실행

1. 수신 namespace와 robot_id, 명령 enum, v1.0의 명령별 mission·target 필수 인자를 검증한다.
2. 영속 command_id 기록을 조회해 동일 명령을 다시 실행하지 않는다.
3. 주행이 필요한 명령은 유효 token 및 로컬 안전 조건을 통과해야 한다.
4. 필요할 때 mission_supervisor가 내부 Nav2 Action을 호출한다. 관제가 Nav2 Action을 직접 실행하는 경로를 만들지 않는다.
5. 진행 상태를 RobotStatus에 반영하고 종료 시 PatrolReport를 생성한다.

START_PATROL, MOVE_TO_SAFE_ZONE, RESUME_PATROL, DOCK는 실행 목적을 구분한다. STOP은 재개 가능한 상태를 보존하고 활성 mission이 없으면 안전한 no-op으로 ACCEPTED한다. CANCEL은 지정한 활성 mission 전체를 종료하고 재개 상태를 남기지 않으며 존재하지 않거나 끝난 mission은 INVALID_MISSION으로 거절한다. 명령 우선순위는 v1.0 계약을 따르고 세부 순찰 재개 지점만 TBD-AMR-005로 차기 버전에 이관한다.

Operational/Mission/Docking은 별개 상태 축이다. interfaces.md의 enum을 따른다. 순찰→대피→대기→재개, 복귀→도킹→완료/실패 흐름은 기준이나 모든 상태 쌍 사이의 전이가 허용된다는 뜻은 아니다. 상세 전이표는 TBD-AMR-005다.

### 2.1 command_store.py — 구현 대조 완료 (순수 모듈)

2026-09-08: 사용자 업무표의 AMR-05를 100% 종단 기준으로 닫기 위한 첫 구현으로 [command_store.py](../src/patrol_amr/patrol_amr/command_store.py)를 추가했다. ROS 구독 노드가 아니라 mission adapter가 사용할 SQLite 영속 중복 제거 모듈이다.

- `CommandStore.register()`는 `command_id`, `mission_id`, `robot_id`, command enum, `target_id`, target pose를 먼저 검증한 뒤 새 command를 ACCEPTED 내부 상태로 원자적으로 저장한다. DDS 수신 시각은 저장하지만 충돌 fingerprint에는 넣지 않는다. 삭제한 `parameters_json` legacy 컬럼은 기존 행을 보존하는 transaction migration으로 제거한다.
- 같은 command ID의 재수신은 현재 내부 상태를 `DUPLICATE_ACCEPTED`·`DUPLICATE_EXECUTING`·`DUPLICATE_COMPLETED`로 돌려준다. mission 실행을 다시 시작하지 않는다. 완료 상태에는 기존 report ID와 직렬화 payload를 함께 보존해 향후 adapter가 같은 PatrolReport를 재발행할 수 있다.
- 같은 command ID에서 interfaces.md 2절이 지정한 충돌 필드 중 하나라도 바뀌면 `COMMAND_ID_CONFLICT`를 반환하고 기존 행은 바꾸지 않는다. target pose는 JSON-compatible payload를 정규화해 key 순서 차이만 무시한다.
- Q-14에 따라 24시간 이내 command는 개수와 무관하게 모두 유지하고, 24시간보다 오래된 command도 최신 1,000개를 유지한다. DB 파일 경로는 호출자가 명시하며 프로세스 재시작 뒤 같은 파일을 열면 상태와 완료 report가 남아 있다.
- `complete_report()`는 검증된 `PatrolReportRecord`의 command ID와 robot ID가 저장된 command와 일치할 때만 canonical JSON으로 저장한다. `completed_report()`는 프로세스 재시작 뒤에도 이를 다시 검증해 같은 record로 복원한다. 다른 command·robot의 report가 연결되는 것을 막는다.
- `completed_reports()`는 Q-14 보존 범위의 완료 report 전체를 command 수신 순서로 복원한다. report ACK 계약이 없으므로 전송 완료로 표시하거나 삭제하지 않는다.
- command별 target 계약은 확정했다. START_PATROL은 robot별 default plan ID, DOCK은 robot별 dock ID를 요구하고 나머지는 빈 target ID를 요구한다. `target_pose`는 wire 호환을 위해 유지하지만 모든 명령에서 기본값만 허용한다. CommandCheck는 확정된 0~3 값을 사용한다.

~~~mermaid
flowchart TD
    OPEN[CommandStore: 명시 DB 경로·robot_id] --> DB[SQLite schema 생성 또는 기존 DB 재개]
    RX[register: MissionCommand payload + 수신 시각] --> VALID{고정 계약 필드와 JSON 유효?}
    VALID -->|아니오| BAD[ValueError / 저장 안 함]
    VALID -->|예| LOOKUP{command_id 존재?}
    LOOKUP -->|아니오·다른 robot| BADTARGET[거절 / 저장 안 함]
    LOOKUP -->|아니오·자기 robot| SAVE[ACCEPTED 원자 저장]
    LOOKUP -->|예| SAME{6개 충돌 필드 동일?}
    SAME -->|아니오| CONFLICT[COMMAND_ID_CONFLICT / 기존 행 유지]
    SAME -->|예·ACCEPTED| ACKA[DUPLICATE_ACCEPTED]
    SAME -->|예·EXECUTING| ACKE[DUPLICATE_EXECUTING]
    SAME -->|예·COMPLETED| REPORT[DUPLICATE_COMPLETED + 기존 report 반환]
    SAVE --> EXEC[mark_executing]
    EXEC --> DONE[complete: report ID + payload 영속 저장]
    DONE --> LINK{report command / robot ID 일치?}
    LINK -->|아니오| BADREPORT[거절 / 기존 command 유지]
    LINK -->|예| CODEC[canonical report JSON 저장]
    CODEC --> RESTORE[재시작 뒤 completed_report 검증 복원]
    RESTORE --> ALL[completed_reports: 보존 완료 report 순서 복원]
    PRUNE[prune] --> KEEP[24시간 이내 전부 + 오래된 최신 1000개 유지]
    DONE --> RESTART[프로세스 재시작]
    RESTART --> DB
~~~

검증: [단위시험](../tests/test_command_store.py) 17건은 enum, 신규·동일·충돌, ACCEPTED→EXECUTING→COMPLETED, 상태 역행 방지, 완료 report 재전달, 보존 report 전체의 순서 복원, DB 재개, report command/robot 연결과 재시작 복원, JSON/필드 검증, 다른 robot 차단, Q-14 경계와 1,000개 보존을 확인한다. mission ROS node와 확정된 CommandCheck 숫자를 붙인 뒤 IT-02를 통과해야 AMR-05 전체 완료다.

### 2.2 command_check.py — 구현 대조 완료 (순수 모듈)

`CheckStateMapping`은 v1.0의 UNKNOWN=0, ACCEPTED=1, EXECUTING=2, REJECTED=3을 사용한다. `CommandCheckFactory`는 robot/source session을 검증하고 sequence를 증가시키며, 잘못된 command의 빈 ID도 그대로 echo할 수 있다. `populate_message()`·`publish_record()`는 전체 wire 필드를 변환·발행하고 QoS는 RELIABLE·VOLATILE·KEEP_LAST(10)이다.

~~~mermaid
flowchart TD
    CFG[robot/source session] --> VALID{구조화 session ID 유효?}
    VALID -->|아니오| FAIL[생성 거절]
    VALID -->|예| FACTORY[고정 check_state 0~3 CommandCheckFactory]
    INPUT[command/mission ID + 의미 + reason] --> FACTORY
    FACTORY --> RECORD[CommandCheckRecord + sequence]
    RECORD --> MAP[전체 wire 필드 변환]
    MAP --> PUB[caller-owned publisher]
    PUB --> QOS[RELIABLE / VOLATILE / KEEP_LAST 10]
~~~

### 2.3 mission_ingress.py — 구현 대조 완료 (순수 모듈)

`mission_command_fields()`는 `MissionCommand`의 중복 fingerprint 필드와 `PoseStamped` 전체를 누락 없이 복사한다. `MissionIngress.observe()`는 `command_store` 결과를 신규 1회 dispatch, 기존 ACCEPTED/EXECUTING 재응답, 완료 report 재전달, ID 충돌 REJECTED로 변환한다. invalid/conflict reason code는 호출자가 확정 계약으로 주입하며 기본값이 없다. command별 실행은 상태 전이표가 미정이므로 이 모듈이 시작하지 않는다.

~~~mermaid
flowchart TD
    RX[MissionCommand wire 필드] --> COPY[PoseStamped 포함 fingerprint 복사]
    COPY --> STORE[CommandStore.register]
    STORE -->|NEW| ACCEPT[ACCEPTED + dispatch_new 1회]
    STORE -->|DUPLICATE_ACCEPTED| ACKA[ACCEPTED 재응답 / dispatch 없음]
    STORE -->|DUPLICATE_EXECUTING| ACKE[EXECUTING 재응답 / dispatch 없음]
    STORE -->|DUPLICATE_COMPLETED| REPORT[기존 PatrolReport 재전달]
    STORE -->|COMMAND_ID_CONFLICT| REJECT[REJECTED + 주입 reason code]
    STORE -->|입력 무효| INVALID[REJECTED + 주입 invalid code]
    ACCEPT --> PENDING[확정 전이표의 mission runtime]
~~~

2.2·2.3절 검증은 [CommandCheck 시험](../tests/test_command_check.py) 9건과 [ingress 시험](../tests/test_mission_ingress.py) 7건이다. 공유 계약 확정 요청은 [AMR 수정 요청서](change_requests/CR-AMR_09-08_11-48_명령_상태_보고_종단_계약.md)로 추적한다.

## 3. 로컬 안전과 속도 출력

local_safety_supervisor가 `/{robot}/cmd_vel`의 최종 속도 발행권을 가진다. Nav2나 yaw 정렬 기능이 안전 출력을 우회하지 않도록 한다. TBD-IF-009는 2026-09-08 결정됐으며 Nav2 `collision_monitor`의 `/{robot}/cmd_vel_safe`와 mission_supervisor의 `/{robot}/cmd_vel_yaw`는 `TwistStamped`, 최종 출력은 `Twist`를 사용한다. 두 후보 사이의 중재 정책은 TBD-AMR-001에 남아 있다.

- 유효하지 않은 token은 주행에 사용하지 않는다. 만료·회수 시 신규 주행을 막고 안전 정지한다.
- token의 `control_session_id`·`token_id`·`holder_robot_id`·`message_sequence`를 확인한다. 로컬 lease 경과는 Q-01을 따른다.
- 새 token만 수신했다고 임무를 자동 시작하지 않는다.
- E-stop 활성화는 즉시 반영한다. AMR은 관제가 발행한 대상별 대표 원인을 소비하며 별도 latch/reset을 두지 않는다.
- heartbeat는 5 Hz 입력을 받아 1초 초과 미수신 시 로컬 안전 정지한다. 새 control session이면 이전 token을 폐기한다.
- heartbeat·E-stop이 복구되어도 token과 별도 MissionCommand 없이 자동 재출발하지 않는다.

정지 감속 방식·허용 정지 거리·센서 장애에 대한 속도 출력 규칙은 TBD-AMR-006이다. 안전 정지 요청과 실제 정지 관측을 구분한다.

### 3.1 drive_token_guard.py — 구현 대조 완료

2026-09-07: 사용자 3단계 진행 요청에 따라 [drive_token_guard.py](../src/patrol_amr/patrol_amr/drive_token_guard.py)에 [인터페이스 3절](interfaces.md#3-drivetoken)의 수락 규칙과 Q-01 로컬 lease를 구현했다. ROS 노드가 아니라 6단계 `local_safety_supervisor`가 사용하는 일반 Python 모듈이며, 이 파일은 속도를 발행하지 않는다.

- `DriveTokenGuard.observe(control_session_id, token_id, holder_robot_id, lease_seconds, message_sequence, now)`: 새 [인터페이스 3절](interfaces.md#3-drivetoken)의 이름으로 관측 하나를 적용한다. `token_id`가 빈 문자열이면 지정 holder의 회수이며, `now`는 호출자가 전달하는 로컬 monotonic 초다.
- `message_sequence` 하한은 `control_session_id` 단위다. 같은 관제 세션에서는 token ID가 바뀌어도 하한을 유지하고 역행·중복을 `STALE_MESSAGE_SEQUENCE`로 폐기한다. 관제 세션이 바뀌면 이전 token을 무효화하고 하한을 새로 시작하며, 이미 종료된 세션이 다시 오면 `STALE_CONTROL_SESSION`으로 폐기한다. 앞선 message sequence로 다른 holder가 지정되면 `HOLDER_CHANGED`로 자기 권한을 즉시 끊고, 같은 메시지의 재수신은 `OTHER_HOLDER`로 폐기한다.
- 폐기된 메시지는 lease 만료 시각을 바꾸지 않는다. 수신 사실만으로 lease를 연장하지 않는다는 3절 규칙을 이렇게 만족한다. 갱신은 수락된 관측에서만 일어난다.
- `DriveTokenGuard.authority(now)`: 보유 token이 없으면 `MISSING`, lease 경과면 `EXPIRED`, 그 밖에는 `GRANTED`다. 각각 [인터페이스 5절](interfaces.md#5-patrolreport)의 600 DRIVE_TOKEN_MISSING과 601 DRIVE_TOKEN_EXPIRED에 대응한다. 공용 코드 목록에 회수 전용 값이 없으므로 회수도 `MISSING`이며, AMR 내부 `DRIVE_TOKEN_REVOKED` 로그는 `revoked_last`로 구분한다.
- `authority`·`remaining_lease`·`drive_allowed`는 조회 전용이라 시각을 소비하지 않는다. 한 제어 주기 안에서 같은 시각을 여러 번, 임의 순서로 물어볼 수 있다. 시계 역행 검사는 상태를 바꾸는 `observe`에만 적용한다.
- `duration_to_seconds(sec, nanosec)`는 `builtin_interfaces/Duration` 필드 쌍을 초로 바꾼다. lease 값은 메시지의 `lease_duration`을 사용하며 Q-01의 1.0초는 관제 발행 기준값이다.
- 주행 허용 여부만 보고하고 주행을 시작하지 않는다. 새 token 수신만으로 자동 출발하지 않는다는 3절 규칙은 6단계 supervisor가 최종 보장한다.
- `header.stamp` 기반 message age 검증은 TBD-IF-002의 남은 항목이라 구현하지 않았다. 로컬 lease는 monotonic clock으로만 측정하며 DDS lifespan과 구분한다.

**구현 대조 완료** — 2026-09-07 현재 코드 기준. 패키지 실행 등록은 9단계에서 추가한다.

~~~mermaid
flowchart TD
    MSG[drive_token 관측 / observe] --> SES{새 control_session_id?}
    SES -->|예| OLD{이미 종료된 control session?}
    OLD -->|예| SOLD[STALE_CONTROL_SESSION 폐기]
    OLD -->|아니오| RESET[이전 token 무효화 + sequence 하한 초기화]
    SES -->|아니오| EP
    RESET --> EP{message_sequence 가 하한 이하?}
    EP -->|예| WHO{holder 가 자신?}
    WHO -->|예| STL[STALE_MESSAGE_SEQUENCE 폐기 / 상태 불변]
    WHO -->|아니오| OTH[OTHER_HOLDER 폐기 / 상태 불변]
    EP -->|아니오| SET[control session의 sequence 하한 갱신]
    SET --> H{holder_robot_id 일치?}
    H -->|아니오| HC[HOLDER_CHANGED / 자기 권한 즉시 무효화]
    H -->|예| EMP{token_id 빈 문자열?}
    EMP -->|예| REV[REVOKED / 즉시 무효화 / revoked_last 설정]
    EMP -->|아니오| CHG{보유 token_id와 다른가?}
    CHG -->|예| INV[기존 token 즉시 무효화]
    CHG -->|아니오| LS
    INV --> LS{lease 가 유한한 양수?}
    LS -->|아니오| BAD[INVALID_LEASE 폐기 / 권한 없음]
    LS -->|예| ACC[ACCEPTED / lease 만료 시각 갱신]
    Q[제어 주기 조회 / authority] --> HAS{보유 token 있음?}
    HAS -->|아니오| MIS[MISSING / 600 DRIVE_TOKEN_MISSING]
    HAS -->|예| EXP{만료 시각 도달?}
    EXP -->|예| EXD[EXPIRED / 601 DRIVE_TOKEN_EXPIRED]
    EXP -->|아니오| GRA[GRANTED / 주행 허용]
~~~

검증: [단위시험](../tests/test_drive_token_guard.py)은 lease 경계와 갱신, 폐기 메시지의 lease 미연장, 같은 control session의 역행 message sequence 폐기, 새 control session의 sequence 재시작·기존 token 교체, holder 교대·회수, uint64 경계와 호출자 오류를 확인한다. 실행 명령은 저장소 루트에서 `python3 -m unittest discover -s tests -p test_drive_token_guard.py -v`다. [IT-03·IT-04](integration.md#4-통합시험-명세)의 로컬 판정 부분이며 관제 연동 통합시험은 미실행이다.

### 3.2 estop_guard.py — 구현 대조 완료

2026-09-07: 사용자 4단계 진행 요청에 따라 [estop_guard.py](../src/patrol_amr/patrol_amr/estop_guard.py)에 `/control/estop`의 반영 규칙을 구현했다. [3.1절](#31-drive_token_guardpy--구현-대조-완료)의 `drive_token_guard.py`와 같이 ROS 노드가 아니라 6단계 `local_safety_supervisor`가 사용하는 일반 Python 모듈이며 속도를 발행하지 않는다.

- `EStopGuard(robot_id)`는 어느 로봇의 상태인지 명시한다. `observe(target_robot_id, active, reason, sequence)`는 [인터페이스 3.1절](interfaces.md#31-heartbeat와-e-stop)의 필드명을 그대로 사용하고 `ACCEPTED`·`OTHER_TARGET`·`STALE_SEQUENCE`를 반환한다.
- `active`는 즉시 반영한다. 자동 해제 조건 3초 연속 판정과 활성 원인 집합·대표 원인 선택은 관제(Safety Arbiter)가 담당하므로 AMR은 로컬 해제 타이머나 별도 latch를 두지 않는다.
- 관측 전 기본 상태는 정지(`stopped=True`)다. `battery_monitor`의 초기 UNKNOWN, `DriveTokenGuard`의 초기 MISSING과 같은 안전 기본값이다.
- `reason`은 확정된 0~6만 수락하고 관제가 선택한 대표 원인 하나를 저장한다.
- 공통 토픽에서 `robot1`, `robot6`, `all` 중 자신의 대상과 `all`만 상태에 적용한다. 다른 대상은 sequence 하한만 갱신하고 `OTHER_TARGET`을 반환한다.
- `observe()`는 로그 이름을 반환하지 않는다. 호출자가 호출 전후로 `.stopped`를 비교해 상태 전이를 판정한다. 모듈은 `EVENT_ACTIVATED`·`EVENT_AUTO_RELEASED` 문자열만 정의해 둔다.

**구현 대조 완료** — 2026-09-07 현재 코드 기준. 패키지 실행 등록은 9단계에서 추가한다.

~~~mermaid
flowchart TD
    MSG[estop 관측 / observe] --> SEQ{sequence 가 마지막 수락 값 초과 또는 최초?}
    SEQ -->|아니오| STL[STALE_SEQUENCE 폐기 / 상태 불변]
    SEQ -->|예| SET[공통 stream sequence 하한 갱신]
    SET --> TARGET{target_robot_id 가 자신 또는 all?}
    TARGET -->|아니오| OTHER[OTHER_TARGET / 상태 불변]
    TARGET -->|예| ACC[active·대표 reason 반영 / ACCEPTED]
    ACC --> STOPPED[stopped = active]
    Q[호출자: observe 전후 stopped 비교] --> T1{False → True?}
    T1 -->|예| EA[EVENT_ACTIVATED 로그]
    T1 -->|아니오| T2{True → False?}
    T2 -->|예| ER[EVENT_AUTO_RELEASED 로그]
~~~

검증: [단위시험](../tests/test_estop_guard.py)은 관측 전 안전 기본값, 자기 대상과 `all`의 active·대표 reason 반영, 다른 로봇 대상 미적용, sequence 역행·중복 폐기, reason 0~6과 uint64 경계를 확인한다. 실행 명령은 저장소 루트에서 `python3 -m unittest discover -s tests -p test_estop_guard.py -v`다. [IT-11](integration.md#4-통합시험-명세)의 로컬 반영 부분이며 관제 연동과 물리 버튼 실기 시험은 미실행이다.

### 3.3 motion_guard.py — 구현 대조 완료

2026-09-07: 사용자가 5단계 범위를 확인 질문 후 축소 승인해 [motion_guard.py](../src/patrol_amr/patrol_amr/motion_guard.py)에 이미 확정된 두 규칙만 결합하는 최종 출력 게이트를 구현했다. [3.1](#31-drive_token_guardpy--구현-대조-완료)·[3.2절](#32-estop_guardpy--구현-대조-완료)과 같이 ROS 노드가 아닌 일반 Python 모듈이며 6단계 `local_safety_supervisor`가 사용한다.

원래 파일명이 함의하는 범위(장애물 회피·정지 거리·감속)는 TBD-AMR-006이 "로컬 정지 감속·거리·장애물 및 센서 실패 판정"으로 전부 미정으로 남긴 부분이다. Nav2 후보와 yaw 정렬 후보 사이의 선택은 TBD-AMR-001 "주행 중재"도 미정이다. 두 TBD 모두 실제 로봇 동역학·센서 사양이 필요해 이 저장소의 문서만으로는 근거 없이 숫자를 정할 수 없었다. 사용자에게 확인한 뒤 범위를 좁혀, 이미 문장으로 확정된 것만 구현했다.

- `MotionGuard.evaluate(drive_token_granted, estop_active, candidate, candidate_age)`: `candidate`는 이미 상류에서 결정된(TBD-AMR-001) `(linear, angular)` 실수 쌍이거나, 아직 후보를 받지 못했으면 `None`이다. TBD-IF-009가 2026-09-08 확정됐지만 이 모듈은 계속 ROS 타입을 쓰지 않는다 — 순수 튜플과 초 단위 실수만 다루고, 실제 `TwistStamped`↔`Twist` 변환은 12단계 `local_safety_supervisor`가 한다.
- 3절의 두 확정 문장을 AND로 결합한다 — "유효하지 않은 token은 주행에 사용하지 않는다... 안전 정지한다"(token 미부여), "E-stop 활성화는 즉시 반영한다"(E-stop 활성). 둘 중 하나라도 해당하면 `candidate`를 버리고 `STOP = (0.0, 0.0)`을 반환한다. 둘 다 아니면 `candidate`를 그대로 통과시킨다 — 속도 제한·형태 변형은 하지 않는다.
- 차단 사유는 `MotionBlockReason`으로 전부 보고한다(하나 또는 둘 다). 동시에 여러 사유가 있을 때 어느 것을 "그" 사유로 볼지 우선순위를 정한 문서가 없어 하나를 고르지 않았다. 출력(STOP)은 사유 개수와 무관하다.
- 상태를 두지 않는다. 매 호출이 독립적이며, 3·4단계 가드의 현재 판정을 매 제어 주기마다 그대로 전달받는다. `candidate_age`도 호출자가 재어 넘기므로 이 모듈에는 시계가 없다.

**11단계 추가 — Q-17 후보 신선도(2026-09-08).** [TBD-IF-009 요청서](change_requests/CR-AMR_09-08_08-31_최종_cmd_vel_경로와_주행_후보_토픽.md)에서 확정한 0.5초를 `CANDIDATE_MAX_AGE_SECONDS`로 두고 판정한다.

- 게이트를 두 개로 나눴다. `blocked_reasons(drive_token_granted, estop_active)`는 **권한** 게이트로 token·E-stop만 보고, `evaluate()`는 **출력** 게이트로 여기에 후보 유무·신선도를 더한다. Nav2가 후보를 내고 있는지는 주행이 허용되는지와 다른 질문이므로 합치지 않았다. 덕분에 6단계 `motion_allowed`는 후보 유무에 흔들리지 않고 기존 동작을 그대로 유지한다.
- 사유를 둘로 구분한다. `CANDIDATE_MISSING`은 후보를 한 번도 못 받은 상태, `CANDIDATE_STALE`은 받았으나 age가 0.5초를 넘은 상태다. Nav2가 아직 안 뜬 것과 떠 있는데 늦는 것은 운영자가 볼 때 원인이 다르다. 출력은 두 경우 모두 `STOP`이다.
- 경계는 `age > 0.5`가 낡음이다. Q-17이 "0.5초를 넘으면"이므로 0.5초 정확히는 통과한다.
- 음수 age(후보 stamp가 미래)는 낡음으로 보지 않는다. 후보와 이 게이트는 같은 AMR PC의 같은 시계를 쓰고, 허용 가능한 시계 역행 폭을 정한 문서가 없어 임의 임계값을 만들지 않았다.
- `candidate`와 `candidate_age`는 짝으로만 받는다. 한쪽만 `None`이면 `ValueError`다. 어느 후보의 신선도인지 말하지 않고 물어볼 수 없게 했다.

**TBD-AMR-001·006으로 남긴 부분** — 추측해 구현하지 않았다.

- Nav2·yaw 후보 중 선택(주행 중재)은 이 모듈에 없다. `candidate` 하나만 받는다.
- 장애물 감지·정지 거리·감속 프로파일·센서 고장 시 출력 규칙이 없다. 실제 로봇 사양이 정해지면 반영한다.
- 속도 상한·형태 clamp가 없다. `candidate`가 유한한 실수인지만 확인하고 크기는 검사하지 않는다.

TBD-IF-009는 2026-09-08 AMR이 확정해 더 이상 이 모듈의 미정 사항이 아니다. 다만 확정된 것은 토픽·타입·Q-17이고, 관제 회신은 아직 대기 중이다.

**구현 대조 완료** — 2026-09-08 현재 코드 기준. 패키지 실행 등록은 9단계에서 추가했다.

~~~mermaid
flowchart TD
    IN[evaluate 호출 / drive_token_granted, estop_active, candidate, candidate_age] --> V{인자 유효?}
    V -->|아니오| ERR[ValueError]
    V -->|예| D{drive_token_granted?}
    D -->|아니오| R1[DRIVE_TOKEN_NOT_GRANTED 추가]
    D -->|예| E
    R1 --> E{estop_active?}
    E -->|예| R2[ESTOP_ACTIVE 추가]
    E -->|아니오| C
    R2 --> C{candidate 있음?}
    C -->|아니오| R3[CANDIDATE_MISSING 추가]
    C -->|예| A{age > 0.5초?}
    A -->|예| R4[CANDIDATE_STALE 추가]
    A -->|아니오| CHK
    R3 --> CHK{사유 있음?}
    R4 --> CHK
    CHK -->|예| STOP[STOP = 0,0 반환 / 사유 전체 반환]
    CHK -->|아니오| PASS[candidate 그대로 반환 / 사유 없음]
~~~

`blocked_reasons()`는 위 흐름의 token·E-stop 두 분기까지만 본다. 후보 분기는 `evaluate()`에만 있다.

검증: [단위시험](../tests/test_motion_guard.py) 26건은 두 조건의 AND 게이트(정상·각 단독 차단·동시 차단·세 사유 동시), STOP 값의 정확성, candidate 그대로 통과, 상태 비저장(연속 호출 간 사유 미잔존), 호출자 인자 오류를 확인한다. Q-17은 경계값 0.499·0.5·0.501초, 후보 없음과 낡음의 사유 구분, 미래 stamp 통과, 권한 게이트가 후보 유무에 영향받지 않음, `candidate`·`candidate_age` 짝 강제를 확인한다. 실행 명령은 저장소 루트에서 `python3 -m unittest discover -s tests -p test_motion_guard.py -v`다. 실제 장애물·로봇 동역학 시험은 TBD-AMR-006 해결과 로봇 실기 이후로 남는다.

### 3.4 local_safety_supervisor.py — 구현 대조 완료

2026-09-07: 사용자가 6단계 진행을 요청하기 전 5단계와 같은 이유로 범위를 확인했다. [local_safety_supervisor.py](../src/patrol_amr/patrol_amr/local_safety_supervisor.py)는 3~5단계에서 만든 세 가드를 실제 ROS 노드로 묶은 첫 지점이며, [3.1](#31-drive_token_guardpy--구현-대조-완료)~[3.3절](#33-motion_guardpy--구현-대조-완료)과 달리 `battery_monitor`(5.1절)처럼 진짜 ROS 노드다.

**구현한 것** — `/control/drive_token`·`/control/heartbeat`·`/control/estop`을 실제로 구독해 세 가드에 반영하고, 결합 결과를 AMR 내부 신호 `motion_allowed`(`std_msgs/Bool`)와 `safety_state`(`std_msgs/UInt8`)로 발행한다. `battery_status`(5.1절)와 같은 성격의 내부 연결이며 공용 인터페이스를 추가한 것이 아니다.

- `SafetyGate`: ROS에 의존하지 않는 순수 조합 클래스. `DriveTokenGuard`·`HeartbeatGuard`·`EStopGuard`·`MotionGuard`를 묶는다. heartbeat가 새 control session을 수락하면 이전 token을 폐기하며, `blocked_reasons(now)`/`motion_allowed(now)`가 세 권한 조건을 결합한다.
- `estop_transition_event(previous_stopped, current_stopped, verdict)`: 수락된 E-stop 관측이 활성에서 해제로 전이했을 때 기존 안전 로그 이름 `E_STOP_AUTO_RELEASED`를 선택한다. `local_safety_supervisor._on_estop()`은 `robot_id`·`target_robot_id`·`sequence`와 함께 이 로그를 남긴다. 최종 `motion_allowed`가 token 부재 때문에 계속 `false`여도 E-stop 해제 반영 자체를 확인할 수 있다.
- 신선도 재확인 타이머(0.1초)가 새 메시지 없이도 drive token lease와 heartbeat 1초 timeout을 다시 계산해 `motion_allowed`·`safety_state`·최종 속도를 갱신한다. E-stop은 lease 없이 마지막 관제 상태를 유지한다.
- QoS: drive_token 구독은 9절의 BEST_EFFORT・VOLATILE・KEEP_LAST(3)만 요청하고 deadline은 요청하지 않는다. 처음에는 9절의 "deadline 200ms"까지 구독측에 걸었으나, 사용자 시험 중 DDS 계층에서 실제로 막히는 것을 발견했다 — RxO 호환 규칙상 미지정 offered deadline은 무한대로 취급되어, deadline을 명시하지 않는 발행자(`ros2 topic pub` 포함)의 메시지가 전혀 도달하지 않는다("Last incompatible policy: DEADLINE"). 9절의 deadline·lifespan 값은 실제 발행자(관제)가 지켜야 할 발행 주기·보관 기한 설명으로 재해석했다. 신선도(끊김 감지)는 이미 구현된 Q-01 lease 만료(`DriveTokenGuard.authority`, 애플리케이션 계층)가 담당하므로 DDS deadline 없이도 안전 방향은 유지된다. estop은 9절이 "단일 상태, 정확한 depth TBD"로 남겨, RELIABLE・TRANSIENT_LOCAL은 그대로 따르고 depth=1만 이 노드(구독측)의 로컬 선택으로 채웠다 — 공용 계약을 확정한 것이 아니다. TRANSIENT_LOCAL 요구 때문에 `ros2 topic pub`으로 시험할 때는 `--qos-durability transient_local --qos-reliability reliable`을 함께 줘야 한다(기본값은 VOLATILE이라 그냥 두면 "Last incompatible policy: DURABILITY"로 막힌다 — 의도된 동작이며, 계약과 다른 durability의 발행자를 실제로 걸러낸다). `motion_allowed`는 `battery_status`와 같은 RELIABLE・TRANSIENT_LOCAL・KEEP_LAST(1)이다.
- `robot_id`는 필수 ROS parameter다(`--ros-args -p robot_id:=robot1` 또는 `robot6`). 기본값을 두지 않고 미지정·오지정 시 노드 시작을 막는다 — 잘못된 기본값으로 다른 로봇의 token을 조용히 받아들이는 위험을 피했다.

**12단계 추가 — 최종 속도 출력(2026-09-08).** TBD-IF-009 확정으로 이 노드가 interfaces.md 7절의 "유일한 최종 발행자" 역할을 실제로 수행한다.

- **입력** `cmd_vel_safe`(`geometry_msgs/TwistStamped`) 하나만 구독한다. Nav2 표준 체인의 `collision_monitor` 출력을 여기로 돌린 것이다. `cmd_vel_yaw`는 계약에만 예약하고 구독하지 않는다 — 두 후보 중 선택은 주행 중재(TBD-AMR-001)이고 `mission_supervisor` 담당이라 이 범위 밖이다. 후보 하나 들어오고 출력 하나 나간다.
- **출력** `cmd_vel`(`geometry_msgs/Twist`). 구동부 `diffdrive_controller`가 `use_stamped_vel: false`이므로 stamp를 떼고 내보낸다. 후보에 stamp가 필요한 이유는 Q-17 판정뿐이다.
- 토픽 이름은 모두 상대 이름이다. `/robot1`·`/robot6` namespace 아래에서 실행하면 architecture.md 2절이 요구하는 로봇별 토픽이 된다. launch 배선은 13단계다.
- **두 시계를 분리해서 넘긴다.** Q-01 lease는 `time.monotonic()`(벽시계 점프에 영향받지 않음), Q-17 후보 age는 후보의 ROS stamp와 같은 `get_clock()`으로 잰다. `SafetyGate.output(monotonic_now, ros_now)`가 둘을 따로 받으므로 이 클래스는 여전히 ROS에 의존하지 않는다.
- **발행 시점** — 후보를 수락할 때마다 발행하고(후보 자체 주기를 그대로 따라 지연을 더하지 않는다), 차단 상태에서는 0.1초 재확인 타이머가 매 주기 STOP을 다시 낸다. 정지한 로봇은 스트림이 끊기는 대신 명시적인 0을 계속 받아야 한다. 통과 중일 때는 후보 스트림이 이미 발행하므로 타이머가 중복 발행하지 않는다.
- E-stop·token 콜백도 차단 시 즉시 발행한다. amr.md 3절의 "E-stop 활성화는 즉시 반영한다"를 재확인 타이머까지 기다리지 않고 지킨다.
- **유한하지 않은 후보는 폐기한다.** 콜백에서 예외를 던지면 로봇을 세우고 있는 유일한 노드가 죽으므로 raise하지 않고 그 표본만 버린다. 이전 후보가 남아 Q-17로 만료되므로 실패 방향은 STOP이다.
- QoS는 `RELIABLE`・`VOLATILE`・`KEEP_LAST(1)`이다. 속도는 최신 표본만 의미가 있어 depth 1이고, 지난 값을 늦게 받으면 위험하므로 `TRANSIENT_LOCAL`을 쓰지 않는다. drive_token에서 겪은 것과 같은 이유로 구독측에 deadline·lifespan을 요청하지 않는다. Nav2 `TwistPublisher` 기본값과 호환된다.

`motion_allowed`는 6단계 그대로다. 권한 게이트(token·E-stop)만 반영하고 후보 유무에 흔들리지 않는다 — 후보가 없는 것은 주행 권한이 없다는 뜻이 아니다.

**16단계 추가 — accepted token 상태 연결(2026-09-08).** `SafetyGate.token_status(now)`가 Q-01 lease까지 반영한 현재 token을 `(accepted_token_id, token_valid)`로 한 번에 계산한다. 노드는 이를 상대 내부 토픽 `accepted_token_id`(`std_msgs/String`, RELIABLE・TRANSIENT_LOCAL・KEEP_LAST(1))로 발행한다. 비어 있지 않은 값은 해당 ID가 현재 유효하다는 뜻이고, 미수신·만료·회수·다른 holder는 빈 문자열이다. ID와 bool을 독립 토픽으로 보내 시점이 섞이는 일을 피했으며 공용 메시지 계약은 추가하지 않았다. 최초 상태와 token 콜백 직후, 0.1초 재확인에서 값이 달라질 때만 발행하므로 새 메시지 없이 lease가 만료되어도 빈 값으로 돌아간다.

**TBD-AMR-001·006으로 남긴 부분** — 5단계와 같은 이유다.

- Nav2·yaw 후보 중재는 이 노드에 없다. 후보 토픽 하나만 구독한다.
- 속도 상한·clamp·감속 프로파일·장애물 판정이 없다. 통과가 허용된 후보는 변형 없이 그대로 나간다.

**구현 대조 완료** — 2026-09-08 현재 코드 기준. 패키지 실행 등록은 9단계에서 추가했다.

~~~mermaid
flowchart TD
    DT[/control/drive_token 콜백] --> OT[SafetyGate.observe_drive_token]
    HB[/control/heartbeat 콜백] --> OH[SafetyGate.observe_heartbeat]
    ES[/control/estop 콜백] --> PRE[이전 estop stopped 저장]
    PRE --> OE[SafetyGate.observe_estop]
    OE --> REL{ACCEPTED이고 True → False?}
    REL -->|예| RLOG[E_STOP_AUTO_RELEASED 로그]
    REL -->|아니오| PUB
    RLOG --> PUB
    TIMER[0.1초 재확인 타이머] --> PUB
    OT --> PUB[_publish_if_changed]
    OH --> PUB
    OT --> TOK[SafetyGate.token_status now]
    OH --> TOK
    TIMER --> TOK
    TOK --> TV{accepted token ID가 바뀜?}
    TV -->|예| TP[accepted_token_id 내부 토픽 발행]
    TV -->|아니오| TSKIP[발행 생략]
    PUB --> BR[SafetyGate.blocked_reasons now]
    BR --> H{heartbeat HEALTHY?}
    H -->|아니오| RH[HEARTBEAT_NOT_HEALTHY]
    H -->|예| D{drive_token GRANTED?}
    RH --> D
    D -->|아니오| R1[DRIVE_TOKEN_NOT_GRANTED]
    D -->|예| E
    R1 --> E{estop stopped?}
    E -->|예| R2[ESTOP_ACTIVE]
    E -->|아니오| CHK
    R2 --> CHK{allowed 값이 이전과 다름?}
    CHK -->|아니오| SKIP[발행 생략]
    CHK -->|예| MA[motion_allowed·safety_state 발행 + 로그]
~~~

최종 속도 경로는 위 권한 경로와 별개다. 12단계에서 추가한 부분이다.

~~~mermaid
flowchart TD
    CAND[cmd_vel_safe 콜백] --> FIN{유한한 값?}
    FIN -->|아니오| DROP[표본 폐기 / 경고 로그]
    FIN -->|예| OC[SafetyGate.observe_candidate]
    OC --> PO[_publish_output always=true]
    TIMER2[0.1초 재확인 타이머] --> PO2[_publish_output always=false]
    DT2[drive_token / heartbeat / estop 콜백] --> PO2
    PO --> EV[SafetyGate.output monotonic_now, ros_now]
    PO2 --> EV
    EV --> GA{heartbeat HEALTHY / token GRANTED / estop 해제?}
    GA -->|아니오| RS[권한 사유 추가]
    GA -->|예| CA
    RS --> CA{후보 있음?}
    CA -->|아니오| RM[CANDIDATE_MISSING]
    CA -->|예| AG{ros_now - stamp 가 0.5초 초과?}
    AG -->|예| RT[CANDIDATE_STALE]
    AG -->|아니오| DEC
    RM --> DEC{사유 있음?}
    RT --> DEC
    DEC -->|예| STOPV[cmd_vel = 0,0 발행]
    DEC -->|아니오| PASSV{always=true?}
    PASSV -->|예| SEND[cmd_vel = 후보 그대로 발행]
    PASSV -->|아니오| SKIPV[발행 생략 / 후보 스트림이 담당]
~~~

검증: [단위시험](../tests/test_local_safety_supervisor.py) 31건은 관측 전 기본 차단, 두 가드의 AND 결합, drive_token lease 만료·갱신, 다른 로봇 token·역순 estop 폐기, 후보 신선도와 최종 출력, 그리고 16단계의 token 미수신·수락·만료·회수·다른 holder 상태를 확인한다. 실행 명령은 저장소 루트에서 `python3 -m unittest discover -s tests -p test_local_safety_supervisor.py -v`다. 실제 토픽 시험 순서는 [인수인계 16단계](development/amr-workspace-handoff.md)에 있다.

### 3.5 heartbeat_guard.py — 구현 대조 완료 (순수 모듈)

2026-09-08: [heartbeat_guard.py](../src/patrol_amr/patrol_amr/heartbeat_guard.py)에 확정 계약을 구현하고 `local_safety_supervisor`의 `/control/heartbeat` subscriber와 최종 속도 게이트에 연결했다.

- `HeartbeatGuard.observe(control_session_id, sequence, now)`는 비어 있지 않은 관제 session과 1 이상 uint64 sequence를 검증한다. 같은 session의 중복·역순 sequence는 폐기하며 마지막 수락 시각을 갱신하지 않는다.
- 새 control session은 sequence 하한을 다시 1부터 받을 수 있고 이전 session을 retire한다. retire된 session이 늦게 도착해도 현재 session이나 신선도를 되돌리지 않는다.
- `state(now)`는 수락 heartbeat가 없으면 MISSING, 마지막 수락 후 1.0초 이하면 HEALTHY, **1.0초를 초과하면** EXPIRED다. 업무표 문구와 Q-16의 “1초 초과” 경계를 그대로 사용한다.
- 경과는 AMR의 local monotonic 시각만 사용하고 시계 역행·NaN·무한대를 거절한다. header timestamp와 서로 다른 PC의 시계를 timeout 측정에 섞지 않는다.
- heartbeat 복구만으로 mission을 재개하는 기능은 없다. 이 guard가 HEALTHY로 돌아오는 것과 재출발 허가는 별개이며, 실제 재개는 관제 command와 AMR-18·19 조건을 모두 통과해야 한다.

~~~mermaid
flowchart TD
    INIT[HeartbeatGuard 생성] --> MISS[MISSING / 주행 허용 근거 없음]
    HB[observe: control_session_id / sequence / monotonic now] --> VALID{필드와 시각 유효?}
    VALID -->|아니오| ERROR[ValueError / 상태 유지]
    VALID -->|예| RETIRED{retire된 session?}
    RETIRED -->|예| OLD[STALE_CONTROL_SESSION / 시각 갱신 안 함]
    RETIRED -->|아니오| SESSION{새 session?}
    SESSION -->|예| SWITCH[기존 session retire / sequence 하한 초기화]
    SESSION -->|아니오| SEQ
    SWITCH --> SEQ{sequence가 직전보다 큼?}
    SEQ -->|아니오| STALE[STALE_SEQUENCE / 시각 갱신 안 함]
    SEQ -->|예| ACCEPT[ACCEPTED / 마지막 수신 시각 갱신]
    TIMER[state now] --> HAVE{수락 heartbeat 있음?}
    HAVE -->|아니오| MISS
    HAVE -->|예| AGE{age > 1.0초?}
    AGE -->|아니오| HEALTHY[HEALTHY]
    AGE -->|예| EXPIRED[EXPIRED / 로컬 안전 정지 요구]
    HEALTHY --> WAITCMD[복구만으로 자동 재출발 금지]
~~~

검증 기록: 단위시험은 MISSING 기본값, 1.0초 경계와 초과, 정상 갱신, 중복·역순이 timeout을 연장하지 않음, session 교체·이전 token 폐기, uint64·시각·시계 역행을 확인한다. 실제 관제 연동 IT-10은 배포 환경에서 수행한다.

## 4. Nav2·위치·Keepout

map frame의 pose·측정 시각·covariance를 제공한다. pose가 무효이면 마지막 유효 위치를 보존하되 현재 위치로 사용하지 않는다. 참고 위치 검증과 실제 주행 재개 기준은 Q-06과 Q-05로 구분한다.

AMR2 LiDAR 위치 검증 기준은 Q-06이며 대상·계산 주체·통신 계약이 불명확하다(TBD-AMR-002). 이를 두 로봇에 임의로 일반화하지 않는다.

Keepout은 각 로봇의 global/local costmap에 필요하다. 단일 filter 구성 예시는 다음과 같다.

~~~yaml
filters: ["keepout_filter"]
keepout_filter:
  plugin: "nav2_costmap_2d::KeepoutFilter"
  enabled: true
  filter_info_topic: costmap_filter_info
~~~

mask server와 costmap_filter_info_server도 필요하다. 아래 4.4절에서 사용자 승인 범위의 이중 filter를 실제 AMR overlay와 launch에 반영했다. 관제 transaction과 정식 공유 parameter 계약은 [AMR 이중 Keepout 요청서](change_requests/CR-AMR_09-08_13-02_이중_Keepout_parameter_계약.md) 검토 및 TBD-IF-008 완료가 필요하다.

안전구역은 Q-08 조건을 모두 충족해야 한다. 차량 동선과의 거리를 우선하고 다음으로 경로 비용을 평가한다. 후보가 없으면 현재 위치에서 정지하고 SAFE_ZONE_NOT_FOUND를 보고한다. 계산 주체·지도/차량 동선 공급자는 TBD-CTRL-002다.

### 4.1 safe_zone_selector.py — 구현 대조 완료 (좌표 비의존 판정기)

2026-09-08: 저장소에 실제 map YAML/이미지, Keepout mask, P1~P7·도크·안전구역 좌표가 없음을 확인했다. [safe_zone_selector.py](../src/patrol_amr/patrol_amr/safe_zone_selector.py)는 좌표를 추정하거나 map을 만들지 않고 외부 map·traffic provider가 제공한 후보를 Q-08로만 판정한다.

- `MapPose`는 유한한 x·y·yaw와 frame을 보존한다. 선택 대상은 `map` frame만 통과한다.
- `rejection_reasons()`는 free cell, Keepout 밖, 장애물 간격 0.5 m 이상, 차량 동선 간격 1.0 m 이상, 경로 가능, 다른 AMR과 비중첩을 독립적으로 검증한다.
- `select_safe_zone()`는 적합 후보만 차량 동선 거리 내림차순, 경로 비용 오름차순, candidate ID 순으로 정렬해 결정성있게 하나를 고른다. 적합 후보가 없으면 pose를 추정하지 않고 `SAFE_ZONE_NOT_FOUND=400`을 반환한다.

~~~mermaid
flowchart TD
    INPUT[map/traffic provider의 후보 목록] --> VALID{후보 ID·pose·거리 유효?}
    VALID -->|아니오| ERROR[입력 거절]
    VALID -->|예| FRAME{map frame?}
    FRAME --> GATES{free + Keepout 밖 + 0.5m + 1.0m + path + 비중첩?}
    GATES -->|아니오| DROP[후보 제외 + 모든 사유 보존]
    GATES -->|예| ELIGIBLE[적합 후보]
    ELIGIBLE --> RANK[차량 거리 우선 → 경로 비용 → ID]
    RANK --> SELECT[최종 후보]
    DROP --> NONE{적합 후보 0개?}
    NONE -->|예| FAIL[SAFE_ZONE_NOT_FOUND / pose 없음]
~~~

검증은 [safe-zone 단위시험](../tests/test_safe_zone_selector.py)에서 Q-08 경계, 7개 부적합 사유, 우선순위, 무후보 실패, 중복 ID·비유한 입력 차단을 확인한다. 실제 map·mask·Nav2 path 연결은 자료 제공과 TBD-CTRL-002·TBD-INT-003 확정 후에만 구현한다.

### 4.2 waypoint_catalog.py — 구현 대조 완료

2026-09-08 사용자가 제공한 `final_project_map` 원본과 실측 WP1~WP7을 [maps](../src/patrol_amr/maps)와 [patrol_waypoints.yaml](../src/patrol_amr/config/patrol_waypoints.yaml)에 보존했다. 원본과 패키지 PGM의 SHA-256은 모두 `c07df922bb4b520f9a20a9098a507786eb790646d51c98d95443f19e02efa1e6`이다. map은 126×90 px, 0.05 m/px, origin `[-5.801, -3.430, 0]`이다. 7개 waypoint와 8개 Keepout 경계점은 모두 map 범위 안의 free pixel `gray(254)`임을 확인했다.

~~~mermaid
flowchart TD
    YAML[patrol_waypoints.yaml] --> LOAD[load_waypoint_catalog]
    LOAD --> META{map_id / frame_id=map?}
    META -->|아니오| FAIL[적재 거절]
    META -->|예| EACH[WP1~WP7 순서 로드]
    EACH --> VALID{ID 고유 + x/y 유한 + yaw 0~360?}
    VALID -->|아니오| FAIL
    VALID -->|예| CATALOG[불변 WaypointCatalog]
    CATALOG --> LOOKUP[by_id 조회]
~~~

### 4.3 keepout_mask.py — 구현 대조 완료

사용자 확인에 따라 빨간 기본 Keepout을 `P1-P2-P3-P4`·`P5-P6-P7-P8`, 노란 중앙통로 Keepout을 `P2-P5-P8-P3`으로 [keepout_zones.yaml](../src/patrol_amr/config/keepout_zones.yaml)에 분리했다. 기본 Keepout은 `always`, 중앙통로는 관제가 `/vision/cctv/patrol_allowed=false`를 받았을 때 활성화하는 `control_when_patrol_disallowed`로 표시했다. AMR이 CameraState나 permit을 직접 판단하지 않는다. `keepout_mask.py`는 polygon·map metadata를 검증하고 각 cell 중심을 world 좌표로 변환해 두 장의 map-aligned PGM을 생성한다. 검정 pixel은 occupied Keepout, 흰 pixel은 free다.

~~~mermaid
flowchart TD
    ZONES[keepout_zones.yaml] --> ZVALID{map frame / layer / polygon / 면적 유효?}
    MAP[final_project_map.yaml + PGM] --> MVALID{trinary / negate 0 / yaw 0 / 126x90?}
    ZVALID -->|아니오| FAIL[생성 거절]
    MVALID -->|아니오| FAIL
    ZVALID --> RASTER[cell 중심 world 좌표 변환]
    MVALID --> RASTER
    RASTER --> INSIDE{layer polygon 내부?}
    INSIDE -->|예| BLACK[검정 / occupied Keepout]
    INSIDE -->|아니오| WHITE[흰색 / free]
    BLACK --> BASE[base_keepout_mask.pgm]
    BLACK --> CENTER[center_corridor_keepout_mask.pgm]
    WHITE --> BASE
    WHITE --> CENTER
~~~

두 mask와 metadata는 `setup.py`로 package share에 설치된다. WP3은 중앙통로 mask 내부이고 기본 Keepout 밖이며, 나머지 WP는 두 mask 밖임을 자동시험으로 확인한다. 이는 중앙통로 Keepout이 활성인 동안 WP3를 경로에서 제외해야 한다는 통합 제약이며, 실제 filter 활성 정책과 방문 순서는 Nav2 연결 전에 확정한다.

검증: 전체 자동시험 `Ran 250 tests`/`OK`, `colcon build --packages-select patrol_interfaces patrol_amr` `2 packages finished`. 현재 결과는 map·waypoint·mask 자산과 순수 판정/생성 로직이므로 사용자 ROS 토픽 시험 대상은 아니다.

### 4.4 amr_nav2_keepout.launch.py — 구현 대조 완료

2026-09-08 사용자 승인에 따라 [nav2_keepout_filters.yaml](../src/patrol_amr/config/nav2_keepout_filters.yaml)을 기존 TurtleBot4 Nav2 parameter에 overlay하고 [amr_nav2_keepout.launch.py](../src/patrol_amr/launch/amr_nav2_keepout.launch.py)에서 localization·Nav2·이중 mask 서버를 함께 기동하도록 연결했다. `robot_id`는 `robot1` 또는 `robot6`만 허용하며 map·mask·filter info topic을 로봇 namespace 아래에 분리한다.

- global/local costmap 모두 `base_keepout_filter`와 `center_corridor_keepout_filter`를 로드한다.
- 빨간 기본 filter는 `enabled=true`, 노란 중앙통로 filter는 `enabled=false`로 시작한다.
- 관제가 변경할 대상은 중앙통로 filter 두 개뿐이다. AMR은 `/vision/cctv/patrol_allowed`를 직접 구독하거나 차량 상태를 재판단하지 않는다.
- mask topic은 filter info 메시지 안에서도 robot namespace를 잃지 않도록 절대 이름으로 전달한다.
- 네 mask/info lifecycle 노드는 전용 lifecycle manager가 함께 ACTIVE로 만든다.

~~~mermaid
flowchart TD
    START[amr_nav2_keepout.launch.py] --> ID{robot1 또는 robot6?}
    ID -->|아니오| REJECT[launch 인자 거절]
    ID -->|예| MAP[final_project_map으로 localization]
    ID --> SERVERS[base/center mask server + info server]
    ID --> OVERLAY[TurtleBot4 Nav2 params + Keepout overlay]
    SERVERS --> ACTIVE{4개 lifecycle ACTIVE?}
    OVERLAY --> GLOBAL[global_costmap: base ON + center OFF]
    OVERLAY --> LOCAL[local_costmap: base ON + center OFF]
    ACTIVE --> GLOBAL
    ACTIVE --> LOCAL
    CONTROL[관제 transaction] --> CENTER{patrol_allowed?}
    CENTER -->|false| ENABLE[global/local center enabled=true]
    CENTER -->|true| DISABLE[global/local center enabled=false]
    ENABLE --> READBACK{두 값 read-back 일치?}
    DISABLE --> READBACK
    READBACK -->|아니오| ROLLBACK[snapshot rollback 또는 안전 정지]
    READBACK -->|예| COMMIT[중앙통로 상태 commit]
    GLOBAL --> BASE[빨간 기본 Keepout 상시 유지]
    LOCAL --> BASE
~~~

관제 쪽 snapshot·Q-07 재시도·read-back·rollback은 AMR 책임 범위가 아니므로 해당 코드를 수정하지 않았다. 정식 parameter 이름과 적용 순서는 [CR-AMR_09-08_13-02](change_requests/CR-AMR_09-08_13-02_이중_Keepout_parameter_계약.md)에 제안했으며 합의·실기 전에는 AMR-09를 100%로 표시하지 않는다.

로컬 검증: 전체 단위시험 `Ran 255 tests`/`OK`, `colcon build --packages-select patrol_interfaces patrol_amr` `2 packages finished`, 설치된 launch의 `--show-args`에서 `robot1`·`robot6` 선택과 map/parameter 기본 경로를 확인했다. 실제 lifecycle ACTIVE, global/local parameter read-back, RViz costmap 및 WP3 경로 차단은 장비가 연결된 사용자 실기시험으로 남는다.

### 4.5 실제 mission Nav2 재시도·waypoint skip 경로 — 구현 대조 완료, 실기 대기

2026-09-08: 병합된 production 경로 `mission_supervisor → MissionWorker → MissionController → PatrolScenario → NavigationAdapter → Nav2GoalRunner → TurtleBot4Navigator`에 AMR-16 정책을 직접 연결했다. 별도 시험용 이동 경로나 비연결 Action client를 두지 않는다.

- [navigation_types.py](../src/patrol_amr/patrol_amr/navigation_types.py)의 `MAX_GOAL_RETRIES=3`이 공통 재시도 수다. [nav2_goal_runner.py](../src/patrol_amr/patrol_amr/nav2_goal_runner.py)는 최초 1회와 추가 3회, 총 최대 4번 `NavigateToPose`를 실행한다.
- 일반 Nav2 `FAILED`·`REJECTED`·알 수 없는 결과만 재시도한다. STOP/CANCEL, DriveToken 상실, `motion_allowed=false` 등 안전 취소는 `CANCELED`로 즉시 반환해 재시도하지 않는다.
- 실행 중 `TurtleBot4Navigator.getFeedback()`을 읽어 마지막 feedback을 보존한다.
- 실제 로봇에서 증거를 확인할 수 있도록 각 실패 시도·재시도와 네 번째
  실패 소진을 navigator ROS 로그에 남긴다.
- [scenarios/patrol.py](../src/patrol_amr/patrol_amr/scenarios/patrol.py)는 총 4회 실패한 중간 W1~W6의 checkpoint를 다음 index로 저장하고 다음 waypoint를 실행한다. 마지막 W7 실패는 skip하지 않고 route를 실패로 종료한다.
- 중간 skip 뒤 최종 PatrolReport에 어떤 상세를 남길지는 AMR-17의 TBD-AMR-005 잔여다. 현재 경로 실행은 계속하지만 report에 skip 사실이 포함됐다고 주장하지 않는다.

~~~mermaid
flowchart TD
    CMD[START_PATROL MissionCommand] --> WORKER[MissionWorker]
    WORKER --> PATROL[PatrolScenario W1~W7]
    PATROL --> SEND[Nav2GoalRunner / NavigateToPose 시도 +1]
    SEND --> FEEDBACK[getFeedback 보존]
    FEEDBACK --> RESULT{Nav2 결과}
    RESULT -->|SUCCEEDED| NEXT{마지막 W7?}
    RESULT -->|CANCELED 또는 안전 권한 상실| CANCEL[CANCELED / 재시도·다음 WP 없음]
    RESULT -->|FAILED·REJECTED·UNKNOWN| RETRY{총 4회 미만?}
    RETRY -->|예| SEND
    RETRY -->|아니오| FINAL{현재 W7?}
    FINAL -->|아니오| SKIP[checkpoint를 다음 index로 저장] --> PATROL
    FINAL -->|예| FAIL[route FAILED]
    NEXT -->|아니오| CHECKPOINT[다음 index 저장] --> PATROL
    NEXT -->|예| DOCK[순찰 후 docking 경로]
~~~

자동시험은 실제 production 클래스의 일반 실패 3회 뒤 네 번째 성공, 네 번 실패, goal 거절 네 번, 안전 권한 상실 1회 취소, 중간 waypoint skip과 마지막 waypoint 실패를 확인한다. 실제 로봇의 Nav2·TF·지도·센서·최종 `cmd_vel`은 자동시험으로 대체하지 않으며 robot1·robot6 실기 통과 전 AMR-16을 100%로 표시하지 않는다.

2026-09-08 자동검증: 전체 단위시험 `Ran 352 tests` / `OK`,
`patrol_interfaces`와 `patrol_amr` symlink 빌드 성공. 기존 일반 빌드 산출물과
symlink 설치가 충돌해 해당 `build`·`install/patrol_amr` 디렉터리는 `/tmp`에
복구 가능하게 보관한 뒤 다시 빌드했다. 소스나 Git 이력은 변경하지 않았다.

robot1 실기 절차와 실패 유도 전용 설정은
[AMR-16 실제 로봇 시험](development/amr16-robot-test.md)에 분리했다. 전용
설정의 W1만 지도 밖 좌표이며 기본 `patrol_params.yaml`은 변경하지 않는다.

## 5. 배터리와 도킹

SOC·충전 방향에 따른 Battery enum은 interfaces.md 8절과 Q-11을 따른다. 무효·미수신은 UNKNOWN이다. 배터리 센서 입력 정책은 아래 TBD-AMR-003 결정 기록을 따른다.

### 5.1 battery_monitor.py — 구현 대조 완료

2026-09-07: 사용자 2단계 진행 요청과 TBD-AMR-003 권장안 승인에 따라 [battery_monitor.py](../src/patrol_amr/patrol_amr/battery_monitor.py)에 분류·상태 전이 모델과 ROS 노드를 구현했다. 이전 워크스페이스의 LOW/CHARGED 문자열 이벤트 코드는 현재 enum·Q-11과 달라 이관하지 않았다. 별도 BatteryEvent 계약은 추가하지 않았다.

- `classify_battery(soc, charging)`: 유효성이 확인된 SOC와 명시적인 충전 방향을 입력받아 [인터페이스 8절](interfaces.md#8-battery-enum과-임계값)의 상태를 반환한다. 잘못된 함수 인자는 ValueError이며 센서 오류 정책을 대신하지 않는다.
- `BatteryStateModel.update(observed, now)`: 초기 UNKNOWN, CRITICAL 즉시, 나머지는 Q-11 유지 후 반영한다. 후보가 바뀌거나 현재 상태로 돌아오면 이전 대기 시간을 버린다. `now`는 호출자가 전달하는 monotonic 초다.
- 상대 토픽 `battery_state`의 `sensor_msgs/BatteryState`를 sensor-data QoS로 구독한다. `CHARGING`·`FULL`은 충전 방향, `DISCHARGING`은 방전 방향으로 판정한다. 그 외 status, `present=false`, NaN, 0~1 범위 밖 SOC는 즉시 UNKNOWN이다.
- 마지막 메시지 수신 후 monotonic 경과 3초가 되면 즉시 UNKNOWN으로 전환한다. 유효한 CRITICAL은 즉시, 다른 유효 상태는 Q-11에 따라 같은 상태가 3초 연속 관측된 뒤 반영한다.
- 상태가 바뀔 때 상대 토픽 `battery_status`에 `std_msgs/UInt8`로 enum 값을 발행한다. 현재 상태를 늦게 구독한 내부 노드도 받도록 RELIABLE·TRANSIENT_LOCAL·KEEP_LAST(1)을 사용한다. 이 토픽은 AMR 내부 연결이며 공용 팀 간 인터페이스로 추가하지 않는다.
- 도킹·주행 명령·RobotStatus 발행은 이번 노드에 없다. 7~8단계가 내부 `battery_status`를 상태 보고에 연결한다.

**구현 대조 완료** — 2026-09-07 현재 코드 기준. 패키지 실행 등록은 9단계에서 추가한다.

~~~mermaid
flowchart TD
    A[검증된 SOC와 충전 방향] --> B[classify_battery]
    B --> C{함수 인자 유효?}
    C -->|아니오| ERR[ValueError / 호출자 수정 필요]
    C -->|예| D[인터페이스 8절에 따라 상태 분류]
    MSG[battery_state 콜백] --> VALID{present / SOC / status 유효?}
    VALID -->|예| A
    VALID -->|아니오| U[즉시 UNKNOWN]
    TIMER[0.1초 점검 타이머] --> STALE{마지막 수신 후 3초?}
    STALE -->|예| U
    D --> E[BatteryStateModel.update / observed와 monotonic now]
    U --> H
    E --> F{enum과 시각 유효?}
    F -->|아니오| ERR
    F -->|예| G{CRITICAL 또는 현재 상태와 같음?}
    G -->|예| H[상태 반영 / 대기 후보 초기화]
    G -->|아니오| I{대기 후보와 다름?}
    I -->|예| J[후보 교체 / 유지 시작 시각 초기화]
    I -->|아니오| K{Q-11 유지 시간 충족?}
    K -->|예| H
    K -->|아니오| L[기존 상태 유지]
    H --> R[현재 BatteryStatus 반환]
    J --> R
    L --> R
~~~

검증: [단위시험](../tests/test_battery_monitor.py)은 SOC 경계, 상태 쌍의 즉시/유지시간 경계, 후보 중단·재시작, 입력 유효성, 즉시 무효화를 확인한다. 실행 명령은 저장소 루트에서 `python3 -m unittest discover -s tests -p test_battery_monitor.py -v`다. [IT-13](integration.md#4-통합시험-명세)의 배터리 모델 일부이며 실센서·도킹·교대 통합시험은 미실행이다. 관제 검토는 [배터리 입력 정책 요청서](change_requests/CR-AMR_09-07_14-01_배터리_입력_정책.md)에 기록한다.

도킹은 DOCKING 진입 시 타이머를 시작한다. Q-09의 제한 안에서는 Nav2 재계획을 허용하지만 새 도킹 mission을 만들지 않는다. 접점 또는 완료 센서의 연속 확인으로 성공을 판정하고 실패는 관제로 보고한다. 가용 로봇 선정과 역할 교대는 관제 책임이다.

## 6. 로컬 Detection과 증적

다음은 로컬 Detection 처리의 설계 의도이며 Detection 관련 상세 계약은 TBD로 유지한다.

~~~text
OAK-D 영상 → bbox 생성 / DetectionCandidate
→ mission_supervisor가 AMR yaw 정렬
→ 영상 중심과 bbox 중심 정렬 상태에서 1초 연속 탐지
→ DetectionEvent 확정 → 증적 생성 → 시스템 모니터 수집·저장 / 관제 제어용 이벤트 전달
~~~

1초 조건의 의도는 보존하지만 정렬 오차, 동일 대상 기준, 탐지 단절 시 초기화, yaw timeout·token 및 이동 제한은 TBD-AMR-001이다.

Candidate/Event 필드·enum·QoS는 TBD-IF-006, 증적 전송은 TBD-IF-007을 참조한다. 차량 CameraState와 DetectionEvent를 합친다고 가정하지 않는다.

화재 확정 시 부저 ON, 동일 event_id 중복 처리 금지, 도킹 완료 후 OFF라는 정책을 유지한다. Q-12의 CHARGING 연속 확인 조건과 도킹 완료 센서 기준, 높은 SOC의 PATROL_READY/FULL 상태와의 관계는 TBD-AMR-004다. 실제 부저 제어 위치·계약도 미정이다.

## 7. 상태·결과·진단

RobotStatus의 발행·변경 rate는 Q-02다. PatrolReport는 명령과 연결해 SUCCEEDED/FAILED/CANCELED 및 실패·취소 reason을 제공한다. AMR-07은 subscriber가 없을 때 영속 큐에 보존하고 연결 후 같은 report ID로 발행한다. 수신 애플리케이션 저장 완료 ACK와 최종 큐 삭제 조건은 [TBD-IF-003 검토 요청서](change_requests/CR-AMR_09-08_10-42_PatrolReport_ACK와_큐_삭제_조건_검토.md)에 남겼다.

### 7.1 robot_status_state.py — 구현 대조 완료

2026-09-07: 사용자 7단계 진행 요청에 따라 [robot_status_state.py](../src/patrol_amr/patrol_amr/robot_status_state.py)에 8단계 `status_reporter`가 사용할 순수 Python 상태 모델을 구현했다. ROS 토픽을 발행하는 노드가 아니라 로봇 한 대의 상태를 보관하고 snapshot을 만드는 내부 모듈이다.

- `OperationalState`, `MissionState`, `DockingState`, `BatteryState`: [인터페이스 4·8절](interfaces.md#4-robotstatus)에 확정된 숫자만 `IntEnum`으로 정의했다. 네 축은 독립적으로 갱신한다. 축 조합별 허용 전이는 TBD-AMR-005이므로 이 파일에서 임의로 막지 않는다.
- `RobotStatusState.update_states(...)`: 전달된 축의 값을 모두 먼저 검증한 뒤 한꺼번에 반영한다. 하나라도 잘못되면 어느 축도 바뀌지 않는다. 실제 변경이 있을 때만 내부 `revision`을 1 증가시킨다. 이 revision은 8단계의 변경 감지용 로컬 값이며 공용 `status_sequence`가 아니다.
- `safety_state`: 확정된 `SafetyState` 0~5 enum만 수락한다. 초기값은 `SAFETY_UNKNOWN(0)`이다.
- `RobotStatusState.observe_pose(...)`: 유효 위치는 payload, `map` frame, 측정 시각이 모두 있어야 한다. `pose_valid=false`가 들어오면 현재 pose는 무효로 표시하되 마지막 유효 pose는 지우지 않는다. pose payload에는 8단계에서 ROS pose와 covariance가 함께 들어온다.
- `RobotStatusState.snapshot(snapshot_at)`: 현재 상태의 복사본을 만들고 같은 ROS clock의 snapshot 시각에서 마지막 유효 pose 측정 시각을 빼 `last_valid_pose_age`를 계산한다. token lease처럼 로컬 monotonic 시간을 쓰는 곳과 섞지 않는다.
- `RobotStatusState.update_mission_context(...)`: active command/mission ID, current waypoint, scan state, reason code/detail을 모두 먼저 검증한 뒤 한 번에 갱신한다. ID와 문자열은 mission 입력을 그대로 보존하며 waypoint·scan 의미는 TBD-IF-003이라 해석하지 않는다. reason code는 공용 필드 타입인 uint32 범위만 검증한다.

새 [interfaces.md](interfaces.md#4-robotstatus)는 상태 필드 이름을 `operational_state`, `mission_state`, `docking_state`, `battery_state`, `safety_state`로 명확히 했으므로 내부 모델도 이 이름을 사용한다. [RobotStatus.msg](../src/patrol_interfaces/msg/RobotStatus.msg)도 같은 이름과 확정된 safety enum으로 동기화했다. waypoint·scan 상세 동작은 여전히 TBD-IF-003이다.

~~~mermaid
flowchart TD
    INIT[RobotStatusState 생성] --> DEFAULT[UNKNOWN / NONE / pose_valid false]
    STATE[update_states] --> VALIDATE{전달된 모든 축 값 유효?}
    VALIDATE -->|아니오| ERROR[ValueError / 어떤 축도 변경 안 함]
    VALIDATE -->|예| CHANGED{기존 값과 다른가?}
    CHANGED -->|예| APPLY[축을 독립적으로 반영 + revision 증가]
    CHANGED -->|아니오| KEEP[상태와 revision 유지]
    CONTEXT[update_mission_context] --> CVALID{ID / waypoint / scan / reason 모두 유효?}
    CVALID -->|아니오| ERROR
    CVALID -->|예| CKEEP[mission context 원자 갱신 / 변경 시 revision 증가]
    POSE[observe_pose] --> PVALID{pose_valid?}
    PVALID -->|예| PCHECK{payload + map frame + 측정 시각 유효?}
    PCHECK -->|아니오| ERROR
    PCHECK -->|예| SAVE[현재 pose와 last_valid_pose 모두 갱신]
    PVALID -->|아니오| INVALID[현재 pose만 무효 반영]
    INVALID --> PRESERVE[last_valid_pose 보존]
    SAVE --> REV[변경 시 revision 증가]
    PRESERVE --> REV
    SNAP[snapshot 시각] --> AGE[last_valid_pose_age 계산]
    AGE --> COPY[독립 복사본 반환]
~~~

**14단계 추가 — odometry 축과 `motion_stopped`(2026-09-08).** [interfaces.md 3절](interfaces.md)이 판정에 필요한 네 값을 모두 확정해 두었으므로 이 모듈이 정한 숫자는 없다.

```text
선속도 절댓값 ≤ 0.05 m/s  AND  각속도 절댓값 ≤ 0.1 rad/s
  가 0.5초 연속 유지  AND  측정 age ≤ 0.5초   →  motion_stopped = true
```

- `observe_odometry(linear, angular, measured_at)`가 관측을 받고, 신선도 판정은 snapshot 시각에 달려 있으므로 `snapshot()`에서 완성한다. `STOP_LINEAR_LIMIT`·`STOP_ANGULAR_LIMIT`·`STOP_HOLD_SECONDS`·`ODOMETRY_MAX_AGE_SECONDS` 네 상수가 위 문장을 그대로 옮긴 것이다.
- **명령한 속도가 아니라 odometry다.** `local_safety_supervisor`가 `cmd_vel`에 0을 낸 것은 게이트가 닫혔다는 뜻이지 바퀴가 실제로 멈췄다는 뜻이 아니다. 이 구분이 [IT-04](integration.md#4-통합시험-명세)의 "실제 정지 확인"과 교대(TBD-INT-001)의 전제다.
- 한도를 벗어난 표본은 연속 유지 창을 닫는다. **관측이 끊긴 구간도 창을 닫는다** — 표본 간격이 신선도 한도를 넘으면 그 사이를 "연속 유지"로 주장할 수 없다. 정지 선언이 어려워지는 방향이라 관제가 근거 없이 새 token을 발급하지 않는다.
- 미수신·stale 상태의 선속도·각속도는 0이 아니라 `NaN`이다. 8단계 SOC와 같은 이유로, 측정하지 않은 값을 "측정했더니 0"으로 읽히게 두지 않는다.
- 미래 stamp(음수 age)는 낡음으로 보지 않는다. Q-17과 같은 판단이다 — 같은 ROS 시계이고 허용 역행 폭을 정한 문서가 없다.
- 시각이 역행하는 표본과 유한하지 않은 값은 거절한다.

검증: [단위시험](../tests/test_robot_status_state.py) 39건은 안전한 초기값, 독립 상태 축, mission context 6필드의 원자적 갱신·해제·uint32 경계, 미합의 safety/waypoint/scan 값의 불투명 처리, 유효 pose 저장, 무효 pose 뒤 마지막 유효 pose 보존, age 계산, 입력·snapshot 복사, 잘못된 frame·시각 거절을 확인한다. 14단계분은 네 상수가 interfaces.md 값과 일치하는지, 유지 창 경계, 한도 포함 여부와 초과, 신선도 경계, 관측 단절 시 창 재개, 미수신·stale의 NaN, 시각 역행·비유한 값 거절, 그리고 관측 없이는 정지라고 말하지 않는지를 확인한다. 실행 명령은 저장소 루트에서 `python3 -m unittest discover -s tests -p test_robot_status_state.py -v`다.

### 7.2 status_reporter.py — 구현 대조 완료

2026-09-07: 사용자 8단계 진행 요청에 따라 [status_reporter.py](../src/patrol_amr/patrol_amr/status_reporter.py)를 추가했다. `/{robot}/robot_status`를 새 `RobotStatus.msg` 이름으로 발행하며 Q-02의 정기 2 Hz와 상태 변경 발행 최대 10 Hz를 `PublicationGate`가 관리한다. `StatusSequence`는 프로세스 세션 안에서 1부터 증가하고, `source_session_id`는 실행 시 필수 parameter로 받는다.

- 입력 연결: 현재 구현된 상대 내부 토픽 `battery_status`를 구독해 `battery_state`를 갱신한다. 원본 `battery_state`도 읽어 유효한 SOC와 센서 측정 시각을 `battery_soc`·`battery_timestamp`로 보존한다. enum 변경은 최대 10 Hz 제한 안에서 즉시 발행 대상으로 표시한다.
- 필수 설정은 `robot_id`, `source_session_id`다. `safety_state`는 파라미터가 아니라 `local_safety_supervisor`의 내부 transient-local 상태 토픽을 구독해 갱신한다.
- **14단계 odometry 연결(2026-09-08):** 상대 토픽 `odom`(`nav_msgs/Odometry`)을 구독해 `linear_velocity`·`angular_velocity`·`motion_stopped`를 채운다. 판정은 7.1절의 `RobotStatusState`가 하고 이 노드는 ROS 변환만 한다. `odom`은 로봇 드라이버가 내는 표준 토픽이며 interfaces.md TBD 표에 없다 — 미정 항목이 아니다. launch의 `odom_topic` 인자로 드라이버 위치를 바꿀 수 있다(TBD-ARCH-001).
- **16단계 token 연결(2026-09-08):** 상대 내부 토픽 `accepted_token_id`(`std_msgs/String`)를 구독한다. 값이 비어 있지 않으면 같은 값을 `accepted_token_id`에 쓰고 `token_valid=true`, 빈 값이면 `''`·`false`로 한 snapshot에서 함께 쓴다. Q-02의 즉시 발행 목록에는 token이 없으므로 다음 정기 2 Hz snapshot에 반영한다.
- **17단계 pose 연결(2026-09-08):** Nav2 AMCL 표준 상대 토픽 `amcl_pose`(`geometry_msgs/PoseWithCovarianceStamped`)를 구독한다. `map` frame이고 pose·covariance 전부가 유한한 메시지는 현재 pose와 last-valid pose에 함께 보존한다. frame·수치가 무효면 `pose_valid=false`로 바꾸되 last-valid pose는 지우지 않는다. `pose_valid` 전이만 Q-02의 변경 발행 대상으로 표시하고 일반 위치 이동은 정기 2 Hz snapshot에 반영한다.
- **업무표 100% 연결 준비(2026-09-08):** `populate_mission_fields()`가 상태 snapshot의 active command/mission ID, waypoint, scan, reason code/detail을 실제 RobotStatus wire 필드에 모두 쓴다. mission subscriber는 아직 없으므로 기본값은 비어 있으며, future mission adapter가 `RobotStatusState.update_mission_context()`를 호출해야 실제 값이 들어간다.
- pose 수신이 끊겨도 임의 timeout으로 `pose_valid=false`를 만들지 않는다. Q-03·Q-05의 1.5초는 관제 STALE 및 주행 재개 조건이지 pose 유효성 정의가 아니다. RobotStatus의 pose와 last-valid pose가 측정 timestamp를 포함하므로 소비자가 그 시각으로 age를 판단한다.
- odometry 수신은 **즉시 발행 대상이 아니다.** Q-02가 즉시 발행을 요구하는 것은 mission·safety·battery enum과 `pose_valid`이고 속도는 그 목록에 없다. 속도는 매 표본마다 바뀌므로 변경 트리거로 다루면 이유 없이 10 Hz 제한을 넘긴다.
- **AMR-07 미션 상태 연결(2026-09-08):** `mission_status.json`을 `MissionStatusBridge`로 읽어 mission enum, active command·mission ID, 현재 waypoint와 reason을 같은 RobotStatus에 반영한다. 파일 경로는 robot별 ROS runtime 아래를 기본으로 사용하며 parameter로 바꿀 수 있다.
- **AMR-07 결과 발행(2026-09-08):** `patrol_report_outbox.json`의 종료 결과를 `PatrolReportDrain`이 `/{robot}/patrol_report`로 발행한다. subscriber가 없거나 publish가 실패하면 큐를 유지하고 다음 poll에서 재시도한다. 현재 삭제 시점은 matched subscriber가 있는 publish 호출 성공 직후이며 애플리케이션 저장 ACK 기반 삭제는 TBD-IF-003이다.
- operational·docking·scan의 실제 공급 경로와 safety enum 수치는 아직 미정이다. SOC 미수신은 0으로 오해하지 않도록 NaN으로 낸다.

~~~mermaid
flowchart TD
    START[StatusReporter 생성] --> CFG{robot_id / source_session_id 유효?}
    CFG -->|아니오| FAIL[시작 실패]
    CFG -->|예| MODEL[RobotStatusState 안전 초기값 생성]
    BS[battery_status 콜백] --> BVAL{BatteryState enum 유효?}
    TOK[accepted_token_id 콜백] --> KEEP_TOKEN[현재 유효 token ID 보존]
    AP[amcl_pose 콜백] --> APV{map frame / pose·covariance 유한?}
    APV -->|예| KEEP_POSE[현재 pose + last-valid pose 갱신]
    APV -->|아니오| INVALID_POSE[pose_valid false / last-valid 보존]
    KEEP_POSE --> PVC{pose_valid 전이?}
    INVALID_POSE --> PVC
    PVC -->|예| PENDING
    PVC -->|아니오| WAIT
    BVAL -->|아니오| WARN[경고 후 폐기]
    BVAL -->|예·변경| PENDING[변경 발행 pending]
    RAW[battery_state 콜백] --> SOC{present / SOC 유효?}
    SOC -->|예| KEEP_SOC[SOC + 센서 stamp 보존]
    SOC -->|아니오| UNKNOWN_SOC[NaN + 빈 stamp]
    MFILE[mission_status.json] --> MPOLL[0.1초 mission poll]
    MPOLL --> MBRIDGE[mission 상태·ID·waypoint·reason 반영]
    MBRIDGE --> PENDING
    OUTBOX[patrol_report_outbox.json] --> RPOLL[0.1초 report poll]
    RPOLL --> SUB{subscriber 존재?}
    SUB -->|아니오| OUTBOX
    SUB -->|예| RPUB[/{robot}/patrol_report 발행]
    RPUB -->|실패| OUTBOX
    RPUB -->|성공| RREMOVE[해당 pending record 제거]
    TICK[0.02초 timer] --> DUE{최초 또는 변경 0.1초 또는 정기 0.5초 도달?}
    DUE -->|아니오| WAIT[대기]
    DUE -->|예| SNAP[RobotStatusState.snapshot]
    SNAP --> MAP[새 RobotStatus 필드명으로 변환]
    CTX[future mission context] --> MCTX[active IDs / waypoint / scan / reason]
    MCTX --> MAP
    KEEP_TOKEN --> MAP
    KEEP_POSE --> SNAP
    INVALID_POSE --> SNAP
    MAP --> SEQ[status_sequence 증가]
    SEQ --> PUB[/{robot}/robot_status 발행]
~~~

검증: [단위시험](../tests/test_status_reporter.py) 17건과 [robot_status_state 단위시험](../tests/test_robot_status_state.py) 39건은 발행 주기, sequence, token·mission context 매핑, pose 유효성 및 context 원자성을 확인한다. main 통합 당시 status reporter·상태 모델·미션 bridge·report adapter/outbox/reporter 관련 단위시험 47건과 AMR-07 ROS 스모크도 통과했다. 실제 관제 저장 ACK 종단시험은 TBD-IF-003 결정 뒤 수행한다.

### 7.3 patrol_report.py — 구현 대조 완료

2026-09-08: 사용자 18단계 진행 요청에 따라 [patrol_report.py](../src/patrol_amr/patrol_amr/patrol_report.py)를 추가했다. 이 파일은 확정된 계약으로 최종 결과를 검증하고 불변 record를 만드는 순수 Python 모듈이다. AMR-07의 실제 영속 발행 경로는 `mission_reporter.py`·`patrol_report_outbox.py`·`patrol_report_adapter.py`와 `status_reporter.py`가 담당한다.

- `PatrolResult`와 `ReasonCode`는 [PatrolReport.msg](../src/patrol_interfaces/msg/PatrolReport.msg)의 결과 3종과 reason code 29종을 그대로 옮겼다. 정의되지 않은 숫자는 거절한다.
- `PatrolReportFactory`는 로봇·source session 하나의 report sequence를 관리한다. [interfaces.md 1.2절](interfaces.md#12-공용-식별자-규칙)에 따라 `rpt-<robot_session>-<report_sequence>`를 만들고 sequence는 최소 네 자리로 0을 채운다. persistent owner가 재시작 뒤 다음 sequence를 복원할 수 있도록 `next_sequence` 입력·조회만 제공한다.
- command·mission ID는 비어 있는지만 확인하고 문자열을 파싱하거나 다시 만들지 않는다. MissionCommand에서 받은 값을 그대로 echo해야 한다는 계약 때문이다.
- FAILED와 CANCELED는 `NONE`이 아닌 reason code와 비어 있지 않은 reason이 모두 필요하다. 성공·실패·취소 모두 시작·종료 시각을 보존하고 종료가 시작보다 앞서면 거절한다.
- 같은 command ID와 완전히 같은 결과를 다시 넣으면 기존 record 객체와 report ID를 그대로 반환한다. 다른 결과로 덮으려 하면 거절하고 sequence도 소비하지 않는다.
- `populate_message()`는 header 발행 시각을 호출자에게 명시적으로 받고 `PatrolReport.msg`의 모든 payload 필드를 채운다. `publish_record()`는 호출자가 소유한 publisher와 message type을 사용해 한 번 발행한다. publisher QoS helper는 계약 그대로 RELIABLE·VOLATILE·KEEP_LAST(20)이다.
- `record_to_json()`·`record_from_json()`은 terminal record 전체를 canonical JSON으로 보존·재검증한다. `command_store`가 이 값을 영속 저장하므로 재시작 뒤에도 같은 report ID와 payload를 복원할 수 있다.
- `command_store`가 영속 저장·복원을 담당하고 `report_replay.py`가 재연결 재발행을 담당한다. ACK·삭제 계약이 없으므로 보존 report를 자체 삭제하지 않는다. mission 결과 콜백과 실제 ROS publisher node 연결은 남아 있다.
- AMR-07 통합으로 미션 결과 입력, robot별 영속 큐와 ROS publisher를 연결했다. 수신 애플리케이션의 저장 완료 ACK와 그 ACK를 기준으로 한 최종 큐 삭제 조건은 TBD-IF-003이며, 현재 두 결과 생성 경로를 하나의 canonical factory/store로 정리하는 작업은 I-01 결합 단계에 남긴다.

~~~mermaid
flowchart TD
    START[PatrolReportFactory 생성] --> CFG{robot_id / robot session / next sequence 유효?}
    CFG -->|아니오| FAIL[ValueError / 생성 실패]
    CFG -->|예| WAIT[terminal command 결과 대기]
    INPUT[create: command·mission·result·reason·times] --> VALIDATE{필수 ID / enum / reason / 시각 / 배열 유효?}
    VALIDATE -->|아니오| REJECT[ValueError / sequence 소비 안 함]
    VALIDATE -->|예| DUP{같은 command ID가 이미 있음?}
    DUP -->|예·payload 동일| REUSE[기존 record와 report ID 반환]
    DUP -->|예·payload 다름| CONFLICT[충돌 거절 / 기존 report 보존]
    DUP -->|아니오| ID[rpt-robot_session-NNNN 생성]
    ID --> RECORD[불변 PatrolReportRecord 저장]
    RECORD --> NEXT[next sequence 증가]
    NEXT --> RETURN[호출자에게 record 반환]
    RETURN --> MAP[populate_message: header 시각 + 전체 wire 필드]
    MAP --> EMIT[publish_record: caller-owned publisher로 1회 발행]
    EMIT --> QOS[RELIABLE / VOLATILE / KEEP_LAST 20]
    RETURN --> JSON[record_to_json canonical 저장]
    JSON --> RESTORE[record_from_json 전체 계약 재검증]
    QOS --> PERSIST[AMR-07 outbox·status_reporter 발행 경로]
    PERSIST --> ACK[애플리케이션 ACK·최종 삭제 TBD-IF-003]
    RESTORE --> REPLAY[report_replay 재연결 재발행]
~~~

검증: [단위시험](../tests/test_patrol_report.py) 24건은 result/reason 상수 일치, report ID 형식과 sequence 복원, 필수 필드·시각 경계, 실패·취소 reason 강제, 동일 command 재요청의 ID 재사용, 충돌 거절과 sequence 비소비, 전체 wire 필드 변환, event ID 복사, 1회 발행 helper와 QoS depth, canonical JSON 왕복과 손상 payload 거절을 확인한다. 전체 단위시험은 `Ran 200 tests`/`OK`, `colcon build --packages-select patrol_interfaces patrol_amr`는 두 패키지 성공이다. ROS 환경에서 QoS 객체가 `20 RELIABLE VOLATILE KEEP_LAST`인 것도 확인했다. mission 입력 subscriber가 없으므로 아직 사용자 종단 토픽 시험 대상은 아니다.

### 7.4 report_replay.py — 구현 대조 완료 (순수 모듈)

`SubscriberConnectionReplay.observe()`는 report publisher의 구독자 수가 0에서 양수로 바뀐 연결 epoch당 한 번만 replay를 요청한다. 시작 시 이미 구독자가 있어도 1회 발생하며 연결 유지 중에는 재발행하지 않는다. `replay_completed_reports()`는 보존 record 순서와 report ID를 유지하고, 발행 시각은 호출자 clock으로 공급받는다.

~~~mermaid
flowchart TD
    COUNT[subscription count] --> EDGE{0 → 양수?}
    EDGE -->|아니오| WAIT[재발행 없음]
    EDGE -->|예| LOAD[completed_reports 순서 복원]
    LOAD --> STAMP[호출자 ROS clock]
    STAMP --> PUB[같은 report ID로 재발행]
    PUB --> KEEP[ACK 계약 없음 / 영속 보존]
~~~

[replay 단위시험](../tests/test_report_replay.py) 6건을 포함한 전체 자동시험은 `Ran 231 tests`/`OK`다.

다음 기존 안전 로그를 보존한다.

~~~text
E_STOP_ACTIVATED
E_STOP_RELEASE_CONDITION_STARTED
E_STOP_RELEASE_CONDITION_CANCELED
E_STOP_AUTO_RELEASED
DRIVE_TOKEN_REVOKED
DRIVE_TOKEN_EXPIRED
~~~

E-stop 해제 부저는 사용하지 않는다. 화재 부저와 E-stop 로그 정책을 혼용하지 않는다. 로봇·명령·이벤트 ID를 진단에 연결하는 것은 권장안이며 팀 간 공용 로그 필드·전송 계약은 [interfaces.md의 TBD-IF-011](interfaces.md#tbd), 내부 저장 스키마는 [monitoring_and_data.md의 TBD-MON-001](monitoring_and_data.md#tbd)에서 정한다.

## 8. 검증 기준

명령 중복·토큰 역순/만료·최종 속도 발행권·무효 pose 보존·배터리 경계·도킹 제한·Detection 미확정 조건을 확인한다. 시나리오별 정상·실패·취소 경로, 시나리오 전환 시 잔여 목표·콜백 정리, 공통 안전 경로 적용, 코드와 flowchart의 일치도 확인한다. 구체적 실행과 기대 결과는 [통합시험](integration.md#4-통합시험-명세)에 연결한다.

## TBD

| ID | 미정 사항 | 영향 단위 | 상태 |
|---|---|---|---|
| TBD-AMR-001 | 정렬 오차, 동일 대상·confidence, 연속 탐지 단절, yaw 속도·timeout·주행 중재 | AMR·관제 | OPEN |
| TBD-AMR-002 | AMR2 LiDAR 검증 대상·연산 위치·요청/결과·timeout | AMR·관제 | OPEN |
| TBD-AMR-003 | 결정(2026-09-07): `BatteryState` 3초 미수신 시 UNKNOWN. CHARGING/FULL은 충전, DISCHARGING은 방전. 나머지 status·present=false·NaN·범위 밖 SOC는 UNKNOWN. 근거: 사용자 권장안 승인. 영향: AMR·관제. [검토 요청](change_requests/CR-AMR_09-07_14-01_배터리_입력_정책.md) | AMR·관제 | AMR 반영·관제 검토 요청 |
| TBD-AMR-004 | 도킹 완료·CHARGING·높은 SOC 관계, 화재 부저 제어자·해제 계약 | AMR·관제 | OPEN |
| TBD-AMR-005 | 상세 상태 전이·STOP/CANCEL 차이·재개 지점·waypoint/scan 정책 | AMR·관제 | OPEN |
| TBD-AMR-006 | 로컬 정지 감속·거리·장애물 및 센서 실패 판정 | AMR·관제 | OPEN |

해결 시 결정 근거·일자와 [수정 요청서](change_requests/README.md)를 기록한다.
