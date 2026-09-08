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
| estop_guard.py | [src/patrol_amr/patrol_amr/estop_guard.py](../src/patrol_amr/patrol_amr/estop_guard.py) · `EStopGuard.observe`·`stopped` | [3.2절](#32-estop_guardpy--구현-대조-완료) 구현 대조 완료 |
| motion_guard.py | [src/patrol_amr/patrol_amr/motion_guard.py](../src/patrol_amr/patrol_amr/motion_guard.py) · `MotionGuard.evaluate` | [3.3절](#33-motion_guardpy--구현-대조-완료) 구현 대조 완료 (축소 범위) |
| local_safety_supervisor.py | [src/patrol_amr/patrol_amr/local_safety_supervisor.py](../src/patrol_amr/patrol_amr/local_safety_supervisor.py) · `SafetyGate`·`LocalSafetySupervisor` | [3.4절](#34-local_safety_supervisorpy--구현-대조-완료-축소-범위) 구현 대조 완료 (축소 범위) |
| battery_monitor.py | [src/patrol_amr/patrol_amr/battery_monitor.py](../src/patrol_amr/patrol_amr/battery_monitor.py) · `classify_observation`·`BatteryStateModel.update` | [5.1절](#51-battery_monitorpy--구현-대조-완료) 구현 대조 완료 |
| robot_status_state.py | [src/patrol_amr/patrol_amr/robot_status_state.py](../src/patrol_amr/patrol_amr/robot_status_state.py) · `RobotStatusState.update_states`·`observe_pose`·`observe_odometry`·`snapshot` | [7.1절](#71-robot_status_statepy--구현-대조-완료) 구현 대조 완료 |
| status_reporter.py | [src/patrol_amr/patrol_amr/status_reporter.py](../src/patrol_amr/patrol_amr/status_reporter.py) · `PublicationGate`·`StatusReporter` | [7.2절](#72-status_reporterpy--구현-대조-완료-축소-범위) 구현 대조 완료 (축소 범위) |
| 공통 Nav2 연결·위치·결과 발행 | 실제 코드 파일·모듈별 행으로 분리하여 기록 | 미작성 |

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
- token의 `control_session_id`·`token_id`·`holder_robot_id`·`message_sequence`를 확인한다. 로컬 lease 경과는 Q-01을 따른다.
- 새 token만 수신했다고 임무를 자동 시작하지 않는다.
- E-stop 활성화는 즉시 반영한다. 물리 E-stop latch는 수동 reset 전까지 유지한다.
- token·heartbeat·장애물 원인이 사라진 뒤의 해제 결정은 관제가 한다. 해제 조건 유지 시간은 Q-10이다.
- heartbeat 상세 계약은 TBD-IF-004다. 임의 timeout을 추가하지 않는다.

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

- `EStopGuard(robot_id)`는 어느 로봇의 상태인지 명시한다. `observe(target_robot_id, active, reason, latched, sequence)`는 새 [인터페이스 3.1절](interfaces.md#31-heartbeat와-e-stop)의 필드명을 그대로 사용하고 `ACCEPTED`·`OTHER_TARGET`·`STALE_SEQUENCE`를 반환한다.
- `active`는 즉시 반영하고 `stopped`는 `active or latched`다. 따라서 물리 latch가 남아 있으면 active=false가 와도 정지를 유지한다. 자동 해제 조건 3초 연속 판정은 관제(Safety Arbiter)가 하므로 이 모듈은 로컬 해제 타이머를 두지 않는다.
- 관측 전 기본 상태는 정지(`stopped=True`)다. `battery_monitor`의 초기 UNKNOWN, `DriveTokenGuard`의 초기 MISSING과 같은 안전 기본값이다.
- `reason` enum 숫자는 TBD-IF-004이므로 뜻을 붙이지 않고 uint8 원값으로 저장한다. `latched`도 관제 값을 반영한다.
- 공통 토픽에서 다른 로봇을 대상으로 한 메시지는 sequence 하한만 갱신하고 상태에는 적용하지 않는다. 전체 대상 문자열은 아직 TBD이므로 임의의 `all` 값을 만들지 않는다. 알 수 없는 대상은 `OTHER_TARGET`이며 기본 정지를 해제하지 않는다.
- `observe()`는 로그 이름을 반환하지 않는다. 호출자가 호출 전후로 `.stopped`를 비교해 상태 전이를 판정한다. 모듈은 `EVENT_ACTIVATED`·`EVENT_AUTO_RELEASED` 문자열만 정의해 둔다.

**미구현으로 남긴 부분**

- E-stop `reason` 정수 매핑과 전체 대상 문자열. TBD-IF-004가 정해지면 상수와 전체 대상 처리를 추가한다.
- 물리 E-stop의 로컬 방어적 latch/reset API. 현재 `latched`는 Safety Arbiter 결과를 반영하며 수동 reset 요청 경로는 TBD-IF-004다.

**구현 대조 완료** — 2026-09-07 현재 코드 기준. 패키지 실행 등록은 9단계에서 추가한다.

~~~mermaid
flowchart TD
    MSG[estop 관측 / observe] --> SEQ{sequence 가 마지막 수락 값 초과 또는 최초?}
    SEQ -->|아니오| STL[STALE_SEQUENCE 폐기 / 상태 불변]
    SEQ -->|예| SET[공통 stream sequence 하한 갱신]
    SET --> TARGET{target_robot_id 가 자신?}
    TARGET -->|아니오| OTHER[OTHER_TARGET / 상태 불변]
    TARGET -->|예| ACC[active·reason·latched 반영 / ACCEPTED]
    ACC --> STOPPED[stopped = active OR latched]
    Q[호출자: observe 전후 stopped 비교] --> T1{False → True?}
    T1 -->|예| EA[EVENT_ACTIVATED 로그]
    T1 -->|아니오| T2{True → False?}
    T2 -->|예| ER[EVENT_AUTO_RELEASED 로그]
~~~

**15단계 추가 — 물리 E-stop 로컬 latch(2026-09-08).** [Q-10](../interfaces.md#9-qos와-공통-시간거리-기준)과 [interfaces.md 3.1절](../interfaces.md)이 "물리 E-stop은 수동 reset까지 latch"를 문장으로 확정해 두었다. 관제가 보낸 `latched`를 그대로 비추기만 하면 이 문장을 지킬 수 없다 — 관제가 나중에 `latched=false`를 보내거나 발행을 멈추면, 아무도 버튼을 만지지 않았는데 로봇이 다시 움직인다.

- 수락된 `latched=true` 관측이 이 가드가 소유한 latch를 건다. **들어오는 메시지로는 내려가지 않는다.** `reset_local_latch()`만 내린다.
- `stopped`는 `active` 또는 arbiter의 `latched` 또는 로컬 latch 중 하나라도 참이면 참이다. 셋을 분리해 두었으므로 reset은 로컬 latch만 내리고 활성 E-stop이나 arbiter의 주장을 덮어쓰지 않는다.
- 다른 로봇 대상 메시지와 역순 sequence 메시지는 latch를 걸지 않는다. 기존 폐기 규칙을 그대로 통과한 관측만 반영한다.

**남긴 부분 — reset을 호출할 경로.** TBD-IF-004의 잔여 항목에 수동 reset 요청 계약(토픽인지 서비스인지, 누가 보낼 수 있는지, 무엇이 승인하는지)이 남아 있다. 임의로 만들면 물리 E-stop을 푸는 수단을 추측으로 시스템에 넣는 셈이다. 그래서 `reset_local_latch()`는 ROS 호출자가 없는 메서드로 두었고, **그 결과 latch가 걸린 로봇은 노드를 재시작해야 풀린다.** 안전한 방향이며, TBD-IF-004를 닫아야 할 이유이지 추측할 이유가 아니다.

검증: [단위시험](../tests/test_estop_guard.py) 19건은 관측 전 안전 기본값, 자기 대상 active·reason·latched 반영, 다른 로봇 대상 미적용, 공통 sequence 하한, 역순·중복 폐기, uint64 경계와 호출자 오류를 확인한다. 15단계분은 들어오는 메시지가 로컬 latch를 못 내리는 것, reset만이 내리는 것, reset이 활성 E-stop이나 arbiter의 `latched`를 덮지 않는 것, 다른 로봇·역순 메시지가 latch를 걸지 않는 것, 재latch를 확인한다. 실행 명령은 저장소 루트에서 `python3 -m unittest discover -s tests -p test_estop_guard.py -v`다. [IT-11](integration.md#4-통합시험-명세)의 로컬 반영 부분이며 관제 연동과 물리 버튼 실기 시험은 미실행이다.

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

**구현한 것** — `/control/drive_token`·`/control/estop`을 실제로 구독해 `DriveTokenGuard`·`EStopGuard`에 반영하고, 결합 결과를 AMR 내부 신호 `motion_allowed`(`std_msgs/Bool`)로 발행한다. `battery_status`(5.1절)와 같은 성격의 내부 연결이며 공용 인터페이스를 추가한 것이 아니다.

- `SafetyGate`: ROS에 의존하지 않는 순수 조합 클래스. `robot_id` 하나로 `DriveTokenGuard`·`EStopGuard`·`MotionGuard`를 묶는다. `observe_drive_token`·`observe_estop`이 각 가드의 `observe()`를 그대로 위임하고, `blocked_reasons(now)`/`motion_allowed(now)`가 `MotionGuard.blocked_reasons()`([3.3절](#33-motion_guardpy--구현-대조-완료) 참고)로 결합 판정을 낸다. 노드 클래스와 분리해 둬 ROS 없이도 단위시험이 가능하다.
- `estop_transition_event(previous_stopped, current_stopped, verdict)`: 수락된 E-stop 관측이 활성에서 해제로 전이했을 때 기존 안전 로그 이름 `E_STOP_AUTO_RELEASED`를 선택한다. `local_safety_supervisor._on_estop()`은 `robot_id`·`target_robot_id`·`sequence`와 함께 이 로그를 남긴다. 최종 `motion_allowed`가 token 부재 때문에 계속 `false`여도 E-stop 해제 반영 자체를 확인할 수 있다.
- 신선도 재확인 타이머(0.1초, `battery_monitor`의 `_check_freshness`와 같은 간격)가 새 메시지 없이도 매 주기 `blocked_reasons(now)`를 다시 계산한다. drive_token의 Q-01 lease는 메시지 수신이 아니라 시계로 만료되므로, 메시지가 끊기면 이 타이머가 만료를 감지해 `motion_allowed`를 다시 발행한다. E-stop에는 이런 타이머가 없다 — lease 개념이 없고, heartbeat·신선도 timeout은 TBD-IF-004라 amr.md 3절의 임의 timeout 금지를 그대로 따른다.
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
    ES[/control/estop 콜백] --> PRE[이전 estop stopped 저장]
    PRE --> OE[SafetyGate.observe_estop]
    OE --> REL{ACCEPTED이고 True → False?}
    REL -->|예| RLOG[E_STOP_AUTO_RELEASED 로그]
    REL -->|아니오| PUB
    RLOG --> PUB
    TIMER[0.1초 재확인 타이머] --> PUB
    OT --> PUB[_publish_if_changed]
    OT --> TOK[SafetyGate.token_status now]
    TIMER --> TOK
    TOK --> TV{accepted token ID가 바뀜?}
    TV -->|예| TP[accepted_token_id 내부 토픽 발행]
    TV -->|아니오| TSKIP[발행 생략]
    PUB --> BR[SafetyGate.blocked_reasons now]
    BR --> D{drive_token GRANTED?}
    D -->|아니오| R1[DRIVE_TOKEN_NOT_GRANTED]
    D -->|예| E
    R1 --> E{estop stopped?}
    E -->|예| R2[ESTOP_ACTIVE]
    E -->|아니오| CHK
    R2 --> CHK{allowed 값이 이전과 다름?}
    CHK -->|아니오| SKIP[발행 생략]
    CHK -->|예| MA[motion_allowed 발행 + 로그]
~~~

최종 속도 경로는 위 권한 경로와 별개다. 12단계에서 추가한 부분이다.

~~~mermaid
flowchart TD
    CAND[cmd_vel_safe 콜백] --> FIN{유한한 값?}
    FIN -->|아니오| DROP[표본 폐기 / 경고 로그]
    FIN -->|예| OC[SafetyGate.observe_candidate]
    OC --> PO[_publish_output always=true]
    TIMER2[0.1초 재확인 타이머] --> PO2[_publish_output always=false]
    DT2[drive_token / estop 콜백] --> PO2
    PO --> EV[SafetyGate.output monotonic_now, ros_now]
    PO2 --> EV
    EV --> GA{token GRANTED / estop 해제?}
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

### 7.1 robot_status_state.py — 구현 대조 완료

2026-09-07: 사용자 7단계 진행 요청에 따라 [robot_status_state.py](../src/patrol_amr/patrol_amr/robot_status_state.py)에 8단계 `status_reporter`가 사용할 순수 Python 상태 모델을 구현했다. ROS 토픽을 발행하는 노드가 아니라 로봇 한 대의 상태를 보관하고 snapshot을 만드는 내부 모듈이다.

- `OperationalState`, `MissionState`, `DockingState`, `BatteryState`: [인터페이스 4·8절](interfaces.md#4-robotstatus)에 확정된 숫자만 `IntEnum`으로 정의했다. 네 축은 독립적으로 갱신한다. 축 조합별 허용 전이는 TBD-AMR-005이므로 이 파일에서 임의로 막지 않는다.
- `RobotStatusState.update_states(...)`: 전달된 축의 값을 모두 먼저 검증한 뒤 한꺼번에 반영한다. 하나라도 잘못되면 어느 축도 바뀌지 않는다. 실제 변경이 있을 때만 내부 `revision`을 1 증가시킨다. 이 revision은 8단계의 변경 감지용 로컬 값이며 공용 `status_sequence`가 아니다.
- `safety_state`: 필드 이름은 사용하지만 enum 숫자는 TBD-IF-003이므로 `SafetyState` enum과 기본 숫자를 만들지 않았다. 합의된 값이 호출자에게서 들어오면 uint8 범위만 검증해 보관한다. 초기 `None`은 “계약 매핑이 아직 공급되지 않음”이라는 내부 상태이고 ROS 메시지 값이 아니다.
- `RobotStatusState.observe_pose(...)`: 유효 위치는 payload, `map` frame, 측정 시각이 모두 있어야 한다. `pose_valid=false`가 들어오면 현재 pose는 무효로 표시하되 마지막 유효 pose는 지우지 않는다. pose payload에는 8단계에서 ROS pose와 covariance가 함께 들어온다.
- `RobotStatusState.snapshot(snapshot_at)`: 현재 상태의 복사본을 만들고 같은 ROS clock의 snapshot 시각에서 마지막 유효 pose 측정 시각을 빼 `last_valid_pose_age`를 계산한다. token lease처럼 로컬 monotonic 시간을 쓰는 곳과 섞지 않는다.

새 [interfaces.md](interfaces.md#4-robotstatus)는 상태 필드 이름을 `operational_state`, `mission_state`, `docking_state`, `battery_state`, `safety_state`로 명확히 했으므로 내부 모델도 이 이름을 사용한다. 2026-09-07 사용자 요청으로 [RobotStatus.msg](../src/patrol_interfaces/msg/RobotStatus.msg)도 같은 이름과 의미 필드로 동기화했다. safety enum 숫자와 waypoint·scan 상세 동작은 여전히 TBD-IF-003이다.

~~~mermaid
flowchart TD
    INIT[RobotStatusState 생성] --> DEFAULT[UNKNOWN / NONE / pose_valid false]
    STATE[update_states] --> VALIDATE{전달된 모든 축 값 유효?}
    VALIDATE -->|아니오| ERROR[ValueError / 어떤 축도 변경 안 함]
    VALIDATE -->|예| CHANGED{기존 값과 다른가?}
    CHANGED -->|예| APPLY[축을 독립적으로 반영 + revision 증가]
    CHANGED -->|아니오| KEEP[상태와 revision 유지]
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

**14단계 추가 — odometry 축과 `motion_stopped`(2026-09-08).** [interfaces.md 3절](../interfaces.md)이 판정에 필요한 네 값을 모두 확정해 두었으므로 이 모듈이 정한 숫자는 없다.

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

검증: [단위시험](../tests/test_robot_status_state.py) 32건은 안전한 초기값, 독립 상태 축, 원자적 검증, 미합의 safety 숫자의 불투명 처리, 유효 pose 저장, 무효 pose 뒤 마지막 유효 pose 보존, age 계산, 입력·snapshot 복사, 잘못된 frame·시각 거절을 확인한다. 14단계분은 네 상수가 interfaces.md 값과 일치하는지, 유지 창 경계, 한도 포함 여부와 초과, 신선도 경계, 관측 단절 시 창 재개, 미수신·stale의 NaN, 시각 역행·비유한 값 거절, 그리고 관측 없이는 정지라고 말하지 않는지를 확인한다. 실행 명령은 저장소 루트에서 `python3 -m unittest discover -s tests -p test_robot_status_state.py -v`다.

### 7.2 status_reporter.py — 구현 대조 완료

2026-09-07: 사용자 8단계 진행 요청에 따라 [status_reporter.py](../src/patrol_amr/patrol_amr/status_reporter.py)를 추가했다. `/{robot}/robot_status`를 새 `RobotStatus.msg` 이름으로 발행하며 Q-02의 정기 2 Hz와 상태 변경 발행 최대 10 Hz를 `PublicationGate`가 관리한다. `StatusSequence`는 프로세스 세션 안에서 1부터 증가하고, `source_session_id`는 실행 시 필수 parameter로 받는다.

- 입력 연결: 현재 구현된 상대 내부 토픽 `battery_status`를 구독해 `battery_state`를 갱신한다. 원본 `battery_state`도 읽어 유효한 SOC와 센서 측정 시각을 `battery_soc`·`battery_timestamp`로 보존한다. enum 변경은 최대 10 Hz 제한 안에서 즉시 발행 대상으로 표시한다.
- 필수 설정: `robot_id`, `source_session_id`, `safety_state`를 모두 명시해야 시작한다. `safety_state`는 TBD-IF-003 때문에 기본 숫자를 만들 수 없어, 통합 주체가 합의된 uint8 값을 넣도록 강제했다. 현재 단계의 `safety_state:=0`은 전송 시험값일 뿐 의미 확정이 아니다.
- **14단계 odometry 연결(2026-09-08):** 상대 토픽 `odom`(`nav_msgs/Odometry`)을 구독해 `linear_velocity`·`angular_velocity`·`motion_stopped`를 채운다. 판정은 7.1절의 `RobotStatusState`가 하고 이 노드는 ROS 변환만 한다. `odom`은 로봇 드라이버가 내는 표준 토픽이며 interfaces.md TBD 표에 없다 — 미정 항목이 아니다. launch의 `odom_topic` 인자로 드라이버 위치를 바꿀 수 있다(TBD-ARCH-001).
- **16단계 token 연결(2026-09-08):** 상대 내부 토픽 `accepted_token_id`(`std_msgs/String`)를 구독한다. 값이 비어 있지 않으면 같은 값을 `accepted_token_id`에 쓰고 `token_valid=true`, 빈 값이면 `''`·`false`로 한 snapshot에서 함께 쓴다. Q-02의 즉시 발행 목록에는 token이 없으므로 다음 정기 2 Hz snapshot에 반영한다.
- **17단계 pose 연결(2026-09-08):** Nav2 AMCL 표준 상대 토픽 `amcl_pose`(`geometry_msgs/PoseWithCovarianceStamped`)를 구독한다. `map` frame이고 pose·covariance 전부가 유한한 메시지는 현재 pose와 last-valid pose에 함께 보존한다. frame·수치가 무효면 `pose_valid=false`로 바꾸되 last-valid pose는 지우지 않는다. `pose_valid` 전이만 Q-02의 변경 발행 대상으로 표시하고 일반 위치 이동은 정기 2 Hz snapshot에 반영한다.
- pose 수신이 끊겨도 임의 timeout으로 `pose_valid=false`를 만들지 않는다. Q-03·Q-05의 1.5초는 관제 STALE 및 주행 재개 조건이지 pose 유효성 정의가 아니다. RobotStatus의 pose와 last-valid pose가 측정 timestamp를 포함하므로 소비자가 그 시각으로 age를 판단한다.
- odometry 수신은 **즉시 발행 대상이 아니다.** Q-02가 즉시 발행을 요구하는 것은 mission·safety·battery enum과 `pose_valid`이고 속도는 그 목록에 없다. 속도는 매 표본마다 바뀌므로 변경 트리거로 다루면 이유 없이 10 Hz 제한을 넘긴다.
- 남은 안전한 미연결 값은 mission supervisor가 공급해야 하는 operational·mission·docking·command·mission·waypoint·scan·reason 축과 미정인 safety enum이다. SOC 미수신은 0으로 오해하지 않도록 NaN으로 낸다.

~~~mermaid
flowchart TD
    START[StatusReporter 생성] --> CFG{robot_id / source_session_id / safety_state 유효?}
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
    TICK[0.02초 timer] --> DUE{최초 또는 변경 0.1초 또는 정기 0.5초 도달?}
    DUE -->|아니오| WAIT[대기]
    DUE -->|예| SNAP[RobotStatusState.snapshot]
    SNAP --> MAP[새 RobotStatus 필드명으로 변환]
    KEEP_TOKEN --> MAP
    KEEP_POSE --> SNAP
    INVALID_POSE --> SNAP
    MAP --> SEQ[status_sequence 증가]
    SEQ --> PUB[/{robot}/robot_status 발행]
~~~

검증: [단위시험](../tests/test_status_reporter.py) 16건은 필수 설정, 최초·정기 2 Hz·변경 최대 10 Hz 판정, 시간 역행 거절, status_sequence, token 필드 매핑, pose·orientation·covariance의 유한성 판정을 확인한다. [robot_status_state 단위시험](../tests/test_robot_status_state.py) 32건은 유효 pose 저장, 무효 pose 뒤 last-valid 보존과 age 계산을 포함한다. 실제 토픽 echo는 사용자 환경에서 확인해야 한다.

### 7.3 patrol_report.py — 구현 대조 완료

2026-09-08: 사용자 18단계 진행 요청에 따라 [patrol_report.py](../src/patrol_amr/patrol_amr/patrol_report.py)를 추가했다. 아직 mission/checkpoint 코드가 병합되지 않아 ROS publisher를 임의 콜백에 연결하지 않고, 확정된 계약만으로 최종 결과를 검증하고 불변 record를 만드는 순수 Python 모듈이다.

- `PatrolResult`와 `ReasonCode`는 [PatrolReport.msg](../src/patrol_interfaces/msg/PatrolReport.msg)의 결과 3종과 reason code 29종을 그대로 옮겼다. 정의되지 않은 숫자는 거절한다.
- `PatrolReportFactory`는 로봇·source session 하나의 report sequence를 관리한다. [interfaces.md 1.2절](interfaces.md#12-공용-식별자-규칙)에 따라 `rpt-<robot_session>-<report_sequence>`를 만들고 sequence는 최소 네 자리로 0을 채운다. persistent owner가 재시작 뒤 다음 sequence를 복원할 수 있도록 `next_sequence` 입력·조회만 제공한다.
- command·mission ID는 비어 있는지만 확인하고 문자열을 파싱하거나 다시 만들지 않는다. MissionCommand에서 받은 값을 그대로 echo해야 한다는 계약 때문이다.
- FAILED와 CANCELED는 `NONE`이 아닌 reason code와 비어 있지 않은 reason이 모두 필요하다. 성공·실패·취소 모두 시작·종료 시각을 보존하고 종료가 시작보다 앞서면 거절한다.
- 같은 command ID와 완전히 같은 결과를 다시 넣으면 기존 record 객체와 report ID를 그대로 반환한다. 다른 결과로 덮으려 하면 거절하고 sequence도 소비하지 않는다.
- 이번 단계는 영속 큐·ACK·ROS publisher를 구현하지 않는다. 미전송 report를 저장하고 재연결·재시작 뒤 재발행하려면 mission 결과 입력, 저장 위치와 수명, 수신 확인·삭제 계약이 더 필요하다. 메모리 중복 방지를 영속 완료로 오해하지 않는다.

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
    RETURN --> PENDING[mission 병합 후 ROS publisher·영속 outbox 연결]
~~~

검증: [단위시험](../tests/test_patrol_report.py) 16건은 result/reason 상수 일치, report ID 형식과 sequence 복원, 필수 필드·시각 경계, 실패·취소 reason 강제, 동일 command 재요청의 ID 재사용, 충돌 거절과 sequence 비소비를 확인한다. 전체 단위시험은 `Ran 166 tests`/`OK`, `colcon build --packages-select patrol_interfaces patrol_amr`는 두 패키지 성공이다. ROS publisher가 없으므로 이 단계에 사용자 토픽 시험은 없다.

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
