# 공용 ROS 2 인터페이스

> 기준: [2026-09-07 PM 설계 결정](decisions/2026-09-07-design-baseline.md). 관제는 별도 노드, 시스템 모니터는 UI 전용, 공용 패키지는 `patrol_interfaces`이며 상세 계약은 System design의 확정 내용을 우선한다.

상태: 기존 계약과 권장 스키마를 구분한 설계 초안 · 담당: AMR·관제·시스템 모니터·비전 공동

이 문서는 통신 이름, 메시지 필드·enum, ID, QoS와 공통 시간 기준의 원본이다. 완전한 .msg 구현 정의가 없는 타입은 TBD로 표시한다. 아래 값은 공유 설계 기준이며 실제 동작 검증 결과가 아니다.

## 1. 이름과 송수신

아래 {robot}에는 슬래시 없는 robot1 또는 robot6을 넣는다. 예: /robot1/mission_command. [식별 매핑](architecture.md#2-식별-체계)을 따른다.

| 인터페이스 | 타입·방식 | 송신 → 수신 | 상태 |
|---|---|---|---|
| /{robot}/mission_command | patrol_interfaces/msg/MissionCommand | 관제 → AMR | 필드 권장안, 상세 유효성 TBD |
| /control/drive_token | patrol_interfaces/msg/DriveToken | 관제 → AMR 로컬 안전 | 필드 권장안, 재시작·age 검증 TBD |
| /{robot}/robot_status | patrol_interfaces/msg/RobotStatus | AMR → 관제·시스템 모니터 | 전체 필드 TBD |
| /{robot}/patrol_report | patrol_interfaces/msg/PatrolReport | AMR → 관제·시스템 모니터 | 전체 필드 TBD |
| /vision/cctv/gate_event | CameraState | gate_cam → cam_master | 패키지명·enum 수치 TBD |
| /vision/cctv/center_event | CameraState | center_cam → cam_master | 패키지명·enum 수치 TBD |
| /vision/cctv/patrol_allowed | std_msgs/msg/Bool | cam_master → 관제·시스템 모니터 | 정책 기준 있음 |
| /control/heartbeat | TBD | 관제 → AMR 로컬 안전 | TBD-IF-004 |
| /control/estop | 전용 E-stop 메시지, 전체 정의 TBD | Safety Arbiter → AMR·시스템 모니터 | 단일 발행, TBD-IF-004 |
| 로봇별 Keepout 설정 | Nav2 parameter API | 관제 → AMR global/local costmap | 계획 경로, 실환경 확인 필요 |
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
│   │   ├── robot_status                RobotStatus: AMR1 → 관제·System monitor
│   │   └── patrol_report               PatrolReport: AMR1 → 관제·System monitor
│   ├── /robot6                         [AMR2 / AMR 팀]
│   │   ├── mission_command             MissionCommand: 관제 → AMR2
│   │   ├── robot_status                RobotStatus: AMR2 → 관제·System monitor
│   │   └── patrol_report               PatrolReport: AMR2 → 관제·System monitor
│   ├── /control                        [관제 팀]
│   │   ├── drive_token                 DriveToken: 관제 → 각 AMR 로컬 안전
│   │   ├── heartbeat                   타입 TBD: 관제 → 각 AMR 로컬 안전 [TBD-IF-004]
│   │   └── estop                       타입 상세 TBD: Safety Arbiter → AMR·System monitor
│   │                                   단일 발행자 [TBD-IF-004]
│   └── /vision/cctv                    [비전 팀]
│       ├── gate_event                  CameraState: gate_cam → cam_master
│       ├── center_event                CameraState: center_cam → cam_master
│       └── patrol_allowed              std_msgs/msg/Bool: cam_master → 관제·System monitor
├── Keepout parameter API               [관제 → AMR; 토픽이 아닌 노드/parameter 조합]
│   ├── /robot1/global_costmap/global_costmap → keepout_filter.enabled
│   ├── /robot1/local_costmap/local_costmap   → keepout_filter.enabled
│   ├── /robot6/global_costmap/global_costmap → keepout_filter.enabled
│   └── /robot6/local_costmap/local_costmap   → keepout_filter.enabled
│                                       계획 경로·실환경 확인 [TBD-IF-008 / 7절]
├── AMR 내부 연결                       [robot1·robot6에 각각 적용]
│   ├── mission_supervisor → Nav2       내부 Action; 정확한 이름·타입은 미기재
│   ├── 감지 처리 → 확정 처리           DetectionCandidate [TBD-IF-006]
│   ├── Nav2·yaw 주행 후보 → local_safety_supervisor
│   │                                   속도 토픽·타입·remap [TBD-IF-009]
│   └── local_safety_supervisor → 구동부
│                                       로봇별 최종 속도 출력 [TBD-IF-009]
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

## 2. MissionCommand

권장 필드(설계 제안):

~~~text
std_msgs/Header header
string command_id
string robot_id
uint8 command
string target_id
geometry_msgs/PoseStamped target_pose
string issued_by
string parameters_json
~~~

| command | 값 |
|---|---|
| STOP | 0 |
| START_PATROL | 1 |
| MOVE_TO_SAFE_ZONE | 2 |
| RESUME_PATROL | 3 |
| DOCK | 4 |
| CANCEL | 5 |

관제는 command_id를 UUID v4로 생성한다. 같은 내용의 재전송은 같은 ID, 내용·목적 변경은 새 ID다. AMR은 최근 24시간 또는 최근 1,000개 ID를 영속 저장하고 중복 실행하지 않는다. 이 두 보존 조건의 우선순위·삭제 정책은 TBD-IF-001이다.

메시지 robot_id와 수신 로봇 namespace 매핑이 일치해야 한다. command별 target_id/target_pose 필수 여부와 우선순위, parameters_json 스키마, 명령 수신 확인·동일 ID에 다른 내용이 왔을 때 처리는 TBD-IF-001이다.

## 3. DriveToken

권장 필드(설계 제안):

~~~text
std_msgs/Header header
string token
string holder_robot_id
builtin_interfaces/Duration lease_duration
uint32 sequence
~~~

- 공통 /control/drive_token을 사용한다. holder_robot_id는 robot1 또는 robot6이다.
- token이 빈 문자열이면 관제가 권한을 회수한 상태다.
- 다른 holder의 토큰은 자신의 주행 권한으로 수락하지 않는다.
- token 문자열이 바뀌면 기존 token을 즉시 무효화한다.
- 발급·갱신·명시적 해제 결정권은 관제에 있다.
- sequence가 마지막 수락 값 이하인 메시지, 만료 메시지, 다른 로봇용 토큰은 폐기한다. callback 수신 시각만으로 lease를 연장하지 않는다.
- 만료·회수 시 신규 주행을 차단하고 안전 정지한다. 새 토큰 수신만으로 자동 출발하지 않는다.

시간값은 9절을 따른다. 새 token과 sequence 재설정의 순서, 관제 재시작·uint32 wraparound, 공통 토픽에서 다른 holder로 교체될 때의 무효화·폐기 순서는 TBD-IF-002다. 보장되지 않은 시간 동기화로 서로 다른 monotonic clock을 직접 비교하지 않는다. 송신 timestamp와 로컬 lease의 결합 방식도 해당 TBD에서 결정한다.

## 4. RobotStatus

전체 필드 및 정확한 메시지 레이아웃은 TBD-IF-003이다. 다음 의미는 보존한다.

- 위치 frame은 map이며 측정 시각과 covariance를 포함한다.
- pose_valid=false여도 마지막 유효 pose와 last-valid 시각/age를 보존한다. 이를 현재 유효 위치로 사용하지 않는다.
- operational, mission, docking, battery, safety 상태를 구분한다. safety enum과 필드 구조는 아직 미정이다.
- STALE은 관제가 수신 신선도를 판정하는 상태이며 아래 operational enum에 임의로 추가하지 않는다.

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

정기 및 변경 발행 기준은 9절을 따른다. 순찰 ID·방문 ID·waypoint·방문 시각·scan 상태·주행 결과는 필드 후보이며 타입·필수 여부는 TBD-IF-003이다.

## 5. PatrolReport

~~~text
SUCCEEDED=0
FAILED=1
CANCELED=2
~~~

SUCCEEDED는 목표 정상 달성, FAILED는 자체 장애·주행 실패·위치 검증 또는 시스템 실패, CANCELED는 관제 취소·명령 대체·정책 중단·역할 교대다. FAILED/CANCELED는 reason_code를 필수로 하며 reason에 구체적 진단값을 기록한다.

통신 두절 때 관제는 보고서를 대필하지 않는다. 결과가 없는 임무를 UNREPORTED로 유지한다. UNREPORTED는 PatrolReport 결과 enum에 추가하지 않는다. command_id·mission/patrol ID·report ID 연결, 결과 재전송·중복 수신·복구 전달은 TBD-IF-003이다.

권장 reason code 표는 다음과 같다. FIRE_DETECTED=702를 설계 기준으로 유지한다.

~~~text
0    NONE
100  CONTROL_CANCELED
101  COMMAND_SUPERSEDED
102  SAFETY_POLICY_CANCELED
200  INVALID_COMMAND
201  INVALID_TARGET
202  UNSUPPORTED_COMMAND
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

## 6. CameraState와 Patrol Permit

~~~text
std_msgs/Header header
string event_id
string camera_id
uint8 state
float32 confidence
~~~

CameraState는 차량 상태 계약이며 vehicle_track_id는 사용하지 않는다. 차량은 한 대만 존재한다. gate topic은 ENTERING/EXITED, center topic은 PARKED/EXITING만 허용한다. 잘못된 enum은 폐기하고 진단 로그를 남긴다. state의 정수 매핑·camera_id 값·event_id 생성 규칙은 TBD-IF-005다.

patrol_allowed는 Bool이며 초기 true, ENTERING/EXITING에서 false, PARKED/EXITED에서 true다. 이벤트 쌍·timeout 정책은 [vision.md](vision.md)를 따른다. 이 Bool 자체는 주행 명령이 아니다.

## 7. Keepout과 속도 제어 경계

계획된 노드/파라미터 조합:

| 대상 노드 | parameter |
|---|---|
| /robot1/global_costmap/global_costmap | keepout_filter.enabled |
| /robot1/local_costmap/local_costmap | keepout_filter.enabled |
| /robot6/global_costmap/global_costmap | keepout_filter.enabled |
| /robot6/local_costmap/local_costmap | keepout_filter.enabled |

이는 parameter 이름과 소유 노드의 조합이며 한 개의 토픽 경로가 아니다. 관제가 대상 로봇의 global/local costmap 설정을 논리적으로 하나의 transaction으로 조정한다. 서로 다른 노드 API 호출을 원자적 작업이라고 가정하지 않는다. snapshot, 적용·read-back·lifecycle 확인, 실패 시 rollback은 [control_server.md](control_server.md)에 정의한다.

AMR에는 KeepoutFilter, mask server, costmap_filter_info_server가 필요하다. 실제 노드명·지원 parameter·상태 보고 계약은 TBD-IF-008이다. 구성 예시는 amr.md에 있으며 실행 환경에 적용한 것이 아니다.

local_safety_supervisor는 로봇별 최종 속도 출력의 유일한 발행자다. 전역 /cmd_vel을 두 로봇이 공유하도록 구성하지 않는다. 실제 namespaced 출력·Nav2 입력 경로와 Twist/TwistStamped 타입은 TBD-IF-009다.

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

## 9. QoS와 공통 시간·거리 기준

| Topic | Reliability | Durability | History | 추가 |
|---|---|---|---|---|
| mission_command | RELIABLE | VOLATILE | KEEP_LAST(10) | command ID 중복 제거 |
| drive_token | BEST_EFFORT | VOLATILE | KEEP_LAST(3) | deadline 200 ms, lifespan 500 ms |
| robot_status | RELIABLE | VOLATILE | KEEP_LAST(5) | deadline 500 ms |
| patrol_report | RELIABLE | VOLATILE | KEEP_LAST(20) | 결과 ID 연결 |
| CCTV event | RELIABLE | VOLATILE | KEEP_LAST(20) | 과거 이벤트 replay 방지 |
| patrol_allowed | RELIABLE | VOLATILE | KEEP_LAST(1) | deadline 500 ms, timeout 시 마지막 값 유지 |
| estop | RELIABLE | TRANSIENT_LOCAL | 단일 상태, 정확한 depth TBD | 발행자 하나 |
| heartbeat·Detection·증적 | TBD | TBD | TBD | 계약 결정 필요 |

| 기준 ID | 대상 | 값·규칙 |
|---|---|---|
| Q-01 | Drive Token | 발행 5 Hz, lease 1.0초, AMR 로컬 monotonic 경과 측정 |
| Q-02 | RobotStatus | 정기 2 Hz; mission/safety/battery enum 또는 pose_valid 변경 즉시, 변경 발행 최대 10 Hz |
| Q-03 | 관제 STALE | RobotStatus 미수신 1.5초 시 신규 mission·token 갱신 중단 |
| Q-04 | 복구 수신 게이트 | RobotStatus 정상 수신 5초 연속 |
| Q-05 | 주행 재개 pose | pose_valid=true, pose age ≤ 1.5초 |
| Q-06 | 복구 참고 위치 검증 | 마지막 pose age ≤ 30초, AMR2 LiDAR 오차 ≤ 0.5 m, 방향 오차 ≤ 15도, 3회 연속 |
| Q-07 | Keepout 시도 | 시도당 timeout 2초, 총 2회, 첫 실패 후 200 ms 대기 |
| Q-08 | 안전구역 후보 | Keepout 밖 free cell; footprint-장애물 ≥ 0.5 m, 차량 동선 ≥ 1.0 m, 경로 가능, 다른 AMR과 비중첩 |
| Q-09 | 도킹 | DOCKING 진입 후 60초 이내, 접점 또는 완료 센서 3초 연속 확인 |
| Q-10 | E-stop | 활성화 즉시, 자동 해제 조건 3초 연속; 물리 E-stop은 수동 reset까지 latch |
| Q-11 | 배터리 전이 | CRITICAL 즉시; 기타 조건 3초 연속 |
| Q-12 | 화재 부저 OFF | 설계 기준은 CHARGING 3초 연속 및 DOCKED; 도킹 센서와 관계는 TBD-AMR-004 |
| Q-13 | CCTV 중복 제거 | cam_master가 event_id 10분 보관 |
| Q-14 | 명령 중복 제거 | AMR 영속 저장: 최근 24시간 또는 1,000개, 삭제 조건 TBD-IF-001 |

QoS deadline과 애플리케이션 timeout은 서로 다르다. patrol_allowed의 실제 반복 발행 주기·경고 timeout, 상태 변경 발행의 합산 rate 제한 방식은 TBD-IF-010이다. 지연·age 판정은 timestamp 출처와 수신 경과를 명시한 뒤 구현한다.

## 10. 관제 판단 결과와 공용 로그 계약

관제는 상태·통신 이상·경고·보고 누락 등 운영 판단 결과를 토픽으로 제공하고 시스템 모니터는 수신한 결과를 표시한다. 모니터는 STALE·timeout·UNREPORTED를 자체적으로 판정하지 않는다. AMR의 로컬 안전·감지와 비전의 차량 상태·permit 생성 책임은 기존 기능 계약을 따른다.

팀 간 전달하는 로그의 메시지 필드·타입·ID·시간 의미·토픽·QoS·발행 주기·재전송·중복 전달 계약은 이 문서가 기준이다. 관제 판단 결과와 공용 로그의 상세 계약은 TBD-IF-011에서 합의하며 기존 메시지와 중복되는 필드는 해당 TBD를 참조한다. 새 토픽명이나 필드 수치는 아직 확정하지 않는다.

DB 테이블·컬럼 매핑·인덱스·보존·백업 등 내부 저장 설계는 [monitoring_and_data.md](monitoring_and_data.md)의 TBD-MON-001에 둔다. 내부 DB 변경이 공용 메시지 계약을 자동으로 변경하지 않는다.

## TBD

모든 항목은 OPEN이다. 결정 시 이 표에 일자·근거·요청서 링크를 추가한다.

| ID | 결정할 내용 | 영향 단위 |
|---|---|---|
| TBD-IF-001 | 명령별 필수 필드·JSON·수신 확인, ID 충돌, 24시간/1,000개 보존 정책 | AMR·관제 |
| TBD-IF-002 | token epoch/sequence 재시작·wraparound, holder 교체 순서, message age 검증 | AMR·관제 |
| TBD-IF-003 | RobotStatus·PatrolReport 전체 필드, safety enum, 순찰·방문·결과 ID, 결과 복구 전달 | AMR·관제·시스템 모니터 |
| TBD-IF-004 | heartbeat 타입·주기·timeout, E-stop 필드·범위·depth·해제 요청 계약 | AMR·관제·시스템 모니터 |
| TBD-IF-005 | CameraState 패키지, state 정수값, camera_id·event_id 생성 규칙 | 비전·관제 |
| TBD-IF-006 | DetectionCandidate/Event 필드·enum·토픽·QoS·ID·발행자, 확정 이벤트 중복 보존 | AMR·관제·시스템 모니터 |
| TBD-IF-007 | 증적 메타데이터·전송 방법·결과 ACK·재전송·실패 계약 | AMR·관제·시스템 모니터 |
| TBD-IF-008 | Keepout 상태 토픽·필드와 실parameter, BatteryEvent·ActionFeedback 필요 여부 | AMR·관제·시스템 모니터 |
| TBD-IF-009 | 로봇별 최종 cmd_vel 및 Nav2·yaw 입력 토픽, 타입·remap·중재 | AMR·관제 |
| TBD-IF-010 | permit 발행·경고 timeout, RobotStatus 변경 발행 rate 제한의 세부 의미 | AMR·관제·시스템 모니터·비전 |
| TBD-IF-011 | 관제 판단 결과 표시용 토픽과 공용 로그 필드·타입·ID·시간·QoS·발행 정책·초기 상태·재연결·중복 전달 계약 | AMR·관제·시스템 모니터·비전 |

Detection 알고리즘 수치는 [amr.md의 TBD](amr.md#tbd), 다중 PC 실행 순서는 [integration.md의 TBD](integration.md#tbd)에 둔다. 결정된 공용 계약은 [수정 요청 절차](change_requests/README.md)를 거쳐 적용 상태를 추적한다.
