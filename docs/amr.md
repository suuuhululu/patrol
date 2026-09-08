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
| 정상 순찰 | `src/patrol_amr/patrol_amr/scenarios/start_patrol.py:start_patrol`, `scenarios/patrol.py:PatrolScenario.run` | [0.4.0 구현 대조 완료](../src/patrol_amr/docs/mission_navigation.md#시나리오) · IT-02·07 |
| 안전구역 대피 | `src/patrol_amr/patrol_amr/scenarios/safe_zone.py:move_to_safe_zone` | [0.4.0 구현 대조 완료](../src/patrol_amr/docs/mission_navigation.md#시나리오) · 실제 후보 공급 TBD-CTRL-002 · IT-07·09 |
| 순찰 재개 | `src/patrol_amr/patrol_amr/scenarios/resume_patrol.py:resume_patrol` | [0.4.0 구현 대조 완료](../src/patrol_amr/docs/mission_navigation.md#시나리오) · 기본 비활성, TBD-AMR-005 |
| 도킹 | `src/patrol_amr/patrol_amr/scenarios/docking.py:dock`, `docking_runner.py:DockingRunner` | [0.4.0 구현 대조 완료](../src/patrol_amr/docs/mission_navigation.md#nav2와-도킹) · 센서 의미 TBD-AMR-004 · IT-13 |
| 감지·증적 | `src/patrol_amr/patrol_amr/fire_event_registry.py:FireEventRegistry`, `audio_note_sequence_adapter.py:AudioNoteSequenceAdapter` | [이벤트 기초 모듈 구현 대조](../src/patrol_amr/docs/mission_navigation.md#이벤트-기능-기초) · 입력 event node·yaw·증적은 TBD-AMR-001·TBD-IF-006·007·009 |
| 중단·복구 대응 | `src/patrol_amr/patrol_amr/scenarios/interruption.py:interrupt_navigation`, `mission_arbiter.py:MissionArbiter` | [0.4.0 구현 대조 완료](../src/patrol_amr/docs/mission_navigation.md#명령-콜백과-실행-수명) · STOP/CANCEL 차이 TBD-AMR-005 |
| mission_supervisor | `src/patrol_amr/patrol_amr/mission_supervisor.py:MissionSupervisor`, `mission_command_parser.py:MissionCommandParser`, `mission_command_callback.py:MissionCommandCallback`, `mission_worker.py:MissionWorker`, `mission_controller.py:MissionController` | [0.4.0 구현 대조 완료](../src/patrol_amr/docs/mission_navigation.md#명령-콜백과-실행-수명) · 구조화 ID·mission ID parser 반영 · CommandCheck 세부 TBD-IF-001 |
| local_safety_supervisor | `src/patrol_amr/patrol_amr/local_safety_supervisor.py:SafetyGate`, `create_node_class` 내 ROS callbacks | [0.4.0 안전·미션 결합 구현 대조 완료](../src/patrol_amr/docs/mission_navigation.md#ros-구성과-설정) · IT-04·11·16 |
| Nav2 pose 실행 | `src/patrol_amr/patrol_amr/navigation_adapter.py:NavigationAdapter`, `nav2_goal_runner.py:Nav2GoalRunner` | [0.4.0 구현 대조 완료](../src/patrol_amr/docs/mission_navigation.md#nav2와-도킹) · 최종 속도 연결 TBD-IF-009 · IT-16 |
| 실기 구동 gate | `motion_authorization.py`, `robot_readiness.py`, `robot_readiness_callbacks.py`, `motion_gate.py`, `launch/hardware_patrol.launch.py` | [0.4.0 구현 대조 완료](../src/patrol_amr/docs/mission_navigation.md#ros-구성과-설정) · robot6 단일 기능 시험 경로 · 최종 속도 연결 TBD-IF-009 |
| 명령·checkpoint 영속 저장 | `src/patrol_amr/patrol_amr/command_store.py:CommandStore` | [0.4.0 구현 대조 완료](../src/patrol_amr/docs/mission_navigation.md#내부-상태와-영속성) · 24시간 이내 전체+과거 최신 1,000개 보관 반영 · IT-02 |
| 미션 내부 상태 | `src/patrol_amr/patrol_amr/mission_state.py:MissionStateTracker` | [0.4.0 구현 대조 완료](../src/patrol_amr/docs/mission_navigation.md#내부-상태와-영속성) · RobotStatus 연계 TBD-IF-003 |
| 위치·배터리·RobotStatus/PatrolReport | 실제 코드 파일·모듈별 행으로 분리하여 기록 | 미작성 |

각 그림에는 시작 조건, 함수·콜백 호출 순서, 조건별 분기, 외부 Action·토픽 송수신, 성공·실패·취소·안전 중단, 종료·복구 대기 경로를 표시한다. timeout·재시도 수치와 enum을 복제하지 않고 Q-ID·TBD-ID를 참조한다. 구현 대조 시 코드 버전과 관련 통합시험 ID를 기록한다.

0.4.0 미션 구현은 사용자가 제공한 팀원 차트의 파일 분리 방향을 반영했다. 차트에서 내부 인터페이스 초안으로 표시한 `mission_status`, `motion_authorized`, `cmd_vel_safe`는 공용 문서의 TBD-IF-003·009가 해결되기 전까지 ROS 계약으로 확정하지 않는다. 검토 요청은 `change_requests/CR-AMR_09-07_13-54_미션_내부_연계_검토.md`에 기록했다.

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

## 1.3 AMR 노드 통합 다이어그램과 담당 경계

아래 그림은 `robot1`과 `robot6`에 각각 같은 구성을 적용한다. 박성현 담당
미션·내비게이션 코드는 파란색, 조정묵 담당으로 전달받은 로컬 안전·배터리·
Keepout 코드는 초록색으로 표시한다. 담당표와 팀원 차트에서 소유자가 서로
다른 항목은 노란색 연계 경계로 남긴다. 기존 TurtleBot4/Nav2 구성은
회색이다. 실선은 현재 공용 문서에서 방향과 역할이 확인된 연결이고,
점선은 토픽·타입·필드 또는 remap 합의가 필요한 연결이다.

~~~mermaid
flowchart LR
    subgraph EXT[외부 시스템]
        CONTROL[관제]
        TOKEN["/control/drive_token"]
        HEART["/control/heartbeat"]
        ESTOP["/control/estop"]
        BATTERY["/robotX/battery_state"]
        OAK[OAK-D 영상]
    end

    subgraph AMR[AMR robot1 또는 robot6]
        subgraph PARK[박성현 · 미션·내비게이션 통합]
            MS[mission_supervisor ROS 노드]
            PARSER[mission_command_parser.py<br/>계약 검증·내부 변환]
            CB[mission_command_callback.py<br/>parser 호출·큐 제출]
            ARB[mission_arbiter.py<br/>단일 임무·중단 신호]
            WORK[mission_worker.py<br/>영속 claim·실행 수명]
            CTRL[mission_controller.py<br/>시나리오 선택]
            SCEN[scenarios/<br/>순찰·대피·재개·도킹·중단]
            NAVGW[navigation_adapter.py<br/>Nav2·Dock gateway]
            MSTATE[mission_state.py<br/>mission snapshot]
            REPORT[mission_reporter.py<br/>종료 결과 내부 모델·향후 ROS adapter]
            FIREREG[fire_event_registry.py<br/>활성 화재·다중 화재 판단]
            AUDIO[audio_note_sequence_adapter.py<br/>부저 Action start·cancel]
            MAPCFG[patrol_params.yaml<br/>W1~W7 좌표]
            WPREPO[waypoint_repository.py<br/>7개·순서·유한값 검증]
            STORE[(command_store.json<br/>command ID·checkpoint)]
        end

        NAV2[기존 Nav2 / AMCL<br/>NavigateToPose]
        COSTMAP[global/local costmap]
        DRIVER[TurtleBot4 구동부]

        subgraph TEAM[팀원 담당 연계 영역]
            SAFE[local_safety_supervisor<br/>최종 속도 단일 발행]
            BATMON[battery_monitor]
            KOF[Keepout mask·filter info<br/>costmap filter 구성]
            DETECT[로컬 Detection·증적]
        end

        subgraph SHARED[공동 연계·소유자 확인 영역]
            IFACE[patrol_interfaces<br/>MissionCommand·RobotStatus·PatrolReport]
            STATUS[status_reporter<br/>RobotStatus 전체 집계]
            STATUSFILE[(mission_status.json)]
            OUTBOX[(patrol_report_outbox.json)]
        end
    end

    CONTROL -->|/robotX/mission_command<br/>MissionCommand| IFACE --> MS
    MS --> CB --> PARSER --> ARB --> WORK --> CTRL --> SCEN --> NAVGW
    WORK <--> STORE
    WORK --> MSTATE
    MAPCFG --> WPREPO --> SCEN
    MAPCFG --> NAVGW
    NAVGW -->|내부 NavigateToPose·Dock Action| NAV2
    NAV2 -->|cmd_vel_safe<br/>TwistStamped| SAFE
    SAFE -->|cmd_vel<br/>Twist| DRIVER
    SAFE -->|motion_allowed| MS

    TOKEN --> SAFE
    TOKEN --> MS
    HEART --> SAFE
    ESTOP --> SAFE
    BATTERY --> BATMON
    BATMON -.->|battery 상태 내부 연계<br/>TBD-IF-003| STATUS
    MSTATE --> REPORT
    MSTATE --> STATUSFILE --> STATUS
    REPORT --> OUTBOX --> STATUS
    SAFE -.->|safety_state·motion_stopped<br/>TBD-IF-003| STATUS
    NAV2 -.->|map pose·유효성<br/>TBD-IF-003| STATUS
    STATUS -->|/robotX/robot_status| CONTROL
    STATUS -->|/robotX/patrol_report<br/>PatrolReport| CONTROL

    CONTROL -.->|Nav2 parameter API| COSTMAP
    KOF --> COSTMAP --> NAV2
    MAPCFG -.->|map·waypoint·dock 좌표 정합 확인| COSTMAP
    OAK --> DETECT
    DETECT -.->|확정 fire ID<br/>TBD-IF-006| FIREREG
    FIREREG -->|ON/OFF 결정| AUDIO
    AUDIO -->|robotX/audio_note_sequence Action| DRIVER
    DETECT -.->|cmd_vel_yaw 후보<br/>중재 TBD-AMR-001| MS
    DETECT -.->|확정 이벤트·증적<br/>TBD-IF-006·007| CONTROL

    classDef park fill:#dbeafe,stroke:#2563eb,color:#172554;
    classDef team fill:#dcfce7,stroke:#16a34a,color:#14532d;
    classDef shared fill:#fef3c7,stroke:#d97706,color:#78350f;
    classDef existing fill:#f3f4f6,stroke:#6b7280,color:#111827;
    classDef external fill:#ffedd5,stroke:#ea580c,color:#7c2d12;
    class MS,PARSER,CB,ARB,WORK,CTRL,SCEN,NAVGW,MSTATE,REPORT,FIREREG,AUDIO,MAPCFG,WPREPO,STORE park;
    class SAFE,BATMON,KOF,DETECT team;
    class IFACE,STATUS shared;
    class NAV2,COSTMAP,DRIVER existing;
    class CONTROL,TOKEN,HEART,ESTOP,BATTERY,OAK external;
~~~

### 박성현 담당 로직

사용자가 정한 역할을 우선하면 박성현의 핵심 범위는 **미션 명령을 받아
W1~W7 순찰·대피·재개·도킹을 Nav2로 실행하고, 그 결과를 상태와 보고로
연결하는 구간**이다. 엑셀의 두 시트 및 팀원 차트에서 담당자가 다르게
적힌 항목은 공동 연계로 표시하고 코드 소유자를 확정한 뒤 병합한다.

| 우선순위 | 만들어야 하는 로직 | 현재 0.4.0 상태 | 관련 코드·미정 사항 |
|---|---|---|---|
| 1 | 미션 FSM과 단일 임무 실행 수명 관리 | 기본 구조·단위시험 완료 | `mission_supervisor.py`, `mission_worker.py`, `mission_controller.py` |
| 2 | W1~W7 순찰, 성공 waypoint checkpoint, 중단·재개 정책 | 순찰 완료, 재개 정책 대기 | `scenarios/patrol.py`, `scenarios/resume_patrol.py`; TBD-AMR-005 |
| 3 | 차량 이벤트의 대피 명령을 safe-zone pose로 실행하고 순찰과 연결 | 실행 로직 완료 | `scenarios/safe_zone.py`; 안전구역 계산·공급은 관제 |
| 4 | Nav2 goal 전송·취소·timeout·결과 분류 | goal 실행부 완료 | `nav2_goal_runner.py`; 실제 Nav2 통합시험 필요 |
| 5 | DOCK/UNDOCK를 미션 상태와 연결하고 실패·timeout 처리 | 기본 구현·단위시험 완료 | `docking_runner.py`; AMR-13 공동 연계, TBD-AMR-004·005 |
| 6 | map, W1~W7, safe zone, dock pose의 frame·좌표·yaw 정합 | W1~W7 설정 존재, 나머지 현장 검증 필요 | AMR-08; `patrol_params.yaml`에서 단일 관리 |
| 7 | mission·waypoint·결과 snapshot과 RobotStatus의 미션 필드 생성 | 영속 snapshot과 status_reporter 미션 필드 연결 완료 | `mission_state.py`, `mission_status_store.py`, `status_mission_bridge.py`; AMR-06의 나머지 입력은 후속 |
| 8 | 임무 종료 시 PatrolReport를 command_id와 연결해 한 번 발행 | AMR-07 구현·빌드·격리 ROS 스모크 완료 | `mission_reporter.py`, `patrol_report_outbox.py`, `patrol_report_adapter.py`, `status_reporter.py`; 애플리케이션 ACK는 TBD-IF-003 |
| 9 | MissionCommand 검증·중복 제거·중재의 미션 측 연결 | 구현·단위시험 완료 | AMR-05 담당 표기가 시트별로 달라 소유자 확인 필요 |
| 10 | robot1·robot6 공통 launch와 대피·재개·안전·복구 통합시험 | 빌드·단위시험 완료, 실기 미실행 | T-01·02·04·05 공동 범위 |

박성현 로직의 실행 경계는 `MissionCommand → 검증·중복 제거 → 시나리오
선택 → Nav2 Action → 미션 상태·PatrolReport`이다. `RobotStatus`에서는
미션 관련 필드와 입력 adapter를 만들고, `status_reporter`에서 배터리 상태와
미션 상태를 합친다. 안전·pose·token의 실제 입력 연결은 각 담당 모듈과 후속
단일 기능 시험으로 확장한다.

다음 로직은 박성현이 새로 중복 구현하지 않는다. DriveToken lease,
heartbeat, E-stop, 장애물과 여러 속도 후보의 최종 중재는
`local_safety_supervisor`, 배터리 enum은 `battery_monitor`, Keepout
mask·filter 생성과 차량 이벤트 시 2·3·5·8 구역 on/off는 조정묵 담당이다.
박성현은 해당 출력과 인터페이스를 소비하고 통합시험을 담당한다.

## 2. 명령과 임무 실행

1. 수신 namespace와 robot_id, 명령 enum, 필수 인자를 검증한다. 미정 인자 규칙은 TBD-IF-001을 따른다.
2. 영속 command_id 기록을 조회해 동일 명령을 다시 실행하지 않는다.
3. 주행이 필요한 명령은 유효 token 및 로컬 안전 조건을 통과해야 한다.
4. 필요할 때 mission_supervisor가 내부 Nav2 Action을 호출한다. 관제가 Nav2 Action을 직접 실행하는 경로를 만들지 않는다.
5. 진행 상태를 RobotStatus에 반영하고 종료 시 PatrolReport를 생성한다.

START_PATROL, MOVE_TO_SAFE_ZONE, RESUME_PATROL, DOCK는 실행 목적을 구분한다. STOP은 재개 상태를 보존하고 CANCEL은 임무를 종료한다. 우선순위는 STOP → MOVE_TO_SAFE_ZONE → DOCK → CANCEL → RESUME_PATROL → START_PATROL이다. 실행 중·대기 중 preemption과 CommandCheck/PatrolReport 연결은 [AMR 명령 중재 세부 계약 요청서](change_requests/CR-AMR_09-07_18-58_명령_중재_세부_계약_검토.md)에서 합의한 뒤 구현한다.

Operational/Mission/Docking은 별개 상태 축이다. interfaces.md의 enum을 따른다. 순찰→대피→대기→재개, 복귀→도킹→완료/실패 흐름은 기준이나 모든 상태 쌍 사이의 전이가 허용된다는 뜻은 아니다. 상세 전이표는 TBD-AMR-005다.

## 3. 로컬 안전과 속도 출력

local_safety_supervisor가 `/{robot}/cmd_vel` 최종 속도 발행권을 가진다. Nav2나 yaw 정렬 기능이 안전 출력을 우회하지 않도록 한다. TBD-IF-009는 2026-09-08 결정됐다. Nav2 `collision_monitor`는 `/{robot}/cmd_vel_safe`(`TwistStamped`)를 발행하고, local_safety_supervisor가 token·E-stop·Q-17을 적용해 `/{robot}/cmd_vel`(`Twist`)로 변환한다. yaw 후보 `/{robot}/cmd_vel_yaw`의 중재 정책은 TBD-AMR-001에 남다.

- 유효하지 않은 token은 주행에 사용하지 않는다. 만료·회수 시 신규 주행을 막고 안전 정지한다.
- token의 sequence·holder·message age를 확인한다. 로컬 lease 경과는 Q-01을 따른다.
- 새 token만 수신했다고 임무를 자동 시작하지 않는다.
- E-stop 활성화는 즉시 반영한다. 물리 E-stop latch는 수동 reset 전까지 유지한다.
- token·heartbeat·장애물 원인이 사라진 뒤의 해제 결정은 관제가 한다. 해제 조건 유지 시간은 Q-10이다.
- heartbeat 상세 계약은 TBD-IF-004다. 임의 timeout을 추가하지 않는다.
- 주행 후보의 `header.stamp` age가 Q-17 0.5초를 초과하면 최종 속도 0을 발행한다.

정지 감속 방식·허용 정지 거리·센서 장애에 대한 속도 출력 규칙은 TBD-AMR-006이다. 안전 정지 요청과 실제 정지 관측을 구분한다.

## 4. Nav2·위치·Keepout

map frame의 pose·측정 시각·covariance를 제공한다. pose가 무효이면 마지막 유효 위치를 보존하되 현재 위치로 사용하지 않는다. 참고 위치 검증과 실제 주행 재개 기준은 Q-06과 Q-05로 구분한다.

AMR2 LiDAR 위치 검증 기준은 Q-06이며 대상·계산 주체·통신 계약이 불명확하다(TBD-AMR-002). 이를 두 로봇에 임의로 일반화하지 않는다.

Keepout은 각 로봇의 global/local costmap에 필요하다. 계획 구성 예시는 다음과 같다.

~~~yaml
filters: ["keepout_filter"]
keepout_filter:
  plugin: "nav2_costmap_2d::KeepoutFilter"
  enabled: true
  filter_info_topic: costmap_filter_info
~~~

mask server와 costmap_filter_info_server도 필요하다. 이는 예시이며 실제 parameter 파일 변경 승인이 아니다. 장비별 Keepout 적용 여부는 TBD-ARCH-001과 TBD-IF-008에 따라 실제 설정을 확인한다.

안전구역은 Q-08 조건을 모두 충족해야 한다. 차량 동선과의 거리를 우선하고 다음으로 경로 비용을 평가한다. 후보가 없으면 현재 위치에서 정지하고 SAFE_ZONE_NOT_FOUND를 보고한다. 계산 주체·지도/차량 동선 공급자는 TBD-CTRL-002다.

## 5. 배터리와 도킹

SOC·충전 방향에 따른 Battery enum은 interfaces.md 8절과 Q-11을 따른다. 무효·미수신은 UNKNOWN이다. 배터리 센서 신선도와 전류 부호·충전 여부 판정은 TBD-AMR-003이다.

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

화재 확정 시 부저 ON, 동일 활성 event_id 중복 처리 금지, 도킹 완료 후 OFF라는 정책을 유지한다. 활성 화재 ID 집계와 실기 성공한 `audio_note_sequence` Action adapter는 분리 구현했다. Q-12의 CHARGING 연속 확인, 과거 event 중복 보관, 화재음 패턴과 자동 제어 연결은 TBD-AMR-004·TBD-IF-006이며 [Detection·증적·화재 부저 계약 요청서](change_requests/CR-AMR_09-07_19-10_Detection_증적_화재부저_계약_검토.md)에서 검토한다.

## 7. 상태·결과·진단

RobotStatus의 발행·변경 rate는 Q-02다. PatrolReport는 명령과 연결해 SUCCEEDED/FAILED/CANCELED 및 실패·취소 reason을 제공한다. AMR-07은 subscriber가 없을 때 영속 큐에 보존하고 연결 후 같은 report ID로 발행한다. 수신 애플리케이션 저장 완료 ACK와 최종 큐 삭제 조건은 [TBD-IF-003 검토 요청서](change_requests/CR-AMR_09-08_10-42_PatrolReport_ACK와_큐_삭제_조건_검토.md)에 남겼다.

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
| TBD-AMR-003 | 배터리 입력 신선도, 충전 방향·무효값 판정 | AMR·관제 | OPEN |
| TBD-AMR-004 | 도킹 완료·CHARGING·높은 SOC 관계, 화재 부저 제어자·해제 계약 | AMR·관제 | OPEN |
| TBD-AMR-005 | 상세 상태 전이·STOP/CANCEL 차이·재개 지점·waypoint/scan 정책 | AMR·관제 | OPEN |
| TBD-AMR-006 | 로컬 정지 감속·거리·장애물 및 센서 실패 판정 | AMR·관제 | OPEN |

해결 시 결정 근거·일자와 [수정 요청서](change_requests/README.md)를 기록한다.
