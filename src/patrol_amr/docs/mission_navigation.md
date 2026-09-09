# 미션·내비게이션 구현 대조

구현 대조 기준: `patrol_amr` 0.4.0,
`feat/amr-mission-navigation` 작업 트리, 2026-09-08.

이 문서는 박성현 담당 미션·내비게이션 코드와 조정묵 담당
`local_safety_supervisor`를 연결한 경계를 설명한다. 2026-09-08
TBD-IF-009 합의로 Nav2 후보는 `cmd_vel_safe`(`TwistStamped`), 최종
구동 출력은 `cmd_vel`(`Twist`), 후보 신선도는 Q-17 0.5초로
확정됐다. 미션 노드는 `motion_allowed`를 받아 안전 권한이 사라지면
실행 중인 Nav2·Dock Action을 취소한다. `mission_reporter.py`의 실제 ROS
발행과 yaw 후보 중재는 각각 TBD-IF-003·TBD-AMR-001의 후속 범위다.

## Patrol Nav2 bringup

```mermaid
flowchart LR
    MAP[map_server / AMCL] --> PLANNER[planner_server]
    PLANNER --> BT[bt_navigator]
    BT --> CONTROLLER[controller_server]
    CONTROLLER -->|cmd_vel_nav| SMOOTHER[velocity_smoother]
    SMOOTHER -->|cmd_vel_smoothed| COLLISION[collision_monitor]
    COLLISION -->|cmd_vel_safe<br/>TwistStamped| SAFETY[local_safety_supervisor]
    SAFETY -->|cmd_vel<br/>Twist| DRIVER[Create 3 구동부]
    TOKEN[/control/drive_token] --> SAFETY
    ESTOP[/control/estop] --> SAFETY
    SAFETY -->|motion_allowed| MISSION
    MISSION[mission_supervisor] -->|NavigateToPose| BT
    MISSION -->|Dock Action| DOCK[docking_server]
    ROUTE[route_server: 이 단계에서 미사용]:::unused
    classDef unused fill:#eee,stroke:#999,color:#666
```

현재 단일 기능 실기 단계에서는 `mission_supervisor`가 W1~W7을 각각
`NavigateToPose`로 보내므로 `route_server`와 Nav2의 `waypoint_follower` API를
사용하지 않는다. `patrol_nav2.launch.py`는 두 노드를 lifecycle 관리 대상에서
제외해 route service 지연이 순찰 bringup 전체를 막지 않도록 한다. Fast DDS
서비스 endpoint가 발견되기 전에 전환 요청을 보내지 않도록 별도 lifecycle
manager는 Nav2 프로세스 시작 10초 뒤에 실행한다.

동일한 Fast DDS 준비 지연이 `map_server`와 AMCL lifecycle 서비스에서도
확인되어 `patrol_localization.launch.py`가 두 노드를 먼저 생성하고 기본 10초
후 별도 lifecycle manager를 시작한다. 기존 manager는 `autostart=false`로
유지해 활성화 요청이 중복되지 않게 한다.

## 파일 책임

| 코드 | 진입점·책임 |
|---|---|
| `mission_supervisor.py` | `MissionSupervisor.__init__`: ROS 구성과 수명 관리 |
| `mission_config.py` | `load_config`: namespace·파라미터 조합 |
| `motion_authorization.py` | 로봇별 구동 토큰과 선택한 속도 경로 검증 |
| `robot_readiness.py` | AMCL pose age·LiDAR·odometry 수신 상태 관리 |
| `robot_readiness_callbacks.py` | AMCL·scan·odom 콜백을 readiness 상태에 전달 |
| `motion_gate.py` | 정적 구동 승인과 실시간 센서 준비 상태 결합 |
| `drive_token_guard.py` | 공용 안전 규칙: holder·session·sequence·로컬 monotonic lease 검증 |
| `mission_drive_token.py` | 공용 guard를 worker-safe snapshot 형태로 감싼 미션 adapter |
| `drive_token_callback.py` | DriveToken 콜백을 guard와 mission 취소 gate에 전달 |
| `motion_permission.py` | `motion_allowed` Bool 콜백 상태를 fail-closed로 저장 |
| `local_safety_supervisor.py` | DriveToken·E-stop·Q-17을 `cmd_vel_safe`에 적용해 최종 `cmd_vel` 발행 |
| `waypoint_repository.py` | `load_waypoints`: W1~W7 개수·순서·유한 좌표 검증 |
| `mission_command_parser.py` | `MissionCommandParser.parse`: 공용 명령 계약 검증·내부 객체 변환 |
| `mission_command_callback.py` | `MissionCommandCallback.__call__`: parser 호출·큐 제출 |
| `mission_arbiter.py` | `MissionArbiter.submit`: 단일 주행 허용·STOP/CANCEL 신호 |
| `mission_worker.py` | `MissionWorker._run`: 영속 claim·시나리오 실행·상태와 종료 결과 저장 |
| `mission_controller.py` | `MissionController.execute`: command별 시나리오 선택 |
| `mission_state.py` | `MissionStateTracker`: 상태 reporter용 내부 snapshot |
| `mission_reporter.py` | `MissionReporter.report`: 종료 결과 검증·프로세스 내 중복 억제·sink 전달 |
| `mission_status_store.py` | 최신 미션 snapshot을 원자 교체로 프로세스 간 전달 |
| `status_mission_bridge.py` | 저장 snapshot을 RobotStatus 미션 축·필드로 변환 |
| `patrol_report_outbox.py` | 미전송 PatrolReport를 report ID와 함께 영속 보관 |
| `patrol_report_adapter.py` | outbox record를 ROS 메시지로 변환·발행 |
| `status_reporter.py` | Q-02 RobotStatus 발행과 PatrolReport outbox drain |
| `command_store.py` | `CommandStore.claim/finish`: 중복·충돌·checkpoint 원자 저장 |
| `navigation_adapter.py` | `NavigationAdapter`: Nav2·도킹 구현 조합 |
| `nav2_goal_runner.py` | `Nav2GoalRunner.go_to`: pose goal·안전 취소·결과 정규화 |
| `docking_runner.py` | `DockingRunner.dock/ensure_undocked`: Action과 Q-09 확인 |
| `scenarios/start_patrol.py` | `start_patrol`: 새 순찰 checkpoint 초기화·undock |
| `scenarios/patrol.py` | `PatrolScenario.run`: W1~W7·checkpoint·체류 |
| `scenarios/resume_patrol.py` | `resume_patrol`: 합의된 정책이 있을 때만 재개 |
| `scenarios/safe_zone.py` | `move_to_safe_zone`: 명령이 제공한 map pose 실행 |
| `scenarios/docking.py` | `dock`: 도킹 공통 실행기로 위임 |
| `scenarios/interruption.py` | `interrupt_navigation`: Nav2 취소 요청 |
| `fire_event_registry.py` | `FireEventRegistry`: 활성 화재 ID·다중 화재 부저 상태 |
| `audio_note_sequence_adapter.py` | `AudioNoteSequenceAdapter`: 무한 음표 Action start·cancel |

## ROS 구성과 설정

`mission_supervisor.py`

~~~mermaid
flowchart TD
    A[MissionSupervisor 생성] --> B{MissionCommand 타입 설치됨}
    B -->|아니오| X[오류 종료]
    B -->|예| C[mission_config.load_config]
    C --> D[CommandStore·State·Readiness·MotionGate 생성]
    D --> E[mission_command·/control/drive_token·motion_allowed 구독]
    E --> F[MissionWorker 시작]
    F --> J[MissionSupervisor 전용 executor spin]
    F --> K[worker의 TurtleBot4Navigator는<br/>별도 global executor 사용]
    K -->|초기화 실패| L[주행 영구 차단 사유 저장]
    G[ROS 종료] --> H[arbiter close·goal cancel]
    H --> I[worker join·navigator destroy]
~~~

`mission_config.py`

~~~mermaid
flowchart TD
    A[load_config] --> B{robot_id가 robot1 또는 robot6}
    B -->|아니오| X[설정 오류]
    B -->|예| C{namespace와 robot_id 일치}
    C -->|아니오| X
    C -->|예| D{waypoint 값이 7개 x/y/yaw 조합}
    D -->|아니오| X
    D -->|예| E{시간·resume 설정 유효}
    E -->|아니오| X
    E -->|예| F[구동 경로·로봇별 enable token 설정]
    F --> G[MissionConfig 반환]
~~~

`robot_readiness_callbacks.py`, `robot_readiness.py`, `motion_gate.py`

~~~mermaid
flowchart TD
    A[amcl_pose callback] --> B{map frame·유한 pose·quaternion·stamp 유효}
    B --> C[pose source age와 수신 시각 저장]
    D[scan callback] --> E[LiDAR 최초 수신 저장]
    F[odom callback] --> G[odometry 최초 수신 저장]
    C --> H[MotionGate]
    E --> H
    G --> H
    I[safety_path_ready 또는 hardware_test_mode] --> H
    J[ENABLE_ROBOT_ID_MOTION 일치] --> H
    K[local_safety motion_allowed] --> H
    H --> L{선택한 경로의 pose 기준과 모든 조건 충족}
    L -->|예| M[주행 명령 허용]
    L -->|아니오| N[사유 코드와 함께 주행 명령 거부·현재 goal 취소]
~~~

`drive_token_callback.py`, `drive_token_guard.py`

~~~mermaid
flowchart TD
    A[/control/drive_token callback] --> C{control session과 sequence 유효}
    C -->|아니오| Y[역순·중복·과거 session 무시]
    C -->|예| B{holder가 현재 robot_id인가}
    B -->|아니오| X[현재 로봇 권한 회수·mission cancel]
    B -->|예| D{token_id가 비어 있는가}
    D -->|예| E[즉시 회수·활성 mission cancel]
    D -->|아니오| F[수신 monotonic 시각부터 최대 1초 lease]
    F --> G[MissionCommand 수신 대기]
    G --> H{MissionCommand와 token·센서 준비가 모두 유효}
    H -->|예| I[mission queue 수락]
    H -->|아니오| J[명령 거부·주행 없음]
    F --> K{50 ms watchdog에서 만료 확인}
    K -->|만료| E
~~~

DriveToken은 주행 권한이며 자체적으로 임무를 시작하지 않는다. 같은 token의
갱신은 증가하는 `message_sequence`를 사용해야 한다. 토큰이 회수되거나 로컬
lease가 만료되면 현재 Nav2 또는 Dock Action이 취소되며, 다시 출발하려면
유효한 토큰과 새로운 MissionCommand가 모두 필요하다.

`local_safety_supervisor.py`, `motion_permission.py`

~~~mermaid
flowchart TD
    A[/control/drive_token callback] --> G[DriveTokenGuard]
    B[/control/estop callback] --> E[EStopGuard]
    C[cmd_vel_safe callback<br/>TwistStamped] --> F[Q-17 header stamp 검사]
    G --> P{token 권한 유효}
    E --> Q{E-stop 비활성}
    P --> R[motion_allowed 발행]
    Q --> R
    R --> S[mission motion_permission callback]
    S -->|false| T[현재 Nav2·Dock Action 취소]
    P --> V{token·E-stop·Q-17 모두 통과}
    Q --> V
    F --> V
    V -->|예| W[후보를 cmd_vel Twist로 변환·발행]
    V -->|아니오| X[cmd_vel 0 발행]
    Y[100 ms recheck] --> P
    Y --> F
~~~

`motion_allowed`는 명령 수락과 Action 취소용 권한 신호다. 최종
물리 차단은 `local_safety_supervisor`가 `cmd_vel_safe`를 직접 게이트하여
수행한다. 따라서 미션 worker가 취소에 지연되어도 token 만료·E-stop·
후보 0.5초 초과 중 구동부에는 0 속도가 전달된다.

최종 local safety 경로는 Q-05의 pose age 1.5초를 적용한다. 실기 단일 기능
경로는 정지 중 AMCL header가 갱신되지 않는 장비 동작을 고려해 유효 pose의
수신을 확인하고, 이후 TF·costmap·LiDAR timeout은 stock Nav2와 collision
monitor가 담당한다.

## 명령 콜백과 실행 수명

`mission_command_parser.py`, `mission_command_callback.py`

~~~mermaid
flowchart TD
    A[MissionCommand callback] --> B[MissionCommandParser.parse]
    B --> C{구조화 command·mission ID<br/>robot_id·enum 유효}
    C -->|아니오| R[거부 로그]
    C -->|예| D{명령별 target_id 계약 일치}
    D -->|아니오| R
    D -->|예| E{target_pose가 기본값인가}
    E -->|아니오| R
    E -->|예| G[MissionRequest]
    G --> H[MissionArbiter.submit]
    H -->|허용| I[즉시 callback 종료]
    H -->|busy·safety 미준비·종료 중| R
~~~

`mission_arbiter.py`

~~~mermaid
flowchart TD
    A[submit] --> B{STOP/CANCEL}
    B -->|예| C[cancel_event 설정]
    C --> D[interrupt를 worker queue에 추가]
    B -->|아니오| E{worker 영구 차단 또는<br/>MotionGate 미준비}
    E -->|예| R[SAFETY_NOT_READY와 실제 사유]
    E -->|아니오| F{주행 queued 또는 active}
    F -->|예| G[BUSY / 대체 우선순위 TBD-AMR-005]
    F -->|아니오| H[주행 1개 queue]
    I[worker finish interrupt] --> J{남은 interrupt 있음}
    J -->|아니오| K[cancel_event 해제]
~~~

`mission_worker.py`

~~~mermaid
flowchart TD
    A[worker 시작] --> B{구동 경로 선택과 로봇별 token 일치}
    B -->|예| C[NavigationAdapter 생성·Nav2 active 대기]
    C -->|실패| D[주행 차단·오류 로그]
    B -->|아니오| E[주행 차단 상태]
    C --> F[queue 대기]
    D --> F
    E --> F
    F --> G{command_store claim}
    G -->|같은 ID·같은 내용| H[중복 실행 억제]
    G -->|같은 ID·다른 내용| I[충돌 로그]
    G -->|저장 실패| J[주행 차단]
    G -->|신규| K[시작 state 영속 저장]
    K --> L[MissionController.execute]
    L --> M[종료 결과·시각·마지막 waypoint 확정]
    M --> N[PatrolReport outbox 저장]
    N --> O[command 결과·terminal state 저장]
    O --> F
    N -->|실패| P[REPORT_DURABILITY_FAILED·주행 차단]
    O -->|저장 실패| Q[해당 durability 사유·주행 차단]
~~~

`mission_controller.py`

~~~mermaid
flowchart TD
    A[execute] --> B{command}
    B -->|START_PATROL| C[start_patrol]
    B -->|RESUME_PATROL| D[resume_patrol]
    B -->|MOVE_TO_SAFE_ZONE| E[safe_zone]
    B -->|DOCK| F[docking]
    B -->|STOP/CANCEL| G[interruption]
    B -->|기타| H[REJECTED]
    C --> I[NavigationResult 변환]
    D --> I
    E --> I
    F --> I
    G --> J[SUCCEEDED: 취소 요청 처리]
    I --> K[SUCCEEDED·FAILED·CANCELED]
~~~

## 시나리오

`scenarios/start_patrol.py`

~~~mermaid
flowchart TD
    A[START_PATROL] --> B[같은 patrol ID checkpoint 초기화]
    B --> C[MISSION_UNDOCKING]
    C --> D{ensure_undocked 결과 / timeout TBD}
    D -->|성공| E[PatrolScenario W1부터 실행]
    D -->|실패·취소·미확인| F[종료·자동 출발 없음]
    E --> G{W1~W7 모두 성공}
    G -->|아니오| H[실패·취소 결과 종료]
    G -->|예| I[MISSION_DOCKING]
    I --> J[Dock Action·dock 상태 연속 확인]
    J -->|성공| K[순찰 cycle SUCCEEDED]
    J -->|실패·취소| H
~~~

`scenarios/patrol.py`

~~~mermaid
flowchart TD
    A[run 시작 index] --> B{cancel_event}
    B -->|설정| X[CANCELED]
    B -->|해제| C{남은 waypoint}
    C -->|없음| D[checkpoint 삭제·SUCCEEDED]
    C -->|있음| E[MISSION_PATROLLING·현재 W]
    E --> F[Nav2 go_to / 최초 1회 + 재시도 최대 3회]
    F -->|성공| G[다음 W index 원자 저장]
    F -->|중간 W 일반 실패| S[다음 W index 저장 / skip]
    F -->|마지막 W 실패| H[해당 checkpoint 유지·종료]
    F -->|안전 취소| X
    S --> C
    G --> I[설정된 dwell 동안 cancel 확인]
    I -->|완료| C
    I -->|취소| X
~~~

`scenarios/resume_patrol.py`

~~~mermaid
flowchart TD
    A[RESUME_PATROL] --> B{resume_policy}
    B -->|disabled| X[REJECTED / TBD-AMR-005]
    B -->|합의된 설정| C{checkpoint 존재}
    C -->|아니오| D[REJECTED]
    C -->|예| E[정책에 따른 start index]
    E --> F[PatrolScenario.run]
~~~

`scenarios/safe_zone.py`

~~~mermaid
flowchart TD
    A[MOVE_TO_SAFE_ZONE] --> B{target frame이 map}
    B -->|아니오| X[REJECTED]
    B -->|예| C[안전구역 Waypoint 변환]
    C --> D[Nav2 go_to]
    D -->|성공| E[MISSION_WAITING_SAFE_ZONE]
    D -->|실패·취소| F[종료·현 위치 자동 재개 없음]
~~~

`scenarios/docking.py`

~~~mermaid
flowchart TD
    A[DOCK] --> B[MISSION_DOCKING]
    B --> C[DockingRunner.dock]
    C --> D{Q-09 결과}
    D -->|성공| E[SUCCEEDED]
    D -->|timeout·센서 미확인·Action 실패| F[FAILED]
    D -->|취소| G[CANCELED]
~~~

`scenarios/interruption.py`

~~~mermaid
flowchart TD
    A[STOP 또는 CANCEL] --> B[NavigationAdapter.cancel]
    B --> C[자동 재개하지 않고 다음 MissionCommand 대기]
    C --> D[상태 보존 차이는 TBD-AMR-005]
~~~

## Nav2와 도킹

`navigation_adapter.py`

~~~mermaid
flowchart TD
    A[NavigationAdapter 생성] --> B[TurtleBot4Navigator 1개 소유]
    B --> C[Nav2GoalRunner]
    B --> D[DockingRunner]
    E[go_to·cancel] --> C
    F[dock·ensure_undocked] --> D
    G[종료] --> H[navigator node destroy]
~~~

`nav2_goal_runner.py`

~~~mermaid
flowchart TD
    A[Waypoint] --> B{cancel 상태 또는 MotionGate 미준비}
    B -->|예| X[CANCELED / goal 미전송 / 재시도 없음]
    B -->|아니오| C[map PoseStamped 생성·goToPose]
    C -->|명시적 goal 거부| Y[REJECTED 결과]
    C -->|수락| D{task 완료}
    D -->|아니오| FB[getFeedback 보존]
    FB --> E{cancel_event 또는 MotionGate 상실}
    E -->|예| F[cancelTask 1회]
    E -->|아니오| D
    F --> D
    D -->|예| G[getResult]
    G --> H[SUCCEEDED·FAILED·CANCELED·UNKNOWN]
    Y --> R{일반 실패이고 총 4회 미만?}
    H --> R
    R -->|예| C
    R -->|아니오| T[최종 NavigationResult]
~~~

재시도 수는 `navigation_types.MAX_GOAL_RETRIES=3` 한 곳에서 관리한다. 최초
시도까지 합쳐 goal당 최대 네 번이다. 안전 권한 상실은 일반 Nav2 실패와
구분해 `CANCELED`로 반환하므로 재시도 루프에 들어가지 않는다. 중간 waypoint
skip 뒤 최종 PatrolReport에 어떤 상세를 기록할지는 TBD-AMR-005 잔여다.

`docking_runner.py`

~~~mermaid
flowchart TD
    A[dock] --> B[Q-09 전체 deadline 시작]
    B --> C[Dock Action server·goal·result 대기]
    C -->|거부·실패·취소·deadline| X[해당 결과]
    C -->|Action 성공| D{dock 센서 2초 연속 확인}
    D -->|Q-09 유지 충족| E[SUCCEEDED]
    D -->|끊김| F[연속 시간 초기화]
    F --> D
    D -->|전체 deadline| G[FAILED]
~~~

현재 단계의 순찰 종료 성공 판정은 Dock Action 성공과 `dock_status` 2초
연속 확인까지다. Q-09의 `CHARGING` 동시 확인은 `battery_monitor` 병합 뒤
추가하므로 이 단계의 결과를 최종 도킹 통합시험 완료로 해석하지 않는다.

## 이벤트 기능 기초

DetectionCandidate/Event와 증적의 v1.0 wire 필드·상수는 고정됐지만 정식
토픽·event_type 의미·중재·재전송 계약은 차기 버전 TBD-IF-006·007이다.
따라서 ROS event node는 아직 생성하지 않았다. 실제 robot6에서 성공한
`audio_note_sequence` Action과 Q-12의 다중 활성 화재 규칙만 독립 모듈로
구현했다.

`fire_event_registry.py`

~~~mermaid
flowchart TD
    A[fire event ID 입력] --> B{activate 또는 resolve}
    B -->|activate| C{이미 active인가}
    C -->|예| D[상태 변경 없음]
    C -->|아니오| E[active set 추가]
    B -->|resolve| F{active ID인가}
    F -->|아니오| D
    F -->|예| G[active set 제거]
    D --> H{active event가 남았는가}
    E --> H
    G --> H
    H -->|예| I[buzzer_should_be_on=true]
    H -->|아니오| J[buzzer_should_be_on=false]
~~~

`audio_note_sequence_adapter.py`

~~~mermaid
flowchart TD
    A[start와 호출자 제공 note] --> B{pending 또는 active goal}
    B -->|예| C[중복 goal 억제]
    B -->|아니오| D{Action server 사용 가능}
    D -->|아니오| E[RuntimeError]
    D -->|예| F[INFINITE AudioNoteSequence goal]
    F --> G{goal accepted}
    G -->|아니오| H[idle 복귀]
    G -->|예| I[goal handle 보관]
    J[stop] --> K{goal response 대기 중}
    K -->|예| L[응답 뒤 cancel 예약]
    K -->|아니오·active| M[cancel_goal_async]
    I --> M
~~~

### 이벤트 기초 모듈 기술 선택 근거

| 선택 | 근거 | 적용 범위와 한계 |
|---|---|---|
| active fire ID를 set으로 관리 | 같은 활성 event 중복은 한 번만 반영하고 복수 화재 중 하나가 남으면 Q-12에 따라 부저를 유지한다. | event 해소 메시지와 과거 ID 보관 기간은 TBD-IF-006이다. |
| Action transport adapter 분리 | robot6에서 가청 확인된 `AudioNoteSequence`를 사용하며 Detection 판단 코드가 TurtleBot 메시지에 의존하지 않게 한다. | robot1 실기, 화재음 패턴, Action timeout은 합의가 필요하다. |
| INFINITE goal + cancel | ON 상태를 유한 반복 횟수로 추측하지 않고 OFF 결정이 올 때 명시적으로 중단한다. | cancel 실패 진단과 재시도 계약은 TBD-AMR-004다. |
| note를 호출자 입력으로 요구 | 화재음 주파수·길이를 임의 상수로 고정하지 않는다. | event node 설정은 패턴 결정 뒤 추가한다. |
| pending/active 중복 start 억제 | 같은 상태 callback이 반복돼도 Action goal을 쌓지 않는다. | 프로세스 재시작·장비 재연결 정책은 후속 통합 범위다. |

## 내부 상태와 영속성

`mission_state.py`

~~~mermaid
flowchart TD
    A[worker command 시작] --> B[command_id·mission_id 저장]
    C[scenario state_callback] --> D[mission·waypoint 갱신]
    E[command 종료] --> F[terminal mission·outcome·reason code 갱신]
    B --> G[lock 보호 snapshot]
    D --> G
    F --> G
    G --> H[revision 포함 불변 snapshot]
~~~

`mission_status_store.py`

~~~mermaid
flowchart TD
    A[MissionStateSnapshot] --> B[dict·schema version 변환]
    B --> C[temp 파일 write·fsync]
    C --> D[atomic replace·directory fsync]
    D --> E[(mission_status.json)]
    E --> F[status_reporter read]
    F -->|schema·필드 정상| G[MissionStateSnapshot 복원]
    F -->|손상·미지원| H[MissionStatusStoreError·기존 파일 보존]
~~~

`mission_reporter.py`

~~~mermaid
flowchart TD
    A[MissionRequest·outcome·reason code·시각] --> B{outcome}
    B -->|REJECTED| C[NOT_REPORTABLE]
    B -->|그 외 미지원 값| D[ValueError]
    B -->|SUCCEEDED·FAILED·CANCELED| E{실패·취소 reason 존재}
    E -->|필요하지만 없음| D
    E -->|유효| F[uint32 code·시간 순서·event ID 검증]
    F --> M[불변 MissionCompletion 생성]
    M --> G{command_id가 published 또는 in-flight}
    G -->|예| H[DUPLICATE]
    G -->|아니오| I[in-flight 등록 후 sink 호출]
    I -->|성공| J[published 등록·PUBLISHED]
    I -->|예외| K[in-flight 해제·ReportPublishError]
    K --> L[같은 command_id 재시도 가능]
~~~

`patrol_report_outbox.py`

~~~mermaid
flowchart TD
    A[MissionCompletion·source session] --> B[file lock]
    B --> C{같은 command ID pending}
    C -->|같은 결과| D[기존 report ID 반환]
    C -->|다른 결과| E[충돌 오류]
    C -->|없음| F[session별 sequence 증가]
    F --> G[rpt-session-sequence 생성]
    G --> H[temp write·fsync·atomic replace]
    H --> I[(patrol_report_outbox.json)]
    J[mark_published report ID] --> B
    B --> K[일치 pending만 삭제·원자 저장]
~~~

`patrol_report_adapter.py`

~~~mermaid
flowchart TD
    A[100 ms drain 호출] --> B{subscriber count ≥ 1}
    B -->|아니오| C[pending 유지]
    B -->|예| D[pending 순서대로 읽기]
    D --> E[PatrolReport 필드·ROS Time 변환]
    E --> F[RELIABLE publisher 호출]
    F -->|성공| G[report ID pending 삭제]
    F -->|예외| H[삭제하지 않고 다음 drain 대기]
~~~

`status_mission_bridge.py`

~~~mermaid
flowchart TD
    A[mission_status.json read] --> B{새 revision}
    B -->|아니오| C[변경 없음]
    B -->|예| D{MissionState enum 이름 유효}
    D -->|아니오| E[오류·마지막 정상 상태 유지]
    D -->|예| F[RobotStatusState mission 축 갱신]
    F --> G[command·mission·waypoint·reason snapshot 교체]
~~~

`status_reporter.py`

~~~mermaid
flowchart TD
    A[battery_status callback] --> B[RobotStatusState battery 축]
    C[battery_state callback] --> D[SOC·측정 시각]
    E[100 ms poll] --> F[MissionStatusBridge.refresh]
    E --> G[PatrolReportDrain.publish_pending]
    F --> H[변경 발행 gate]
    B --> H
    I[20 ms tick] --> J{Q-02 발행 시각}
    H --> J
    J -->|예| K[/robotN/robot_status]
    G --> L[/robotN/patrol_report]
    F -->|손상 파일| M[오류 로그·마지막 정상 상태 유지]
    G -->|미연결·발행 실패| N[pending 유지]
~~~

### 미션 보고 모듈 기술 선택 근거

| 선택 | 근거 | 적용 범위와 한계 |
|---|---|---|
| ROS 독립 domain 객체 | 공용 `patrol_interfaces`와 내부 실행 모델을 분리해 생성 메시지 없이도 개별 시험할 수 있다. | 실제 ROS 토픽·QoS·필드 adapter는 합의된 공용 메시지로 연결한다. |
| `@dataclass(frozen=True)` | worker와 향후 publisher 사이에 전달한 종료 결과가 나중에 바뀌지 않게 한다. | 공개 메시지 타입을 확정하는 장치가 아니다. |
| callable sink 주입 | 결과 검증과 저장 수단을 분리한다. | launch에서 robot별 영속 outbox sink를 연결한다. |
| lock과 in-flight/published 집합 | 같은 프로세스의 동시 호출에서 command 결과가 두 번 enqueue되는 것을 막는다. | 재시작 뒤에는 command store와 outbox의 영속 ID가 중복을 막는다. |
| outbox 선저장 | ROS subscriber가 없을 때도 임무 결과를 보존한다. | 수신 애플리케이션 ACK와 최종 삭제 기준은 TBD-IF-003이다. |
| 원자 교체·fsync | 전원 중단 시 부분 JSON을 정상 상태로 오인하지 않는다. | 디스크 자체 장애에서는 주행을 차단하고 오류를 남긴다. |
| subscriber 확인 후 drain | 명백히 수신자가 없는 상태에서 VOLATILE report를 버리지 않는다. | 연결만으로 DB 저장 완료를 보장하지 않으며 검토 요청서에서 ACK를 요청했다. |
| REJECTED 비발행 | PatrolReport의 확정 enum은 SUCCEEDED/FAILED/CANCELED 세 개뿐이다. | 명령 거부는 v1.0 `CommandCheck.REJECTED`로 전달하고 PatrolReport를 만들지 않는다. |

`command_store.py`

~~~mermaid
flowchart TD
    A[command_id·6필드 fingerprint] --> B[24시간+과거 최신 1,000개 보관 정리]
    B --> C{기존 ID}
    C -->|없음| D[temp 파일 write·fsync]
    D --> E[atomic replace·directory fsync]
    E --> F[NEW·부작용 실행 가능]
    C -->|같은 fingerprint| G[DUPLICATE]
    C -->|다른 fingerprint| H[CONFLICT]
    D -->|실패| I[StoreError·주행 차단]
    J[waypoint 성공] --> K[다음 index 같은 방식으로 저장]
~~~

## 미완료 연계와 시험 상태

- `patrol_interfaces/msg/MissionCommand`는 공용 패키지 의존성으로 사용한다.
  공용 패키지를 먼저 빌드·source한 뒤 ROS 노드를 기동한다. 구조화 ID,
  mission ID, 충돌 fingerprint와 보관 규칙, CommandCheck 수치와
  명령별 target 규칙은 v1.0 계약에 반영했다.
- 미션 상태는 AMR 내부 영속 `mission_status.json`으로 프로세스 경계를
  넘기며 공개 ROS 내부 토픽을 새로 만들지 않았다. `status_reporter`가 이를
  읽어 RobotStatus의 mission·command·waypoint·reason 필드를 만든다.
- TBD-IF-009의 `cmd_vel_safe → local_safety_supervisor → cmd_vel` 경로와
  Q-17 0.5초는 2026-09-08 AMR 회신에 따라 코드에 반영됐다.
- W1~W7 이동 단위 테스트는 수행할 수 있다. scan 완료 정의와 재개 지점은
  TBD-AMR-005라 기본 dwell은 0, resume은 disabled다.
- 활성 화재 집계와 audio Action adapter는 단위시험을 통과했다. Detection
  메시지·yaw·증적·화재음 계약이 열려 있어 event node는 BLOCKED이며
  `CR-AMR_09-07_19-10_Detection_증적_화재부저_계약_검토.md`에 기록했다.
- 실제 robot6 W1~W7 시험 launch와 명령 절차는 구현했다. 첫 실기 기동에서
  `mission_supervisor`와 worker의 전역 executor 동시 spin 충돌을 확인해
  supervisor 전용 executor로 분리했다. 수정 후 실제 장비 재시험은 남아
  있으며, 최종 IT-16은 local safety 결합 뒤 수행한다.
- `MissionReporter → 영속 outbox → status_reporter → PatrolReport` 연결은
  AMR-07 범위에서 완료했다. 수신 애플리케이션 ACK와 큐 삭제 기준은
  `CR-AMR_09-08_10-42_PatrolReport_ACK와_큐_삭제_조건_검토.md`의
  TBD-IF-003 잔여 결정 전까지 provisional 동작이다.

## 2026-09-08 검증 결과

- 당시 패키지 분리 전 `colcon build --packages-select patrol_interfaces patrol_amr --symlink-install`: PASS. 현재 검증 명령은 `colcon build --packages-select patrol_interfaces patrol_amr patrol_amr_safety --symlink-install`이다.
- 전체 Python 단위시험 207개: PASS
- AMR-07 격리 ROS 스모크: `/robot6/robot_status` 미션 실패 상태와
  `/robot6/patrol_report`의 ID·result·reason code·시각·최종 W4 수신,
  발행 후 pending 큐 삭제 PASS
- parser·영속 보관·W1~W7 순차 실행·실기 구동 gate·executor 분리 변경 후
  단위시험 62개 PASS
- 이벤트 기초 모듈 단위 테스트 9개와 subtest 3개 PASS
- AMR-07 결과 검증·미션 상태·원자 저장·outbox·ROS adapter·worker 연결
  단위시험 28개: PASS
- 신규 reporter 코드·시험 `ament_flake8`, reporter `ament_pep257`, 전체
  Python compileall: PASS
- ROS launch 파일 로드와 프로세스 생성: PASS
- 격리 domain의 `/robot6/mission_command` 구독 1개와 구조화 ID 실제
  pub/sub PASS; `safety_path_ready=false` 주행 차단 PASS
- 당시 safety 패키지 분리 전, 공용 `MissionCommand` 5종이 있는 팀 브랜치
  사본의 패키지 메타데이터를 `patrol_interfaces`로 바로잡은 격리 작업공간에서
  두 패키지 동시 빌드: PASS
- `/robot6/mission_command` 타입
  `patrol_interfaces/msg/MissionCommand`, RELIABLE/VOLATILE 구독 1개: PASS
- 유효한 `START_PATROL` 실제 토픽 발행 → `mission_supervisor` 콜백 수신 →
  `safety_path_ready=false` 주행 차단: PASS
- 공용 패키지와 패키지 메타데이터의 v1.0 통일: 완료. 각 PC 설치본의 manifest SHA-256 비교는 통합시험 시작 전에 수행한다.
- `hardware_patrol.launch.py --show-args`: PASS
- 토큰 누락 시 프로세스 기동 후 주행 차단 로그: PASS
- 첫 robot6 실기 기동: `Executor is already spinning` 재현, 원인 확인 및
  executor 분리 수정 완료; 수정 빌드 후 실제 장비 재시험 PENDING
- 실제 Nav2·도킹·robot1/robot6 실기 주행: NOT_RUN
- 최종 local safety 속도 경로 IT-16: TBD-IF-009 계약·로컬 게이트 반영 완료. 실제 Nav2·yaw 후보 결합과 robot1·robot6 실기 검증은 NOT_RUN
