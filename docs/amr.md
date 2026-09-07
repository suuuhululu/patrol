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
| 정상 순찰 | 구현 시 기록 | 미작성 |
| 안전구역 대피 | 구현 시 기록 | 미작성 |
| 순찰 재개 | 구현 시 기록 | 미작성 |
| 도킹 | 구현 시 기록 | 미작성 |
| 감지·증적 | 구현 시 기록 | 미작성 |
| 중단·복구 대응 | 구현 시 기록 | 미작성 |
| mission_supervisor | 구현 시 기록 | 미작성 |
| local_safety_supervisor | 구현 시 기록 | 미작성 |
| drive_token_guard.py | [src/patrol_amr/patrol_amr/drive_token_guard.py](../src/patrol_amr/patrol_amr/drive_token_guard.py) · `DriveTokenGuard.observe`·`authority` | [3.1절](#31-drive_token_guardpy--구현-대조-완료) 구현 대조 완료 |
| battery_monitor.py | [src/patrol_amr/patrol_amr/battery_monitor.py](../src/patrol_amr/patrol_amr/battery_monitor.py) · `classify_observation`·`BatteryStateModel.update` | [5.1절](#51-battery_monitorpy--구현-대조-완료) 구현 대조 완료 |
| 공통 Nav2 연결·위치·상태/결과 발행 | 실제 코드 파일·모듈별 행으로 분리하여 기록 | 미작성 |

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

1. 수신 namespace와 robot_id, 명령 enum, 필수 인자를 검증한다. 미정 인자 규칙은 TBD-IF-001을 따른다.
2. 영속 command_id 기록을 조회해 동일 명령을 다시 실행하지 않는다.
3. 주행이 필요한 명령은 유효 token 및 로컬 안전 조건을 통과해야 한다.
4. 필요할 때 mission_supervisor가 내부 Nav2 Action을 호출한다. 관제가 Nav2 Action을 직접 실행하는 경로를 만들지 않는다.
5. 진행 상태를 RobotStatus에 반영하고 종료 시 PatrolReport를 생성한다.

START_PATROL, MOVE_TO_SAFE_ZONE, RESUME_PATROL, DOCK는 실행 목적을 구분한다. STOP과 CANCEL의 정확한 임무 보존·종료 차이, 명령 대체 우선순위, 순찰 재개 지점은 TBD-AMR-005 및 TBD-CTRL-001에서 합의한다.

Operational/Mission/Docking은 별개 상태 축이다. interfaces.md의 enum을 따른다. 순찰→대피→대기→재개, 복귀→도킹→완료/실패 흐름은 기준이나 모든 상태 쌍 사이의 전이가 허용된다는 뜻은 아니다. 상세 전이표는 TBD-AMR-005다.

## 3. 로컬 안전과 속도 출력

local_safety_supervisor가 최종 속도 발행권을 가진다. Nav2나 yaw 정렬 기능이 안전 출력을 우회하지 않도록 한다. 구체적인 토픽·타입은 TBD-IF-009다.

- 유효하지 않은 token은 주행에 사용하지 않는다. 만료·회수 시 신규 주행을 막고 안전 정지한다.
- token의 sequence·holder·message age를 확인한다. 로컬 lease 경과는 Q-01을 따른다.
- 새 token만 수신했다고 임무를 자동 시작하지 않는다.
- E-stop 활성화는 즉시 반영한다. 물리 E-stop latch는 수동 reset 전까지 유지한다.
- token·heartbeat·장애물 원인이 사라진 뒤의 해제 결정은 관제가 한다. 해제 조건 유지 시간은 Q-10이다.
- heartbeat 상세 계약은 TBD-IF-004다. 임의 timeout을 추가하지 않는다.

정지 감속 방식·허용 정지 거리·센서 장애에 대한 속도 출력 규칙은 TBD-AMR-006이다. 안전 정지 요청과 실제 정지 관측을 구분한다.

### 3.1 drive_token_guard.py — 구현 대조 완료

2026-09-07: 사용자 3단계 진행 요청에 따라 [drive_token_guard.py](../src/patrol_amr/patrol_amr/drive_token_guard.py)에 [인터페이스 3절](interfaces.md#3-drivetoken)의 수락 규칙과 Q-01 로컬 lease를 구현했다. ROS 노드가 아니라 6단계 `local_safety_supervisor`가 사용하는 일반 Python 모듈이며, 이 파일은 속도를 발행하지 않는다.

- `DriveTokenGuard.observe(token, holder_robot_id, lease_seconds, sequence, now)`: 관측 하나를 적용하고 수락·폐기 사유를 `TokenVerdict`로 반환한다. `now`는 호출자가 전달하는 로컬 monotonic 초다. 다른 holder의 토큰은 폐기하고, 빈 token은 회수로 처리해 즉시 무효화하며, 보유 token과 다른 문자열은 기존 token을 즉시 무효화한다. `sequence`가 마지막 수락 값 이하이거나 lease가 유한한 양수가 아니면 폐기한다.
- 폐기된 메시지는 lease 만료 시각을 바꾸지 않는다. 수신 사실만으로 lease를 연장하지 않는다는 3절 규칙을 이렇게 만족한다. 갱신은 수락된 관측에서만 일어난다.
- `DriveTokenGuard.authority(now)`: 보유 token이 없으면 `MISSING`, lease 경과면 `EXPIRED`, 그 밖에는 `GRANTED`다. 각각 [인터페이스 5절](interfaces.md#5-patrolreport)의 600 DRIVE_TOKEN_MISSING과 601 DRIVE_TOKEN_EXPIRED에 대응한다. 공용 코드 목록에 회수 전용 값이 없으므로 회수도 `MISSING`이며, AMR 내부 `DRIVE_TOKEN_REVOKED` 로그는 `revoked_last`로 구분한다.
- `authority`·`remaining_lease`·`drive_allowed`는 조회 전용이라 시각을 소비하지 않는다. 한 제어 주기 안에서 같은 시각을 여러 번, 임의 순서로 물어볼 수 있다. 시계 역행 검사는 상태를 바꾸는 `observe`에만 적용한다.
- `duration_to_seconds(sec, nanosec)`는 `builtin_interfaces/Duration` 필드 쌍을 초로 바꾼다. lease 값은 메시지의 `lease_duration`을 사용하며 Q-01의 1.0초는 관제 발행 기준값이다.
- 주행 허용 여부만 보고하고 주행을 시작하지 않는다. 새 token 수신만으로 자동 출발하지 않는다는 3절 규칙은 6단계 supervisor가 최종 보장한다.

**TBD-IF-002로 남긴 부분** — 추측해 구현하지 않았다.

- `sequence` 재시작·uint32 wraparound 처리가 없다. 마지막 수락 값 이하는 그대로 폐기하므로, 관제가 sequence를 되돌리면 확정 전까지 주행 권한이 살아나지 않는다.
- token 문자열이 바뀌면서 sequence가 함께 재설정되면 기존 token은 무효화되고 새 token은 폐기된다. 결과는 권한 없음이며 이는 안전 방향의 기본값이다.
- 공통 토픽에서 다른 holder로 교체될 때 현재 권한을 앞당겨 끊지 않는다. 갱신이 멈추면 Q-01 lease 안에서 만료된다. 즉시 무효화가 필요한지는 미확정이다.
- 송신 `header.stamp`를 이용한 message age 검증은 구현하지 않았다. 3절이 보장되지 않은 시간 동기화의 직접 비교를 금지하고 결합 방식을 TBD-IF-002로 두었기 때문이다. 현재 경과 판정은 로컬 monotonic lease 하나뿐이다.

**구현 대조 완료** — 2026-09-07 현재 코드 기준. 패키지 실행 등록은 9단계에서 추가한다.

~~~mermaid
flowchart TD
    MSG[drive_token 관측 / observe] --> H{holder_robot_id 일치?}
    H -->|아니오| OTH[OTHER_HOLDER 폐기 / 권한·sequence 불변]
    H -->|예| EMP{token 빈 문자열?}
    EMP -->|예| REV[REVOKED / 즉시 무효화 / revoked_last 설정]
    EMP -->|아니오| CHG{보유 token 과 다른 문자열?}
    CHG -->|예| INV[기존 token 즉시 무효화 / last_sequence 유지]
    CHG -->|아니오| SEQ
    INV --> SEQ{sequence 가 마지막 수락 값 초과?}
    SEQ -->|아니오| STL[STALE_SEQUENCE 폐기 / lease 연장 없음]
    SEQ -->|예| LS{lease 가 유한한 양수?}
    LS -->|아니오| BAD[INVALID_LEASE 폐기]
    LS -->|예| ACC[ACCEPTED / 만료 시각 = now + lease]
    Q[제어 주기 조회 / authority] --> HAS{보유 token 있음?}
    HAS -->|아니오| MIS[MISSING / 600 DRIVE_TOKEN_MISSING]
    HAS -->|예| EXP{만료 시각 도달?}
    EXP -->|예| EXD[EXPIRED / 601 DRIVE_TOKEN_EXPIRED]
    EXP -->|아니오| GRA[GRANTED / 주행 허용]
~~~

검증: [단위시험](../tests/test_drive_token_guard.py)은 lease 경계와 갱신, 폐기 메시지의 lease 미연장, 다른 holder·역행 sequence·무효 lease 폐기, 회수와 token 교체의 즉시 무효화, sequence 하한 유지, 호출자 인자 오류, 조회의 순서 무관성을 확인한다. 실행 명령은 저장소 루트에서 `python3 -m unittest discover -s tests -p test_drive_token_guard.py -v`다. [IT-03·IT-04](integration.md#4-통합시험-명세)의 로컬 판정 부분이며 관제 연동 통합시험은 미실행이다.

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

RobotStatus의 발행·변경 rate는 Q-02다. PatrolReport는 명령과 연결해 SUCCEEDED/FAILED/CANCELED 및 실패·취소 reason을 제공한다. 통신 두절 후 결과 전달 방식은 TBD-IF-003이다.

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
