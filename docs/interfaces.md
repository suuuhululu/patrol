# 공용 ROS 2 인터페이스

> 기준: [2026-09-07 PM 설계 결정](decisions/2026-09-07-design-baseline.md). 관제는 별도 노드, 시스템 모니터는 UI 전용, 공용 패키지는 `patrol_interfaces`이며 상세 계약은 System design의 확정 내용을 우선한다.

상태: v1.0 공용 계약 확정 · 차기 버전 TBD 분리 · 담당: AMR·관제·시스템 모니터·비전 공동

이 문서는 통신 이름, 메시지 필드·enum, ID, QoS와 공통 시간 기준의 원본이다. 완전한 .msg 구현 정의가 없는 타입은 TBD로 표시한다. 아래 값은 공유 설계 기준이며 실제 동작 검증 결과가 아니다.

관제 구현의 확정 입력 버전은 [v1.0 기준선](decisions/2026-09-08-control-interface-baseline.md)이다. 해당 기준선에 열거한 필드·enum·명령 전이·Heartbeat·E-stop·RobotStatus·Keepout parameter 의미는 2026-09-08 합의 상태로 고정한다. 기준선 밖의 TBD는 차기 버전으로 이관하며 v1.0 완료 조건이 아니다. 확정 범위를 바꾸려면 새 수정 요청서와 기준선 갱신이 필요하다.

## 1. 이름과 송수신

아래 {robot}에는 슬래시 없는 robot1 또는 robot6을 넣는다. 예: /robot1/mission_command. [식별 매핑](architecture.md#2-식별-체계)을 따른다.

| 인터페이스 | 타입·방식 | 송신 → 수신 | 상태 |
|---|---|---|---|
| /{robot}/mission_command | patrol_interfaces/msg/MissionCommand | 관제 → AMR | 명령별 mission·target과 `.msg`·AMR 수신부 반영, 관제 송신부 미구현 |
| /{robot}/command_check | patrol_interfaces/msg/CommandCheck | AMR → 관제 | check_state 수치·전이와 `.msg`·AMR 발행부 반영, 관제 수신부 미구현 |
| /{robot}/mission_execution_event | patrol_interfaces/msg/MissionExecutionEvent | AMR mission → AMR command gateway | 2026-09-09 AMR 내부 계약, gateway 소비부 반영 중·mission 생산부 미반영 |
| /control/drive_token | patrol_interfaces/msg/DriveToken | 관제 → AMR 로컬 안전 | 세션·ID·message_sequence·회수 타입 반영 |
| /{robot}/robot_status | patrol_interfaces/msg/RobotStatus | AMR → 관제·시스템 모니터 | safety_state 의미·AMR 발행부 반영, `.msg` 중복 상수 정리와 관제 수신부 미구현 |
| /{robot}/patrol_report | patrol_interfaces/msg/PatrolReport | AMR → 관제·시스템 모니터 | 영속 큐·동일 report_id 발행 구현, 수신 저장 ACK는 TBD-IF-003 |
| /vision/cctv/gate_event | CameraState | gate_cam → cam_master | 패키지명·enum 수치 TBD |
| /vision/cctv/center_event | CameraState | center_cam → cam_master | 패키지명·enum 수치 TBD |
| /vision/cctv/patrol_allowed | std_msgs/msg/Bool | cam_master → 관제·시스템 모니터 | 정책 기준 있음 |
| /control/heartbeat | patrol_interfaces/msg/ControlHeartbeat | 관제 → AMR 로컬 안전 | 타입·필드·주기·timeout·QoS와 `.msg`·AMR 수신부 반영, 관제 발행부 미구현 |
| /control/estop | patrol_interfaces/msg/EStop | Safety Arbiter → AMR·시스템 모니터 | `.msg`와 AMR·시스템 모니터 소비부 반영, 대표 원인 우선순위 확정, 관제 발행부 미구현 |
| 로봇별 Keepout 설정 | Nav2 parameter API | 관제 → AMR global/local costmap | base 상시 ON·center corridor 제어 parameter 확정, 관제 transaction·실환경 검증 미실시 |
| DetectionCandidate | TBD | AMR 감지 처리 → AMR 확정 처리 | 로컬 경계, TBD-IF-006 |
| DetectionEvent·증적 | TBD | AMR → 시스템 모니터(수집·저장), 관제(제어용 이벤트) | TBD-IF-006·007 |

표의 시스템 모니터 수신 표기는 기존 관측·저장 기능의 담당 팀을 구분한 것이다. 직접 구독·중계 여부와 제어 상태·로그 전달 경로는 TBD-IF-003·004·006·007·008·010·011에서 합의하며, 팀 분리만으로 새 토픽이나 메시지를 확정하지 않는다.

외부 시스템은 AMR을 Action으로 직접 호출하지 않는다. AMR mission_supervisor가 내부 Nav2 Action을 사용한다. 차량 진입은 사람이 직접 제어하므로 /control/vehicle_entry_block은 사용하지 않는다.

/{robot}/keepout/status, BatteryEvent, ActionFeedback은 추가 인터페이스 제안이다. 아직 정식 토픽·타입으로 확정하지 않는다(TBD-IF-008).

### 1.1 전체 인터페이스 트리

이 트리는 이 문서에 정의된 시스템 인터페이스의 전체 목록이다. 토픽 경로, parameter API, AMR 내부 연결, 이름 미정인 계약을 구분한다. 실제 ROS 그래프를 조회한 결과나 전체 센서·Nav2 내장 토픽 목록은 아니다. 타입의 패키지 접두어와 상세 필드·QoS는 위 송수신 표 및 2~10절을 따른다.

~~~text
순찰 시스템 인터페이스
├── 이름이 정의된 ROS 토픽 (상세 계약의 TBD는 유지)
│   ├── /robot1                         [AMR1 / AMR 팀]
│   │   ├── mission_command             MissionCommand: 관제 → AMR1
│   │   ├── command_check               CommandCheck: AMR1 → 관제
│   │   ├── robot_status                RobotStatus: AMR1 → 관제·System monitor
│   │   └── patrol_report               PatrolReport: AMR1 → 관제·System monitor
│   ├── /robot6                         [AMR2 / AMR 팀]
│   │   ├── mission_command             MissionCommand: 관제 → AMR2
│   │   ├── command_check               CommandCheck: AMR2 → 관제
│   │   ├── robot_status                RobotStatus: AMR2 → 관제·System monitor
│   │   └── patrol_report               PatrolReport: AMR2 → 관제·System monitor
│   ├── /control                        [관제 팀]
│   │   ├── drive_token                 DriveToken: 관제 → 각 AMR 로컬 안전
│   │   ├── heartbeat                   ControlHeartbeat: 관제 → 각 AMR 로컬 안전
│   │   └── estop                       EStop: Safety Arbiter → AMR·System monitor
│   │                                   단일 발행자 [TBD-IF-004]
│   └── /vision/cctv                    [비전 팀]
│       ├── gate_event                  CameraState: gate_cam → cam_master
│       ├── center_event                CameraState: center_cam → cam_master
│       └── patrol_allowed              std_msgs/msg/Bool: cam_master → 관제·System monitor
├── Keepout parameter API               [관제 → AMR; 토픽이 아닌 노드/parameter 조합]
│   ├── /robot1/global_costmap/global_costmap → center_corridor_keepout_filter.enabled
│   ├── /robot1/local_costmap/local_costmap   → center_corridor_keepout_filter.enabled
│   ├── /robot6/global_costmap/global_costmap → center_corridor_keepout_filter.enabled
│   └── /robot6/local_costmap/local_costmap   → center_corridor_keepout_filter.enabled
│                                       base_keepout_filter.enabled=true는 상시 유지·관제 변경 금지
│                                       상태 토픽·실환경 확인 [TBD-IF-008 / 7절]
├── AMR 내부 연결                       [robot1·robot6에 각각 적용]
│   ├── mission_supervisor → Nav2       내부 Action; 정확한 이름·타입은 미기재
│   ├── mission_supervisor → gateway    MissionExecutionEvent: admission·실행·저장 완료
│   ├── 감지 처리 → 확정 처리           DetectionCandidate [TBD-IF-006]
│   ├── cmd_vel_safe                 TwistStamped: Nav2 collision_monitor → local safety
│   ├── cmd_vel_yaw                  TwistStamped: mission_supervisor → local safety
│   └── cmd_vel                      Twist: local_safety_supervisor → 구동부
│                                       로봇별 최종 속도 출력, 단일 발행자
├── 토픽명·전송 계약 미정인 연결
│   ├── AMR → 관제·System monitor       DetectionEvent [TBD-IF-006]
│   ├── AMR → System monitor            증적 이미지·메타데이터 [TBD-IF-007]
│   │   └── 전달 결과 ACK·재전송        필요 방식·방향·필드 합의 [TBD-IF-007]
│   ├── 관제 → System monitor          운영 판단 결과 토픽 [TBD-IF-011]
│   │   ├── STALE·통신 상태·CCTV timeout 경고
│   │   ├── UNREPORTED·순찰·교대 진행 상태
│   │   ├── 명령·권한·Keepout·복구·안전 상태
│   │   └── 운영상 증적 누락·지연 경고
│   │                                   위 항목은 전달할 의미이며 개별 토픽 확정이 아님
│   └── 팀 간 공용 로그 전달            생산자·수신자·토픽·필드·QoS 합의 [TBD-IF-011]
└── 추가 인터페이스 제안                [채택 여부·경로·타입 미확정: TBD-IF-008]
    ├── /{robot}/keepout/status          로봇별 Keepout 상태 후보
    ├── BatteryEvent                    이름 후보; Battery enum과 별개
    └── ActionFeedback                  이름 후보; 외부 Nav2 Action 호출 계약이 아님
~~~

- System monitor는 시스템 모니터 팀이다. 관제 코드와 함께 PC 3에서 실행하지만 독립 개발 단위이며, 수신 결과의 표시·저장·조회를 담당한다. 운영 상태·경고 판단은 관제가 수행한다.
- AMR·비전 토픽의 System monitor 수신 표기는 데이터 소비 관계다. 직접 구독·중계 방식은 해당 TBD에서 합의하며, 관제 판단 결과를 모니터가 다시 계산하지 않는다.
- Discovery Server와 네트워크 연결은 [architecture.md](architecture.md)의 실행 기반 구성이다. 공용 메시지 토픽과 구분한다. 내부 DB 테이블·인덱스·보존 정책은 [monitoring_and_data.md](monitoring_and_data.md)에 둔다.
- 전역 `/cmd_vel` 공유와 `/control/vehicle_entry_block`은 사용하지 않는다. 트리에 미정으로 표시한 이름·필드는 구현 계약으로 확정된 것이 아니다.

### 1.2 공용 식별자 규칙

2026-09-07 결정으로 UUID v4 대신 사람이 로그에서 식별할 수 있는 세션·sequence 기반 문자열 ID를 사용한다. 영문 소문자, 숫자, 하이픈을 사용하고 순번은 최소 네 자리로 0을 채운다. 시간만으로 유일성을 보장하지 않으며 발행자 세션과 증가 sequence를 함께 사용한다. ID는 추적·중복 제거용이고 수신자는 ID 문자열을 파싱해 제어하지 않으며 별도 robot·command·state·sequence 필드를 기준으로 동작한다. source session은 `<source>-<YYYYMMDDTHHMMSS>[-<restart_sequence>]` 형식으로 프로세스 시작 시 생성하고 재시작 시 변경한다.

| 종류 | 형식 |
|---|---|
| 관제 세션 | `ctrl-<YYYYMMDDTHHMMSS>[-<restart_sequence>]` |
| mission | `msn-<control_session>-<robot_id>-<mission_sequence>` |
| command | `cmd-<control_session>-<robot_id>-<command>-<sequence>` |
| Drive Token | `tok-<control_session>-<holder_robot_id>-<grant_sequence>` |
| PatrolReport | `rpt-<robot_session>-<report_sequence>` |
| CCTV 차량 이벤트 | `cam-<camera_session>-<state>-<sequence>` |
| AMR Detection | `det-<robot_session>-<event_type>-<sequence>` |
| 증적 | `evi-<robot_session>-<event_sequence>-<evidence_sequence>` |
| 관제 운영 이벤트 | `op-<control_session>-<event_type>-<sequence>` |

command 이름은 `start`, `evacuate`, `resume`, `dock`, `stop`, `cancel`을 사용한다. 관제 command sequence는 robot이나 mission이 바뀌어도 초기화하지 않는다. 각 생산자의 session ID는 프로세스 재시작 시 변경한다. 변경 근거와 AMR 반영 요청은 [관제 수정 요청서](change_requests/CR-관제_09-07_15-55_AMR_명령_토큰_상태_안전_계약_변경.md)에 기록한다.

## 2. MissionCommand

필드 의미 기준:

~~~text
std_msgs/Header header
string command_id
string mission_id
string robot_id
uint8 command
string target_id
geometry_msgs/PoseStamped target_pose
string issued_by
~~~

| command | 값 |
|---|---|
| STOP | 0 |
| START_PATROL | 1 |
| MOVE_TO_SAFE_ZONE | 2 |
| RESUME_PATROL | 3 |
| DOCK | 4 |
| CANCEL | 5 |

command ID는 1.2절 형식을 사용한다. 같은 내용의 재전송은 같은 ID와 원래 발급 시각·payload를 유지하고 내용·목적 변경은 새 ID다. START_PATROL은 새 mission ID를 생성한다. 같은 순찰의 대피·재개·복귀·도킹은 mission ID를 유지하고 command ID만 새로 생성한다. 완료·실패·취소 뒤의 새 START_PATROL과 독립 수동 DOCK는 새 mission ID를 사용한다.

AMR은 command ID를 최소 24시간 보관한다. 1,000개를 초과해도 24시간 이내 항목은 삭제하지 않고, 24시간이 지난 항목 중 최신 1,000개는 유지한다. 같은 ID를 중복 실행하지 않는다. 같은 ID가 실행 전 다시 오면 기존 ACCEPTED, 실행 중이면 EXECUTING, 완료 후면 기존 PatrolReport를 재발행한다. 같은 ID에 `robot_id`, `command`, `target_id`, `target_pose`, `mission_id` 중 다른 값이 있으면 `REJECTED / COMMAND_ID_CONFLICT`로 거절한다. DDS 수신 시각은 충돌 비교 대상이 아니다. `parameters_json`은 사용하지 않으며 공용 `.msg`와 AMR 지문·검증·DB 스키마에서 제거했다. 기존 DB 행은 migration 시 보존한다.

명령별 필수값과 의미는 다음과 같다. 빈 값은 해당 타입의 기본값을 뜻한다. 합의된 명령에서는 `target_pose`를 사용하지 않지만, 필드 제거는 AMR 검토 후 결정하므로 현재 스키마에는 유지한다.

| command | mission_id | target_id | target_pose | 처리 기준 |
|---|---|---|---|---|
| STOP | 활성 mission이 있으면 해당 ID, 없으면 빈 값 허용 | 빈 값 | 미사용 | 활성 mission이 없어도 안전한 no-op으로 ACCEPTED 가능하며 재개 가능한 상태를 보존한다. |
| START_PATROL | 새 ID 필수 | robot1은 `robot1_default`, robot6은 `robot6_default` | 미사용 | 다른 plan ID는 `REJECTED / INVALID_TARGET`이다. waypoint 구성 변경은 TBD-AMR-005다. |
| MOVE_TO_SAFE_ZONE | 기존 활성 mission ID 필수 | 빈 값 | 미사용 | AMR이 map·안전영역에서 가장 가까운 유효 좌표를 동적으로 계산한다. 계산 결과·도착 보고 계약은 TBD-AMR-005·TBD-IF-003에서 검토한다. |
| RESUME_PATROL | 재개할 기존 mission ID 필수 | 빈 값 | 미사용 | CANCEL된 mission은 재개할 수 없다. |
| DOCK | 기존 또는 독립 신규 mission ID 필수 | robot1은 `dock_1`, robot6은 `dock_6` | 미사용 | docking station은 target_id만 사용한다. |
| CANCEL | 취소할 활성 mission ID 필수 | 빈 값 | 미사용 | 지정 mission 전체를 취소하고 재개 가능한 상태를 남기지 않는다. 없거나 종료된 mission은 `REJECTED / INVALID_MISSION`이다. |

START_PATROL은 새 mission을 시작하고 RESUME_PATROL은 기존 mission ID를 이어간다. STOP은 실행을 멈추되 재개 가능한 상태를 보존하고, CANCEL은 지정한 활성 mission 전체를 종료해 CANCELED 결과를 만든다. E-stop과 token 만료는 독립 안전 계층이다. MissionCommand 중재 우선순위는 STOP → MOVE_TO_SAFE_ZONE → DOCK → CANCEL → RESUME_PATROL → START_PATROL 순이다.

### 2.1 CommandCheck

~~~text
std_msgs/Header header
string command_id
string mission_id
string robot_id
uint8 check_state
uint32 reason_code
string reason
string source_session_id
uint64 sequence
~~~

| check_state | 값 | 의미 |
|---|---:|---|
| CHECK_UNKNOWN | 0 | 초기·해석 불가 상태. 정상 응답으로 사용하지 않는다. |
| CHECK_ACCEPTED | 1 | 형식·상태 검증을 통과하고 실행 대기열에 들어감 |
| CHECK_EXECUTING | 2 | 실제 command 실행을 시작함 |
| CHECK_REJECTED | 3 | command를 실행하지 않음 |

정의되지 않은 check_state 숫자는 폐기하고 프로토콜 경고를 기록한다. 정상 전이는 ACCEPTED → EXECUTING이며 역방향 전이는 항상 폐기한다. 관제 내부 `WAITING` 상태에서 ACCEPTED가 누락된 EXECUTING을 받으면 동일 `command_id`·`mission_id`·`robot_id`가 모두 일치할 때만 `WAITING → EXECUTING` 복구 예외로 수락하고 관제 운영 경고 `ACCEPTED_MISSING`을 기록한다. 이 예외를 수락하면 AMR이 실행을 시작한 증거이므로 해당 MissionCommand 재전송을 중단한다.

### 2.2 AMR 내부 MissionExecutionEvent

`/{robot}/mission_execution_event`는 mission 실행부가 command gateway에 admission·실행 시작·영속 저장 완료를 알리는 AMR 내부 토픽이다. 외부 관제는 이 토픽을 구독하지 않으며 외부 `CommandCheck`는 gateway 하나만 발행한다.

~~~text
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
~~~

gateway는 새 명령을 PENDING으로 저장하고 전체 `MissionCommand`를 `mission_dispatch`에 발행한다. mission의 ADMITTED 뒤에만 외부 ACCEPTED, worker 실제 시작을 알리는 STARTED 뒤에 EXECUTING을 발행한다. REJECTED는 외부 REJECTED로 변환한다. NONTERMINAL_STORED는 PAUSED·WAITING_SAFE_ZONE처럼 PatrolReport가 없는 저장 완료이며, RESULT_STORED는 `has_report=true`이고 report의 robot·command·mission ID가 이벤트와 모두 일치해야 한다.

같은 이벤트의 영속 멱등성 키는 `command_id + event_type + report_id`다. report가 없는 이벤트는 빈 report ID를 사용한다. 완료 상태를 과거 상태로 되돌리는 이벤트는 적용하지 않고 프로토콜 경고를 남긴다. QoS는 RELIABLE / TRANSIENT_LOCAL / KEEP_LAST(20)이다. `mission_dispatch`도 RELIABLE / TRANSIENT_LOCAL / KEEP_LAST(10)으로 사용하며, retained 재수신으로 실제 Action이 중복되지 않도록 mission 실행 ledger가 command fingerprint를 보존한다.

관제는 MissionCommand를 발행한 뒤 5초 이내에 같은 command ID의 ACCEPTED 또는 REJECTED를 기다린다. 매 시도 5초 timeout 후 동일 ID·payload를 최대 2회 재전송한다. 이후에도 확인되지 않으면 관제 운영 판단 `COMMAND_CHECK_TIMEOUT`을 기록하고 새 command ID를 자동 생성하지 않는다. EXECUTING은 정상 Check timeout 응답 조건이 아니며 최종 결과는 PatrolReport로 전달한다. 중간 CommandCheck가 일부 누락됐어도 ID가 유효한 PatrolReport는 최종 결과로 수락하고 프로토콜 경고만 기록한다. `COMMAND_CHECK_TIMEOUT`과 `ACCEPTED_MISSING`은 AMR CommandCheck reason code가 아니라 TBD-IF-011의 관제 운영 이벤트다.

## 3. DriveToken

필드 의미 기준:

~~~text
std_msgs/Header header
string control_session_id
string token_id
string holder_robot_id
builtin_interfaces/Duration lease_duration
uint64 message_sequence
~~~

- 공통 /control/drive_token을 사용한다. holder_robot_id는 robot1 또는 robot6이다.
- token_id가 빈 문자열이면 holder_robot_id에 지정한 로봇의 권한을 관제가 회수한 상태다.
- 다른 holder의 토큰은 자신의 주행 권한으로 수락하지 않는다.
- control_session_id 또는 token_id가 바뀌면 기존 token을 즉시 무효화한다.
- 발급·갱신·명시적 해제 결정권은 관제에 있다.
- 같은 control session에서 message_sequence가 마지막 수락 값 이하인 메시지, 만료 메시지, 다른 로봇용 token은 폐기한다. callback 수신 시각만으로 lease를 연장하지 않는다.
- 만료·회수 시 신규 주행을 차단하고 안전 정지한다. 새 토큰 수신만으로 자동 출발하지 않는다.

token ID는 1.2절 형식을 사용하고 새 권한 발급 때만 변경한다. 갱신에서는 같은 token ID와 증가한 message sequence를 사용한다. 관제 재시작 시 control session을 변경하고 message sequence를 1부터 시작한다. AMR은 새 control session에서 이전 token을 폐기한다. 회수는 빈 token ID, 이전 holder_robot_id, 증가한 message sequence로 발행한다.

holder 교대는 기존 holder 회수 → AMR의 회수 수락 → 실제 정지 확인 → 신규 holder token 발급 순서다. 실제 정지는 AMR odometry에서 선속도 절댓값 ≤ 0.05 m/s, 각속도 절댓값 ≤ 0.1 rad/s가 0.5초 연속 유지되고 측정 age ≤ 0.5초일 때 확인한다. odometry가 오래됐거나 무효이면 정지 확인 실패이며 신규 holder token을 발급하지 않는다.

시간값은 9절을 따른다. 보장되지 않은 시간 동기화로 서로 다른 monotonic clock을 직접 비교하지 않는다. message age의 timestamp 검증과 로컬 lease 경과 측정은 구분한다.

### 3.1 Heartbeat와 E-stop

`/control/heartbeat`는 `patrol_interfaces/msg/ControlHeartbeat`를 5 Hz로 발행하며 AMR은 1초 미수신을 timeout으로 판단해 로컬 안전 정지한다. QoS는 BEST_EFFORT·VOLATILE·KEEP_LAST(3)이다. 새 `control_session_id`를 받으면 이전 heartbeat·token 상태를 무효화하며 heartbeat 복구만으로 자동 재출발하지 않는다.

~~~text
std_msgs/Header header
string control_session_id
uint64 sequence
~~~

E-stop은 Safety Arbiter만 발행한다. 하드웨어·물리 E-stop과 수동 reset은 구현 범위에 포함하지 않는다. 시스템 모니터 UI는 관제 소유 요청 API를 호출할 수 있으나 `/control/estop`을 직접 발행하거나 안전 판단을 하지 않는다. UI 경로 도입은 시스템 모니터의 읽기 전용 경계 변경이므로 팀 검토 전까지 제안 상태다.

~~~text
std_msgs/Header header
string target_robot_id      # robot1, robot6 또는 all
bool active
uint8 reason
uint64 sequence
~~~

| reason | 값 | 의미 |
|---|---:|---|
| ESTOP_REASON_UNKNOWN | 0 | 원인을 신뢰할 수 없거나 아직 분류하지 못함 |
| ESTOP_REASON_OPERATOR | 1 | 시스템 모니터 UI를 통한 운영자 정지 요청 |
| ESTOP_REASON_COMMUNICATION | 2 | 관제·AMR 안전 통신 상실 또는 timeout |
| ESTOP_REASON_TOKEN | 3 | Drive Token 누락·만료·회수로 주행 권한이 없음 |
| ESTOP_REASON_OBSTACLE | 4 | 로컬 장애물 안전 차단 |
| ESTOP_REASON_KEEPOUT_FAILURE | 5 | Keepout 적용·확인·rollback 실패로 안전 상태를 보장할 수 없음 |
| ESTOP_REASON_SYSTEM_FAULT | 6 | 센서·구동·안전 감독 등 시스템 고장 |

관제는 대상별 활성 원인 집합을 내부에 유지하고 `/control/estop`에는 다음 순서에서 가장 먼저 활성인 대표 원인 하나만 발행한다.

`SYSTEM_FAULT → UNKNOWN → OPERATOR → KEEPOUT_FAILURE → COMMUNICATION → OBSTACLE → TOKEN`

전체 활성 원인 집합은 `uint8[] active_reasons` 의미의 디버깅·표시용 관제 판단 계약으로 별도 제공하며 EStop 메시지 필드에 넣지 않는다. 해당 전달 타입·토픽은 TBD-IF-011, 각 원인의 상세 활성·해제 조건은 TBD-IF-004로 차기 버전에 이관한다.

UI 정지 요청은 OPERATOR 원인을 즉시 활성화한다. UI 해제 요청은 OPERATOR 원인을 해제 대기 상태로 바꾸며, 모든 활성 원인이 3초 연속 사라진 경우에만 Safety Arbiter가 `active=false`를 발행할 수 있다. 조건이 다시 발생하면 3초 계수를 초기화한다. 해제 후에도 AMR은 정지 상태를 유지하며 새 Drive Token과 별도 MissionCommand를 모두 받은 뒤 이동한다. E-stop 해제 부저는 사용하지 않는다.

## 4. RobotStatus

필드 의미 기준은 다음과 같다. safety_state enum은 2026-09-08 결정이며 `.msg`와 AMR 상태 발행 경로에 반영했다. 시스템 모니터 소비 호환성은 별도 검토 대상이다.

~~~text
std_msgs/Header header                         # RobotStatus snapshot 생성 시각
string robot_id
string source_session_id
uint64 status_sequence
uint8 operational_state
uint8 mission_state
uint8 docking_state
uint8 battery_state
uint8 safety_state
string active_command_id
string active_mission_id
geometry_msgs/PoseWithCovarianceStamped pose
bool pose_valid
geometry_msgs/PoseWithCovarianceStamped last_valid_pose
float32 linear_velocity
float32 angular_velocity
bool motion_stopped
string accepted_token_id
bool token_valid
float32 battery_soc
builtin_interfaces/Time battery_timestamp
string current_waypoint_id
string scan_state
uint32 reason_code
string reason
~~~

- 위치 frame은 map이며 측정 시각과 covariance를 포함한다.
- pose_valid=false여도 마지막 유효 pose와 last-valid 시각/age를 보존한다. 이를 현재 유효 위치로 사용하지 않는다.
- operational, mission, docking, battery, safety 상태를 구분한다.
- STALE은 관제가 수신 신선도를 판정하는 상태이며 아래 operational enum에 임의로 추가하지 않는다.
- header.stamp는 상태 snapshot 생성 시각, pose와 last_valid_pose의 header.stamp는 각 pose 측정 시각이다. 관제·시스템 모니터의 수신 시각은 로컬에서 별도 기록한다.
- motion_stopped는 3절의 실제 정지 속도·연속 유지·신선도 조건을 모두 만족할 때만 true다.

| safety_state | 값 | 의미 |
|---|---:|---|
| SAFETY_UNKNOWN | 0 | 초기화되지 않았거나 상태를 신뢰할 수 없음 |
| SAFETY_NORMAL | 1 | 활성 로컬 안전 정지가 없음. 이 값만으로 이동 권한을 뜻하지 않는다. |
| SAFETY_STOPPING | 2 | 출력이 차단됐고 감속·정지 확인 중임 |
| SAFETY_STOPPED | 3 | 출력이 차단됐으며 별도의 실제 정지 조건이 확인됨 |
| SAFETY_ESTOPPED | 4 | E-stop이 활성 상태임. 이 값만으로 속도 0을 보장하지 않는다. |
| SAFETY_ERROR | 5 | local_safety_supervisor 또는 관련 안전 계층 오류 |

구체적인 원인은 `reason_code`·`reason`으로 구분한다. `safety_state`, `motion_stopped`, 속도 측정 age는 서로 대체하지 않는다.

~~~text
Operational:
OP_UNKNOWN=0
OP_INITIALIZING=1
OP_READY=2
OP_MOVING=3
OP_STOPPED_SAFETY=4
OP_CHARGING=5
OP_ERROR=6

Mission:
MISSION_NONE=0
MISSION_UNDOCKING=1
MISSION_PATROLLING=2
MISSION_MOVING_TO_SAFE_ZONE=3
MISSION_WAITING_SAFE_ZONE=4
MISSION_RETURNING_TO_DOCK=5
MISSION_DOCKING=6
MISSION_PAUSED=7
MISSION_COMPLETED=8
MISSION_FAILED=9
MISSION_CANCELED=10

Docking:
DOCK_UNKNOWN=0
DOCK_UNDOCKED=1
DOCK_UNDOCKING=2
DOCK_DOCKING=3
DOCK_DOCKED=4
DOCK_FAILED=5
~~~

정기 및 변경 발행 기준은 9절을 따른다. waypoint·방문·scan 상세 필드의 확장은 TBD-AMR-005와 함께 결정한다.

## 5. PatrolReport

필드 의미 기준:

~~~text
std_msgs/Header header
string report_id
string robot_id
string source_session_id
string command_id
string mission_id
uint8 result
uint32 reason_code
string reason
builtin_interfaces/Time started_at
builtin_interfaces/Time finished_at
string final_waypoint_id
string[] related_event_ids
~~~

~~~text
SUCCEEDED=0
FAILED=1
CANCELED=2
~~~

SUCCEEDED는 목표 정상 달성, FAILED는 자체 장애·주행 실패·위치 검증 또는 시스템 실패, CANCELED는 관제 취소·명령 대체·정책 중단·역할 교대다. FAILED/CANCELED는 reason_code를 필수로 하며 reason에 구체적 진단값을 기록한다.

command 하나가 최종 상태에 이를 때 PatrolReport 하나를 생성한다. report ID는 1.2절 형식으로 AMR이 생성하고, command ID와 mission ID는 수신한 MissionCommand의 값을 그대로 사용한다. 여러 report가 같은 mission ID를 공유할 수 있다. AMR은 미전송 report를 로컬 영속 큐에 저장하고 재연결 후 같은 report ID로 재전송한다. 수신자는 report ID로 중복을 제거한다.

2026-09-08 AMR-07 구현은 robot별 로컬 outbox에 종료 결과를 저장하고 matched subscriber가 생기면 같은 report ID로 `/{robot}/patrol_report`를 발행한다. DDS publish 호출 성공만으로 수신 애플리케이션 저장 완료를 보장할 수 없으므로 ACK 단위와 ACK 이후 삭제 조건은 [AMR 검토 요청서](change_requests/CR-AMR_09-08_10-42_PatrolReport_ACK와_큐_삭제_조건_검토.md)의 TBD-IF-003에 남긴다. E-stop reset과 함께 정리한 [상세 권장 인터페이스 초안](change_requests/CR-AMR_09-08_13-54_E-stop_reset과_PatrolReport_ACK_인터페이스_명세.md)은 영향 팀 합의 전 제안이다.

통신 두절 때 관제는 보고서를 대필하지 않는다. 결과가 없는 임무를 UNREPORTED로 유지하고 UNREPORTED를 PatrolReport 결과 enum에 추가하지 않는다. 늦은 report가 도착하면 현재 UNREPORTED를 해제하되 발생·해제 이력은 보존한다.

권장 reason code 표는 다음과 같다. FIRE_DETECTED=702를 설계 기준으로 유지한다.

~~~text
0    NONE
100  CONTROL_CANCELED
101  COMMAND_SUPERSEDED
102  SAFETY_POLICY_CANCELED
200  INVALID_COMMAND
201  INVALID_TARGET
202  UNSUPPORTED_COMMAND
203  COMMAND_ID_CONFLICT
204  INVALID_MISSION
205  INVALID_PARAMETERS
206  INVALID_STATE
300  NAV_NO_PATH
301  NAV_TIMEOUT
302  NAV_GOAL_REJECTED
303  NAV_GOAL_ABORTED
400  SAFE_ZONE_NOT_FOUND
401  KEEPOUT_APPLY_FAILED
402  KEEPOUT_ROLLBACK_FAILED
500  LOCALIZATION_INVALID
501  POSE_STALE
502  LIDAR_VERIFICATION_FAILED
600  DRIVE_TOKEN_MISSING
601  DRIVE_TOKEN_EXPIRED
602  COMMUNICATION_LOST
700  E_STOP_ACTIVE
701  OBSTACLE_BLOCKED
702  FIRE_DETECTED
800  BATTERY_LOW
801  BATTERY_CRITICAL
900  DOCKING_TIMEOUT
901  ROLE_HANDOFF
1000 SENSOR_ERROR
1001 INTERNAL_ERROR
~~~

200~206은 CommandCheck의 REJECTED 원인과 최종 PatrolReport의 관련 실패 원인에 공통으로 사용할 수 있다. 203은 같은 command ID의 payload 불일치, 204는 누락·종료·대상 불일치 mission, 205는 `parameters_json`이 아니라 명령별 필수 필드·값 조합 오류, 206은 현재 mission·로봇 상태에서 허용되지 않는 명령을 뜻한다.

## 6. CameraState와 Patrol Permit

~~~text
std_msgs/Header header
string event_id
string camera_id
string source_session_id
uint64 source_sequence
uint8 state
float32 confidence
~~~

CameraState는 차량 상태 계약이며 vehicle_track_id는 사용하지 않는다. 차량은 한 대만 존재한다. gate topic은 ENTERING/EXITED, center topic은 PARKED/EXITING만 허용한다. 잘못된 enum은 폐기하고 진단 로그를 남긴다. event ID는 1.2절 형식을 사용하고 source_session_id·source_sequence를 별도 필드로 전달해 ID 문자열을 파싱하지 않고 재시작·순서를 확인한다. state의 정수 매핑과 camera_id 값은 TBD-IF-005다.

patrol_allowed는 Bool이며 초기 true, ENTERING/EXITING에서 false, PARKED/EXITED에서 true다. 이벤트 쌍·timeout 정책은 [vision.md](vision.md)를 따른다. 이 Bool 자체는 주행 명령이 아니다.

## 7. Keepout과 속도 제어 경계

2026-09-08 확정된 이중 Keepout parameter 조합은 다음과 같다.

| 대상 노드 | 기본 빨간 영역 | 노란 중앙통로 |
|---|---|---|
| /robot1/global_costmap/global_costmap | `base_keepout_filter.enabled=true` | `center_corridor_keepout_filter.enabled` |
| /robot1/local_costmap/local_costmap | `base_keepout_filter.enabled=true` | `center_corridor_keepout_filter.enabled` |
| /robot6/global_costmap/global_costmap | `base_keepout_filter.enabled=true` | `center_corridor_keepout_filter.enabled` |
| /robot6/local_costmap/local_costmap | `base_keepout_filter.enabled=true` | `center_corridor_keepout_filter.enabled` |

위 값은 parameter 이름과 소유 노드의 조합이며 한 개의 토픽 경로가 아니다. `base_keepout_filter.enabled`는 AMR 시작 시 항상 true이고 관제가 변경하지 않는다. `center_corridor_keepout_filter.enabled`의 초기값은 false이며 관제는 `/vision/cctv/patrol_allowed=false`일 때 true, `patrol_allowed=true`일 때 false를 요청한다.

관제는 robot1·robot6의 global/local 중앙통로 parameter를 논리적으로 하나의 transaction으로 조정한다. 서로 다른 노드 API 호출을 원자적 작업이라고 가정하지 않는다. 전체 대상 snapshot, 적용, 두 값 read-back과 lifecycle 확인, 실패 시 전체 snapshot rollback을 수행한다. Q-07의 timeout·재시도를 적용하며 일부 성공을 commit하지 않는다. rollback 실패 시 Keepout 상태를 UNKNOWN으로 판단하고 Safety Arbiter 정지를 요청한다.

AMR은 두 mask server·두 costmap filter info server와 global/local costmap의 두 KeepoutFilter를 제공한다. parameter 계약의 근거는 [AMR 이중 Keepout 요청서](change_requests/CR-AMR_09-08_13-02_이중_Keepout_parameter_계약.md)다. 정식 Keepout 상태 토픽과 실환경 lifecycle·read-back·주행 검증은 TBD-IF-008에 남긴다.

local_safety_supervisor는 로봇별 최종 속도 출력의 유일한 발행자다. 전역 /cmd_vel을 두 로봇이 공유하도록 구성하지 않는다.

2026-09-08 TBD-IF-009 결정으로 경로가 확정됐다. Nav2 표준 체인을 유지하고 끝단에만 안전 게이트를 넣는다.

```text
controller_server·behavior_server → /robotN/cmd_vel_nav
  → velocity_smoother            → /robotN/cmd_vel_smoothed
  → collision_monitor            → /robotN/cmd_vel_safe
mission_supervisor(yaw 정렬)      → /robotN/cmd_vel_yaw
  → local_safety_supervisor      → /robotN/cmd_vel  → 구동부
```

후보 두 토픽은 `geometry_msgs/TwistStamped`이며 Nav2 노드에 `enable_stamped_cmd_vel: true`를 적용한다. 후보의 `header.stamp` 신선도 기준은 Q-17이다. namespace는 `robot_id`에서 파생하고 관제 launch는 `PushRosNamespace`·`RewrittenYaml`을 사용한다. `cmd_vel_yaw`는 `mission_supervisor`가 단독 발행한다. 두 후보 사이의 주행 중재는 [TBD-AMR-001](amr.md#tbd)로 남는다. 적용 근거는 [요청서](change_requests/CR-AMR_09-08_08-31_최종_cmd_vel_경로와_주행_후보_토픽.md)와 [확정 회신](change_requests/CR-AMR_09-08_10-06_AMR_cmd_vel_계약_5개_확정_회신.md)을 따른다.

## 8. Battery enum과 임계값

~~~text
UNKNOWN=0
CRITICAL=1
LOW=2
NORMAL=3
CHARGING=4
PATROL_READY=5
FULL=6
~~~

| 상태 구분 | SOC | 결과 |
|---|---|---|
| 방전 중 | < 0.10 | CRITICAL |
| 방전 중 | 0.10 이상, 0.20 미만 | LOW |
| 방전 중 | 0.20 이상 | NORMAL |
| 충전 중 | < 0.50 | CHARGING |
| 충전 중 | 0.50 이상, 0.80 미만 | PATROL_READY |
| 충전 중 | 0.80 이상 | FULL |
| 무효·미수신 | 해당 없음 | UNKNOWN |

CRITICAL 진입은 즉시, 나머지 전이는 조건 연속 유지 후 적용한다. 유지 시간은 9절, 센서 신선도·충전 방향 판정은 [TBD-AMR-003](amr.md#tbd)다.

관제 임무 정책은 다음과 같다. CRITICAL이면 현재 waypoint 완료를 기다리지 않고 즉시 복귀 또는 도킹을 판단한다. LOW이면 새 mission을 시작하지 않고 현재 mission의 순찰·복귀·도킹까지 완료한다. LOW 상태에서 CRITICAL로 전환되면 mission 완료 대기를 중단한다. UNKNOWN은 신규 순찰과 교대 투입 대상에서 제외한다. 이 정책은 E-stop, token, permit과 AMR 로컬 안전을 우회하지 않는다.

도킹 성공은 도킹 완료 센서가 DOCKED를 보고하고 CHARGING 상태가 모두 2초 연속 유지될 때다. 도킹 timeout은 DOCKING 진입 후 60초다. 기존 3초 기준을 변경한 결정이며 [관제 수정 요청서](change_requests/CR-관제_09-07_15-55_AMR_명령_토큰_상태_안전_계약_변경.md)로 AMR 반영을 요청한다.

## 9. QoS와 공통 시간·거리 기준

| Topic | Reliability | Durability | History | 추가 |
|---|---|---|---|---|
| mission_command | RELIABLE | VOLATILE | KEEP_LAST(10) | command ID 중복 제거 |
| command_check | RELIABLE | VOLATILE | KEEP_LAST(10) | command ID 연결, Check timeout 5초 |
| drive_token | BEST_EFFORT | VOLATILE | KEEP_LAST(3) | deadline 200 ms, lifespan 500 ms |
| robot_status | RELIABLE | VOLATILE | KEEP_LAST(5) | deadline 500 ms |
| patrol_report | RELIABLE | VOLATILE | KEEP_LAST(20) | 결과 ID 연결 |
| CCTV event | RELIABLE | VOLATILE | KEEP_LAST(20) | 과거 이벤트 replay 방지 |
| patrol_allowed | RELIABLE | VOLATILE | KEEP_LAST(1) | deadline 500 ms, timeout 시 마지막 값 유지 |
| estop | RELIABLE | TRANSIENT_LOCAL | 단일 상태, 정확한 depth TBD | 발행자 하나 |
| heartbeat | BEST_EFFORT | VOLATILE | KEEP_LAST(3) | 5 Hz, 애플리케이션 timeout 1초 |
| Detection·증적 | TBD | TBD | TBD | 계약 결정 필요 |

| 기준 ID | 대상 | 값·규칙 |
|---|---|---|
| Q-01 | Drive Token | 발행 5 Hz, lease 1.0초, AMR 로컬 monotonic 경과 측정; control session·token ID·message sequence 구분 |
| Q-02 | RobotStatus | 정기 2 Hz; mission/safety/battery enum 또는 pose_valid 변경 즉시, 변경 발행 최대 10 Hz |
| Q-03 | 관제 STALE | RobotStatus 미수신 1.5초 시 신규 mission·token 갱신 중단 |
| Q-04 | 복구 수신 게이트 | RobotStatus 정상 수신 5초 연속 |
| Q-05 | 주행 재개 pose | pose_valid=true, pose age ≤ 1.5초 |
| Q-06 | 복구 참고 위치 검증 | 마지막 pose age ≤ 30초, AMR2 LiDAR 오차 ≤ 0.5 m, 방향 오차 ≤ 15도, 3회 연속 |
| Q-07 | Keepout 시도 | 시도당 timeout 2초, 총 2회, 첫 실패 후 200 ms 대기 |
| Q-08 | 안전구역 후보 | Keepout 밖 free cell; footprint-장애물 ≥ 0.5 m, 차량 동선 ≥ 1.0 m, 경로 가능, 다른 AMR과 비중첩 |
| Q-09 | 도킹 | DOCKING 진입 후 60초 이내, DOCKED 완료 센서와 CHARGING 상태 2초 연속 확인 |
| Q-10 | E-stop | 활성화 즉시, 모든 활성 원인 제거 상태가 3초 연속일 때만 해제 가능; 조건 재발생 시 계수 초기화 |
| Q-11 | 배터리 전이 | CRITICAL 즉시; 기타 조건 3초 연속 |
| Q-12 | 화재 부저 OFF | DOCKED 완료 센서와 CHARGING 상태 2초 연속; 도킹 실패 시 다른 활성 화재가 없으면 OFF하고 관제 경고 |
| Q-13 | CCTV 중복 제거 | cam_master가 event_id 10분 보관 |
| Q-14 | 명령 중복 제거 | 24시간 이내 전체 보존, 24시간 경과 항목 중 최신 1,000개 유지 |
| Q-15 | CommandCheck | 각 시도 5초, 동일 command ID·payload 최대 2회 재전송 |
| Q-16 | heartbeat | 발행 5 Hz, AMR 애플리케이션 timeout 1초 |
| Q-17 | 주행 후보 신선도 | 후보 `header.stamp` 기준 age ≤ 0.5초. 초과 또는 미수신 시 최종 속도 출력 정지 ([TBD-IF-009 결정](change_requests/CR-AMR_09-08_08-31_최종_cmd_vel_경로와_주행_후보_토픽.md)) |

QoS deadline과 애플리케이션 timeout은 서로 다르다. patrol_allowed의 실제 반복 발행 주기·경고 timeout, 상태 변경 발행의 합산 rate 제한 방식은 TBD-IF-010이다. 지연·age 판정은 timestamp 출처와 수신 경과를 명시한 뒤 구현한다.

## 10. 관제 판단 결과와 공용 로그 계약

관제는 상태·통신 이상·경고·보고 누락 등 운영 판단 결과를 토픽으로 제공하고 시스템 모니터는 수신한 결과를 표시한다. 모니터는 STALE·timeout·UNREPORTED를 자체적으로 판정하지 않는다. AMR의 로컬 안전·감지와 비전의 차량 상태·permit 생성 책임은 기존 기능 계약을 따른다.

팀 간 전달하는 로그의 메시지 필드·타입·ID·시간 의미·토픽·QoS·발행 주기·재전송·중복 전달 계약은 이 문서가 기준이다. 관제 판단 결과와 공용 로그의 상세 계약은 TBD-IF-011에서 합의하며 기존 메시지와 중복되는 필드는 해당 TBD를 참조한다. 새 토픽명이나 필드 수치는 아직 확정하지 않는다.

`CONTROL_SHUTDOWN`, `COMMAND_CHECK_TIMEOUT`, `ACCEPTED_MISSING`은 E-stop reason이나 AMR CommandCheck reason이 아니라 관제 운영 이벤트다. 정상 Ctrl+C/SIGINT 종료는 `CONTROL_SHUTDOWN`으로 기록하고 운영 이벤트 ID의 event_type에는 `control-shutdown`을 사용한다. 가능하면 token 회수를 best-effort로 발행한 다음 token·heartbeat 발행을 종료한다. 비정상 종료에서는 이 이벤트나 마지막 회수 메시지 전달을 보장하지 않으며 안전 보장은 AMR의 token lease·heartbeat timeout이 담당한다.

관제 재기동은 새 `control_session_id` 생성 → AMR의 이전 token 폐기 → Q-04 RobotStatus 정상 수신과 pose·배터리·permit·Keepout·E-stop 게이트 확인 → 새 Drive Token 발급 → 별도 START_PATROL 또는 RESUME_PATROL 발행 순서다. 새 token 발급 전 다음 단계로 진행하지 않고, token만으로 이동을 시작하지 않는다. 운영 이벤트의 토픽·메시지 필드·전달 QoS는 TBD-IF-011에 남긴다.

DB 테이블·컬럼 매핑·인덱스·보존·백업 등 내부 저장 설계는 [monitoring_and_data.md](monitoring_and_data.md)의 TBD-MON-001에 둔다. 내부 DB 변경이 공용 메시지 계약을 자동으로 변경하지 않는다.

## TBD

아래 미정 항목은 모두 v1.0 완료 조건에서 제외하고 차기 버전으로 이관한다. 결정 시 이 표에 일자·근거·요청서 링크를 추가한다. `일부 결정`은 나열한 잔여 항목을 차기 버전 구현 전에 추가 합의해야 한다는 뜻이다.

| ID | 결정할 내용·현재 상태 | 영향 단위 |
|---|---|---|
| TBD-IF-001 | **결정(2026-09-08):** CommandCheck 0~3 수치, 정상·복구 예외·역방향 전이, 일치하는 EXECUTING 후 재전송 중단, 명령별 mission/target, `parameters_json` 제거, 203~206 reason code, `target_pose` 필드 유지·기본값 강제, robot별 default plan ID. [기존 요청서](change_requests/CR-관제_09-07_15-55_AMR_명령_토큰_상태_안전_계약_변경.md) · [관제 요청서](change_requests/CR-관제_09-08_15-15_AMR_명령_Heartbeat_E-stop_상태_계약.md) · [AMR 확정 회신](change_requests/CR-AMR_09-08_17-00_명령_Heartbeat_E-stop_상태_계약_확정_회신.md) | AMR·관제 |
| TBD-IF-002 | **일부 결정(2026-09-07):** control session, token ID, message sequence, holder 회수·교대·정지 기준. 잔여: 송신 timestamp 기반 message age 검증. [요청서](change_requests/CR-관제_09-07_15-55_AMR_명령_토큰_상태_안전_계약_변경.md) | AMR·관제 |
| TBD-IF-003 | **일부 결정(2026-09-08):** RobotStatus·PatrolReport 의미 필드와 ID 연결, safety_state 0~5와 의미, 유효 ID의 최종 report 수락, AMR 로컬 영속 outbox·동일 report ID 발행 구현. 잔여: waypoint·visit·scan 상세 타입, 안전구역 계산 결과·도착 보고, 수신 애플리케이션 저장 ACK와 ACK 이후 큐 삭제 조건. [관제 요청서](change_requests/CR-관제_09-07_15-55_AMR_명령_토큰_상태_안전_계약_변경.md) · [AMR 계약 요청서](change_requests/CR-관제_09-08_15-15_AMR_명령_Heartbeat_E-stop_상태_계약.md) · [AMR ACK 검토 요청서](change_requests/CR-AMR_09-08_10-42_PatrolReport_ACK와_큐_삭제_조건_검토.md) · [상세 제안](change_requests/CR-AMR_09-08_13-54_E-stop_reset과_PatrolReport_ACK_인터페이스_명세.md) | AMR·관제·시스템 모니터 |
| TBD-IF-004 | **v1.0 일부 결정(2026-09-08):** `ControlHeartbeat` 타입·필드·5 Hz·1초 timeout·QoS, E-stop reason 0~6, 전체 대상 `all`, 대표 원인 발행과 우선순위 `SYSTEM_FAULT → UNKNOWN → OPERATOR → KEEPOUT_FAILURE → COMMUNICATION → OBSTACLE → TOKEN`, 원인 제거 3초 해제, 하드웨어 E-stop·manual reset 제외. **차기 버전 이관:** 원인별 상세 활성/해제 조건·TRANSIENT_LOCAL depth, UI 요청 API와 전체 원인 집합 표시 계약. [AMR 요청서](change_requests/CR-관제_09-08_15-15_AMR_명령_Heartbeat_E-stop_상태_계약.md) · [System monitor 요청서](change_requests/CR-관제_09-08_15-15_System_monitor_E-stop_UI_운영상태_연계.md) · [상세 제안](change_requests/CR-AMR_09-08_13-54_E-stop_reset과_PatrolReport_ACK_인터페이스_명세.md) | AMR·관제·시스템 모니터 |
| TBD-IF-005 | **일부 결정(2026-09-07):** CCTV event ID와 source session·sequence 필드. 잔여: CameraState 패키지, state 정수값, camera_id 값 | 비전·관제 |
| TBD-IF-006 | **일부 결정(2026-09-07):** Detection event ID 형식. 잔여: Candidate/Event 필드·enum·토픽·QoS·발행자·중복 보존 | AMR·관제·시스템 모니터 |
| TBD-IF-007 | **일부 결정(2026-09-07):** evidence ID 형식. 잔여: 메타데이터·전송 방법·결과 ACK·재전송·실패 계약 | AMR·관제·시스템 모니터 |
| TBD-IF-008 | **일부 결정(2026-09-08):** base Keepout 상시 ON·관제 변경 금지, center corridor global/local parameter 이름·초기값·permit 대응과 transaction 대상. 잔여: 정식 Keepout 상태 토픽·필드, 실환경 lifecycle/read-back 검증, BatteryEvent·ActionFeedback 필요 여부. [AMR 요청서](change_requests/CR-AMR_09-08_13-02_이중_Keepout_parameter_계약.md) | AMR·관제·시스템 모니터 |
| TBD-IF-009 | **결정(2026-09-08):** 최종 `/robotN/cmd_vel`, 후보 `/robotN/cmd_vel_safe`·`/robotN/cmd_vel_yaw`, `enable_stamped_cmd_vel: true`, Q-17 후보 신선도 0.5초, namespace는 `robot_id` 파생, `cmd_vel_yaw`는 `mission_supervisor` 단독 발행. 후보 중재는 TBD-AMR-001로 남는다. [요청서](change_requests/CR-AMR_09-08_08-31_최종_cmd_vel_경로와_주행_후보_토픽.md) · [확정 회신](change_requests/CR-AMR_09-08_10-06_AMR_cmd_vel_계약_5개_확정_회신.md) | AMR·관제 |
| TBD-IF-010 | OPEN: permit 발행·경고 timeout, RobotStatus 변경 발행 rate 제한의 세부 의미 | AMR·관제·시스템 모니터·비전 |
| TBD-IF-011 | **일부 결정(2026-09-08):** 관제 운영 event ID 형식과 `CONTROL_SHUTDOWN`·`COMMAND_CHECK_TIMEOUT`·`ACCEPTED_MISSING` 분류, 정상 종료·재기동 순서. 잔여: 표시용 토픽과 공용 로그 필드·타입·시간·QoS·발행 정책·초기 상태·재연결·중복 전달. [System monitor 요청서](change_requests/CR-관제_09-08_15-15_System_monitor_E-stop_UI_운영상태_연계.md) | AMR·관제·시스템 모니터·비전 |

Detection 알고리즘 수치는 [amr.md의 TBD](amr.md#tbd), 다중 PC 실행 순서는 [integration.md의 TBD](integration.md#tbd)에 둔다. 결정된 공용 계약은 [수정 요청 절차](change_requests/README.md)를 거쳐 적용 상태를 추적한다.
