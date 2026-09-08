# Control Server 기능 설계

> 기준: [2026-09-07 PM 설계 결정](decisions/2026-09-07-design-baseline.md). 관제는 별도 노드, 시스템 모니터는 UI 전용, 공용 패키지는 `patrol_interfaces`이며 상세 계약은 System design의 확정 내용을 우선한다.

상태: 설계 초안 · 담당: 관제 팀 · 통합 실행 위치: PC 3 · 참조: [interfaces.md](interfaces.md), [integration.md](integration.md)

시스템 시나리오는 [scenarios.md](scenarios.md)를 따른다. 이 팀은 UC-01·02·03·04·05·06·07·08의 관제 판단·제어·로그 제공 범위를 담당하며, UC 전체를 단독 구현하는 것으로 해석하지 않는다.

## 1. 책임

관제는 robot1·robot6을 관리하고 명령, Drive Token, Keepout, 복구 게이트, 역할 교대를 결정한다. E-stop은 Safety Arbiter가 단일 발행한다. 별도 개발 단위인 시스템 모니터 팀의 모니터링·DB·Dashboard는 [monitoring_and_data.md](monitoring_and_data.md)에 둔다.

PC 3에서 함께 실행해도 시스템 모니터 팀의 코드 소유권과 수정 범위는 분리한다. 관제는 제어 판단과 화면에 제공할 운영 상태·통신 이상·경고·보고 누락 판단을 수행한다. 시스템 모니터는 관제가 토픽으로 제공한 판단 결과를 표시하고 이력을 저장·조회한다.

아래는 논리 기능 분할이며 독립 ROS 노드 수를 의미하지 않는다.

| 기능 | 책임 |
|---|---|
| Robot Command Manager | 명령 검증·중재·재전송·취소·대체 |
| Drive Token Manager | holder 선정, 발급·갱신·회수 |
| Robot State / Recovery Gate | 유효 상태·STALE·위치·재개 조건 관리 |
| Handover Manager | 배터리·거리 기반 가용 AMR 선정과 교대 |
| Emergency Controller / Safety Arbiter | 정지 원인 통합, 단일 E-stop, 해제 결정 |
| Traffic / Keepout Coordinator | permit 대응, Keepout transaction, 대피 조정 |
| ROS 2 Command Gateway | 결정된 명령·권한 발행, parameter API 호출 및 결과 전달 |

## 2. 명령과 권한

로봇 표시명은 AMR1/AMR2, 계약 식별자는 robot1/robot6이다. 관제는 외부 Nav2 Action을 호출하지 않고 MissionCommand로만 AMR에 임무를 요청한다.

### 2.1 식별자 규칙

2026-09-07 사용자 결정으로 UUID v4 대신 사람이 로그에서 식별할 수 있는 구조화 문자열 ID를 사용한다. ID는 추적·중복 제거용이며 제어 로직은 ID 문자열을 파싱하지 않고 별도 `robot_id`, `command`, `state`, `sequence` 필드를 사용한다. 영문 소문자, 숫자, 하이픈을 사용하며 순번은 최소 네 자리로 0을 채운다. source session은 `<source>-<YYYYMMDDTHHMMSS>[-<restart_sequence>]` 형식으로 프로세스 시작 시 생성하고 재시작 시 변경한다.

| 종류 | 형식 | 생성자·수명 |
|---|---|---|
| 관제 세션 | `ctrl-<YYYYMMDDTHHMMSS>[-<restart_sequence>]` | 관제 시작 시 생성, 재시작 시 변경 |
| mission | `msn-<control_session>-<robot_id>-<mission_sequence>` | 관제가 새 mission 시작 시 생성 |
| command | `cmd-<control_session>-<robot_id>-<command>-<sequence>` | 관제가 새 명령·대체 명령마다 생성 |
| Drive Token | `tok-<control_session>-<holder_robot_id>-<grant_sequence>` | 관제가 새 주행 권한을 부여할 때 생성 |
| PatrolReport | `rpt-<robot_session>-<report_sequence>` | AMR이 command 최종 결과마다 생성 |
| CCTV 차량 이벤트 | `cam-<camera_session>-<state>-<sequence>` | 비전 생산 ID의 관제 수신 형식 |
| AMR Detection | `det-<robot_session>-<event_type>-<sequence>` | AMR이 확정 이벤트마다 생성 |
| 증적 | `evi-<robot_session>-<event_sequence>-<evidence_sequence>` | AMR이 증적마다 생성 |
| 관제 운영 이벤트 | `op-<control_session>-<event_type>-<sequence>` | 관제가 STALE·경고·상태 변화마다 생성 |

시간만으로 유일성을 보장하지 않고 세션 내 증가 sequence를 함께 사용한다. command sequence는 robot이나 mission이 바뀌어도 초기화하지 않는 관제 전체 공통 순번이다. 같은 command의 재전송에는 같은 ID를 유지하고 내용·목적 변경에는 새 ID를 사용한다.

명령 ID의 command 표기는 `start`, `evacuate`, `resume`, `dock`, `stop`, `cancel`을 사용한다. mission ID는 command ID의 상위 개념이다. START_PATROL에서 새 mission ID를 생성하고, 해당 순찰의 대피·재개·복귀·도킹은 같은 mission ID와 각기 새로운 command ID를 사용한다. 완료·실패·취소된 mission 뒤의 새 START_PATROL과 독립 수동 DOCK에는 새 mission ID를 사용한다.

이 결정은 [interfaces.md](interfaces.md)에 공용 계약으로 반영했다. AMR·비전·시스템 모니터 기능 문서는 직접 수정하지 않고 각 생산·소비 단위의 검토와 수정 요청 절차로 반영한다.

### 2.2 MissionCommand와 CommandCheck

AMR은 MissionCommand를 받으면 다음 의미의 CommandCheck를 반환하고, 최종 결과는 PatrolReport로 반환한다.

| 상태 | 값 | 의미 |
|---|---:|---|
| CHECK_UNKNOWN | 0 | 초기·해석 불가 상태. 정상 응답으로 사용하지 않음 |
| CHECK_ACCEPTED | 1 | 형식·상태 검증을 통과하고 실행 대기열에 들어감 |
| CHECK_EXECUTING | 2 | 실제 command 실행을 시작함 |
| CHECK_REJECTED | 3 | command를 실행하지 않음 |

CommandCheck에는 `header`(stamp), `command_id`, `mission_id`, `robot_id`, `check_state`, `reason_code`, `reason`, `source_session_id`, `sequence`를 포함한다. 같은 command ID가 재수신되면 실행 전에는 기존 ACCEPTED, 실행 중에는 EXECUTING, 이미 끝났으면 기존 PatrolReport를 다시 보낸다. 같은 command ID에 다른 payload가 들어오면 `REJECTED / COMMAND_ID_CONFLICT`로 거절하고 관제가 경고를 발생시킨다.

충돌 비교 대상은 `robot_id`, `command`, `target_id`, `target_pose`, `mission_id`다. `parameters_json`은 계약에서 제거한다. 재전송에서는 원래 발급 시각과 payload를 유지하며 DDS 수신 시각은 비교하지 않는다.

Check timeout은 MissionCommand 최초 발행 후 해당 command ID의 ACCEPTED 또는 REJECTED를 기다리는 시간으로 5초다. timeout이면 동일 command ID와 동일 payload를 최대 2회 재전송한다. 이후에도 확인되지 않으면 관제 운영 이벤트 `COMMAND_CHECK_TIMEOUT`으로 판단하며 새 command ID를 자동 생성하지 않는다. EXECUTING 전환은 정상 Check timeout의 응답 조건이 아니다.

정상 전이는 ACCEPTED → EXECUTING이다. 역방향 전이는 항상 폐기한다. 관제 내부 WAITING 상태에서 ACCEPTED가 누락된 EXECUTING은 동일 command ID·mission ID·robot ID가 모두 일치하는 경우에만 `WAITING → EXECUTING` 복구 예외로 수락하고 `ACCEPTED_MISSING` 관제 운영 경고를 남긴다. 이때 재전송 중단 여부는 AMR과의 계약으로 남긴다. 중간 CommandCheck 일부가 누락돼도 유효한 ID의 PatrolReport는 최종 결과로 수락하고 경고만 기록한다. 정의되지 않은 check_state 숫자는 폐기한다.

명령 ID는 최소 24시간 보관한다. 1,000개를 초과해도 24시간 이내 항목은 삭제하지 않고, 24시간이 지난 항목 중 최신 1,000개는 유지한다. AMR은 전체 command ID 문자열을 중복 제거 키로 사용한다.

명령별 mission·target 계약은 [interfaces.md 2절](interfaces.md#2-missioncommand)을 따른다. START_PATROL은 새 mission ID와 `patrol_plan_id`, MOVE_TO_SAFE_ZONE은 기존 mission ID만 보내고 좌표 계산은 AMR에 맡긴다. RESUME_PATROL은 기존 mission ID, DOCK은 기존 또는 신규 mission ID와 robot별 `dock_1`·`dock_6` target_id만 사용한다. STOP은 활성 mission이 없어도 안전한 no-op ACCEPTED를 허용하고 재개 상태를 보존한다. CANCEL은 지정한 활성 mission 전체를 취소하며 재개 상태를 남기지 않고, 없거나 종료된 mission은 `REJECTED / INVALID_MISSION`이다. 현재 모든 명령에서 `target_pose`는 사용하지 않으며 필드 제거 여부는 AMR 검토 사항이다.

E-stop과 token 만료는 명령 우선순위가 아니라 독립 안전 계층이다. MissionCommand 간 우선순위는 STOP → MOVE_TO_SAFE_ZONE → DOCK → CANCEL → RESUME_PATROL → START_PATROL 순이다.

### 2.3 Drive Token

Drive Token 발급·갱신·회수는 관제가 결정하고 AMR은 별도의 로컬 검증·만료 책임을 가진다. token을 받은 사실과 mission을 실행하라는 명령은 분리한다. 발행은 5 Hz, lease는 1.0초다.

Drive Token에는 `control_session_id`, `token_id`, `holder_robot_id`, `lease_duration`, `message_sequence`를 포함한다. `token_id`는 새 권한을 부여할 때만 변경하고, `message_sequence`는 같은 관제 세션에서 갱신 메시지를 발행할 때마다 증가한다. 관제 재시작 시 control session을 변경하고 message sequence를 1부터 다시 시작한다. AMR은 새 control session을 받으면 이전 token을 무효화하며 새 token과 MissionCommand 없이는 자동 출발하지 않는다.

회수는 빈 `token_id`, 이전 `holder_robot_id`, 증가한 `message_sequence`로 발행한다. 예를 들어 robot1 회수는 `token_id=""`, `holder_robot_id="robot1"`로 표현한다. 다른 로봇으로 교대할 때는 회수 발행 → AMR 회수 수락 → 실제 정지 확인 → 신규 holder token 발급 순서를 지킨다.

실제 정지는 AMR odometry에서 선속도 절댓값 0.05 m/s 이하, 각속도 절댓값 0.1 rad/s 이하가 0.5초 연속 유지되고 속도 측정 age가 0.5초 이하일 때 확인한다. odometry가 오래됐거나 무효이면 정지 확인 실패다. 회수 메시지 수락만으로 정지를 단정하지 않으며 실제 정지를 확인하지 못하면 다른 로봇에 token을 발급하지 않는다.

## 3. RobotStatus와 통신 복구

수신 로봇 ID와 namespace를 확인하고 마지막 수신 시각·유효 pose를 추적한다. Q-03을 초과하면 관제의 상태를 STALE로 전환하고 신규 mission과 token 갱신을 중단한다. 결과 미수신 임무는 UNREPORTED로 유지하며 PatrolReport를 대필하지 않는다.

RobotStatus의 권장 의미 필드는 다음과 같다. 실제 ROS 타입·배치는 공용 인터페이스 반영 시 확정한다.

~~~text
header                       # RobotStatus snapshot 생성 시각
robot_id
source_session_id
status_sequence
operational_state
mission_state
docking_state
battery_state
safety_state
active_command_id
active_mission_id
pose                         # 자체 측정 시각 포함
pose_valid
last_valid_pose              # 자체 측정 시각 포함
linear_velocity
angular_velocity
motion_stopped
accepted_token_id
token_valid
battery_soc
battery_timestamp
current_waypoint_id
scan_state
reason_code
reason
~~~

`header.stamp`는 상태 snapshot 생성 시각, pose의 stamp는 pose 측정 시각, last_valid_pose의 stamp는 마지막 유효 pose 측정 시각이다. 관제 수신 시각은 관제 로컬에서 별도 기록하고 측정 시각으로 대체하지 않는다. `motion_stopped`는 2.3절의 속도·연속 유지·신선도 기준을 충족할 때만 true다.

`safety_state`는 UNKNOWN=0, NORMAL=1, STOPPING=2, STOPPED=3, ESTOPPED=4, ERROR=5를 사용한다. NORMAL은 이동 허가가 아니라 활성 로컬 안전 정지가 없다는 뜻이다. STOPPING은 출력 차단 후 정지 확인 중, STOPPED는 별도의 실제 정지 조건 확인 완료, ESTOPPED는 E-stop 활성 상태이며 그 자체로 속도 0을 증명하지 않는다. ERROR는 로컬 안전 계층 오류다. 구체적인 원인은 `reason_code`로 구분하고, `motion_stopped`와 속도 측정 age를 별도로 확인한다.

PatrolReport에는 `report_id`, `robot_id`, `source_session_id`, `command_id`, `mission_id`, `result`, `reason_code`, `reason`, `started_at`, `finished_at`, `final_waypoint_id`, `related_event_ids`를 포함하는 것을 기준으로 한다. command 하나가 최종 상태에 이를 때 report 하나를 생성하고, AMR은 MissionCommand에서 받은 command ID와 mission ID를 그대로 반환한다. 여러 command의 report가 같은 mission ID를 공유할 수 있다. 같은 report ID의 재전송은 중복 저장하지 않으며, 늦게 report가 도착하면 현재 UNREPORTED는 해제하되 발생·해제 이력은 보존한다.

복구 시 다음을 모두 확인한다.

1. Q-04 동안 RobotStatus를 정상 연속 수신한다.
2. Q-05의 pose_valid·pose age 기준을 충족한다.
3. E-stop이 해제되어 있다.
4. 필요한 Keepout 적용 상태와 배터리 조건이 충족된다.
5. 유효 Drive Token을 확보하고 재개 명령을 발행할 수 있다.

하나라도 실패하면 자동 순찰을 시작하지 않는다. Q-06의 오래된 pose는 복구 참고용이며 주행 재개 위치로 대체하지 않는다. 재개 가능한 배터리 상태는 NORMAL, PATROL_READY, FULL이며 배터리 입력이 유효하고 최신이어야 한다. RobotStatus 정상 수신은 Q-04의 5초 동안 계약에 맞는 연속 메시지를 받고 그 사이 Q-03의 STALE 조건이 다시 발생하지 않은 상태다.

정상 Ctrl+C/SIGINT 종료는 E-stop이 아니라 `CONTROL_SHUTDOWN` 관제 운영 이벤트(`control-shutdown`)다. 정상 종료 시 이벤트를 기록하고 가능한 경우 token 회수를 best-effort로 발행한 뒤 token·heartbeat 발행을 중단한다. 비정상 종료에서는 마지막 이벤트·회수 전달을 보장하지 않으며 AMR의 token lease와 heartbeat timeout이 안전 정지를 보장한다.

관제 재기동은 새 control session 생성 → AMR의 이전 token 폐기 → RobotStatus 정상 수신 5초와 pose·배터리·permit·Keepout·E-stop 게이트 확인 → 새 token 발급 → 별도 START_PATROL 또는 RESUME_PATROL 발행 순서로 진행한다. 새 token 발급 전 다음 단계로 진행하지 않고 token만으로 이동시키지 않는다.

## 4. 차량 상태와 Keepout

patrol_allowed=false는 정지 명령 그 자체가 아니다. 기존 순찰 취소 → Keepout ON → MOVE_TO_SAFE_ZONE → 도착 확인 → token 회수 순서로 조정한다. 대피 주행 중 필요한 token은 유지하되 E-stop·통신 등 독립 안전 조건은 계속 적용한다.

patrol_allowed=true는 E-stop·RobotStatus·Keepout 등 재개 조건 확인 → Keepout OFF → token 발급 → RESUME_PATROL 순서다. 빠른 permit 반전·중복 값에 따른 재진입 정책은 TBD-INT-002다.

Keepout transaction의 대상은 해당 로봇의 global/local costmap이다.

1. 전체 대상 parameter snapshot을 읽는다.
2. 목표값을 적용한다.
3. 전체 대상 read-back 및 lifecycle 확인이 성공하면 commit한다.
4. 일부 실패하면 전체 snapshot으로 rollback한다.
5. rollback 실패 시 Safety Arbiter에 정지를 요청하고 Keepout을 UNKNOWN으로 보고한다.

재시도 시간·횟수는 Q-07이다. rollback의 timeout·확인 절차와 재시도 중 상태 보장은 TBD-CTRL-002다. 서로 다른 노드 parameter 변경을 기본적으로 원자적이라고 취급하지 않는다.

안전구역 후보는 Q-08을 충족해야 한다. 후보가 없으면 현재 위치 정지와 SAFE_ZONE_NOT_FOUND 보고를 처리한다. mask·차량 동선 제공, 후보 계산 위치, Keepout ON 이전에 탈출 가능성을 어떻게 검증할지는 TBD-CTRL-002 및 TBD-INT-003이다.

Keepout과 안전구역의 세부 설계안은 AMR 팀이 먼저 제시하고 관제 담당자가 검토·확인한다. 제시안에는 실제 costmap 노드·parameter, lifecycle·read-back, 안전구역 계산 위치, 지도·차량 동선 공급, 탈출 경로 사전 검증, 대피 도착 기준, rollback 중 AMR 상태를 포함해야 한다. 검토 전에는 위 항목을 관제 구현에서 추측해 확정하지 않는다. 관제의 기존 Keepout transaction·대피 조정 책임은 유지하며 최종 책임 경계는 제시안 확인 후 공용 계약에 반영한다.

## 5. 도킹과 역할 교대

AMR은 도킹 실행·센서 성공 판정을 담당하고 관제는 실패를 받아 가용 AMR을 선정한다. 배터리 입력이 UNKNOWN이면 신규 순찰·교대 투입을 금지한다. CRITICAL은 현재 waypoint 완료를 기다리지 않고 관제가 즉시 복귀 또는 도킹을 판단한다. LOW는 새 mission을 시작하지 않고 현재 mission의 순찰·복귀·도킹까지 완료한다. LOW 상태에서 CRITICAL로 전환되면 mission 완료 대기를 중단하고 즉시 복귀 또는 도킹을 판단한다. 이 정책은 E-stop, token, permit과 로컬 안전을 우회하지 않으며 복귀 경로가 없으면 현재 위치 안전 정지와 실패를 보고한다.

교대 후보는 Battery 상태가 NORMAL, PATROL_READY 또는 FULL이고 pose·safety·통신 게이트를 통과한 로봇이다. 후보 점수는 배터리 60%, 인계 지점까지 거리 30%, 최근 장애·도킹 실패 이력 10%로 계산한다. 동점이면 유휴 시간이 긴 로봇, 다시 같으면 robot1 순으로 선택한다. 실제 점수 정규화와 장애 이력 구간은 구현 전에 시험 fixture로 고정한다.

도킹 성공은 DOCKED 센서와 CHARGING 상태가 모두 2초 연속 유지될 때로 한다. 이 결정은 interfaces.md의 Q-09·Q-12와 integration.md의 통합시험 기준에 반영했으며 AMR 기능 반영은 수정 요청서로 추적한다.

기존 AMR token 회수 후 새 command_id로 인계한다. 기존 임무 종료/대체와 새 임무의 연결 관계를 기록한다. 이전 로봇이 도킹하기 위한 주행과 새 로봇 순찰의 시간 관계는 TBD-INT-001에서 결정한다.

## 6. E-stop과 화재 경계

Safety Arbiter만 `/control/estop`을 발행한다. 하드웨어·물리 E-stop과 수동 reset은 구현하지 않는다. AMR 로컬 안전이 최종 속도를 통제하며 관제는 OPERATOR·COMMUNICATION·TOKEN·OBSTACLE·KEEPOUT_FAILURE·SYSTEM_FAULT 원인을 통합한다. 활성화는 즉시이고 모든 활성 원인이 제거된 상태가 3초 연속 유지된 경우에만 해제할 수 있다.

heartbeat는 `patrol_interfaces/msg/ControlHeartbeat`로 5 Hz 발행하고 1초 미수신을 timeout으로 한다. 메시지에는 `header`, `control_session_id`, `sequence`를 포함하고 QoS는 BEST_EFFORT·VOLATILE·KEEP_LAST(3)이다. timeout 시 AMR은 로컬 안전 정지하며 heartbeat 복구만으로 자동 재출발하지 않는다.

E-stop 대상은 `robot1`, `robot6`, `all`이다. 관제는 대상별 활성 원인 집합을 유지하고 EStop 메시지에는 합의할 우선순위 기준의 대표 원인 하나만 발행한다. 전체 원인 집합은 `uint8[] active_reasons` 의미의 디버깅·표시용 관제 판단으로 제공하며 전달 타입·토픽은 TBD-IF-011, 원인 우선순위와 활성·해제 조건은 AMR 협의 전까지 TBD-IF-004다.

시스템 모니터 UI의 정지 요청은 관제 소유 API를 통해 OPERATOR 원인을 즉시 활성화하고, UI 해제 요청은 OPERATOR 원인을 해제 대기 상태로 바꾼다. UI는 E-stop을 직접 발행하거나 해제를 판정하지 않는다. 이 UI는 시스템 모니터의 기존 읽기 전용 경계 변경이므로 요청서 합의 전에는 구현 확정으로 간주하지 않는다. 해제 후에도 AMR은 정지 상태를 유지하고 새 token과 별도 MissionCommand를 모두 받은 뒤 이동한다. E-stop 해제 부저는 사용하지 않는다.

화재 Detection이 확정되면 신규 순찰 구간을 추가하지 않고 현재 mission ID로 순찰·복귀·도킹까지 완료한다. 해당 mission의 기존 Drive Token은 도킹 완료 또는 실패까지 갱신·유지하고 종료 시 회수한다. 이후 다른 로봇에 새로운 Drive Token을 발급하지 않고 전체 순찰을 중단한다. 기존 token이 만료되거나 E-stop이 발생하면 화재 mission도 즉시 안전 정지하며 만료된 token을 새 token ID로 재발급해 자동 복구하지 않는다.

화재 부저는 확정 event에서 ON하고 DOCKED와 CHARGING이 2초 연속 유지되면 OFF한다. 도킹 timeout 또는 실패가 확정되면 부저를 OFF하고 `FIRE_DOCKING_FAILED` 관제 경고를 활성화한다. 단, 다른 활성 화재 event가 남아 있으면 부저를 끄지 않는다. 부저 OFF 전달 실패도 관제 경고로 남긴다. 기존 mission의 정상 완료 여부와 별개로 FIRE_DETECTED=702는 reason code로만 사용하고 PatrolReport 결과 enum이나 Detection event_type 수치로 혼용하지 않는다.

## 7. 기록과 검증

관제는 STALE·UNREPORTED, CCTV timeout 경고, 순찰·교대 진행 상태와 운영상 증적 누락·지연 경고를 판단하고 시스템 모니터에 토픽으로 제공한다. 판단 결과와 로그의 토픽명·필드·발행 정책·초기 상태·재연결 계약은 [TBD-IF-011](interfaces.md#tbd)에서 정의한다. 기존 판단 기준은 유지하고 미정 기준은 관련 TBD에서 합의한다. 모니터가 자체 판단을 대신 수행한다고 가정하지 않는다.

명령 ID, holder 변화, Keepout 적용·rollback, STALE·복구, E-stop 원인·해제, 교대 결과를 모니터링과 연결한다. 저장 실패 시 제어 동작 영향은 TBD-MON-002에서 결정한다.

검증은 [integration.md](integration.md)의 token·상태·Keepout·교대·E-stop 시험을 따른다. Dashboard는 현재 읽기 전용이다. E-stop 정지·해제 요청 UI 추가는 System monitor 팀과 PM 검토가 필요한 경계 변경이며, UI는 합의 후에도 관제 소유 요청 API만 호출하고 판단·직접 발행을 수행하지 않는다. 구체 API는 TBD-CTRL-004다.

## 8. 결정 기록과 공동 반영 대기

AMR 적용 검토와 robot1·robot6 반영 상태는 [관제 수정 요청서](change_requests/CR-관제_09-07_15-55_AMR_명령_토큰_상태_안전_계약_변경.md)로 추적한다.

- 2026-09-07 사용자 결정: command·mission·token·report·event·증적·운영 이벤트 ID는 2.1절의 사람이 식별 가능한 세션·sequence 기반 문자열을 사용한다. 근거: 개발 프로세스 학습 범위에서 로그 추적성과 이해 가능성을 우선한다. 영향: 관제·AMR·비전·시스템 모니터의 공용 메시지와 중복 처리. interfaces.md에 공용 계약을 반영했으며 상대 단위 기능 문서는 수정 요청과 검토 후 반영한다.
- 2026-09-07 사용자 결정: MissionCommand 확인은 CommandCheck의 ACCEPTED·EXECUTING·REJECTED로 구분하고 최종 결과는 PatrolReport로 반환한다. Check timeout은 5초, 동일 ID·payload 최대 재전송은 2회다. START/RESUME과 STOP/CANCEL의 의미, command 중재 우선순위, ID 보존은 2.2절을 따른다. 영향: 관제·AMR, TBD-CTRL-001·TBD-IF-001·003.
- 2026-09-07 사용자 결정: Drive Token은 control session, grant ID와 발행 sequence를 구분하고 회수 대상 holder를 명시한다. 교대는 실제 정지 확인 후 신규 token을 발급하며 정지 기준은 2.3절을 따른다. 영향: 관제·AMR, TBD-IF-002·TBD-INT-001·TBD-AMR-006.
- 2026-09-07 사용자 결정: Keepout·안전구역 세부 설계는 AMR 팀이 먼저 제시하고 관제 담당자가 확인한다. 검토 전에는 미정 계약을 구현값으로 추측하지 않는다. 영향: 관제·AMR, TBD-CTRL-002·TBD-INT-003.
- 2026-09-07 사용자 결정: LOW는 새 mission을 시작하지 않고 현재 mission의 순찰·복귀·도킹까지 완료하며, CRITICAL은 즉시 복귀 또는 도킹 판단으로 전환한다. 영향: 관제·AMR, TBD-CTRL-003·TBD-AMR-003·005.
- 2026-09-07 사용자 결정: 화재 확정 후 현재 mission의 순찰·복귀·도킹까지 완료하고 기존 token을 그 종료까지 유지한다. 도킹 후 다른 로봇에 새 token을 발급하지 않는다. DOCKED와 CHARGING 2초 연속을 도킹 완료와 화재 부저 OFF 조건으로 하며, 도킹 실패 시 다른 활성 화재가 없는 경우 부저를 끄고 관제 경고를 발생시킨다. 영향: 관제·AMR, TBD-INT-004·TBD-AMR-004 및 Q-09·Q-12. 공용 기준 반영 완료, AMR 검토 대기.
- 2026-09-08 사용자 결정: CommandCheck 0~3, 정상 ACCEPTED→EXECUTING과 제한된 ACCEPTED 누락 복구, 명령별 mission·target, `parameters_json` 제거, reason code 203~206, RobotStatus safety_state 0~5를 2.2절·3절과 interfaces.md에 반영한다. 영향: 관제·AMR·시스템 모니터. 실제 `.msg`와 상대 단위 코드는 새 요청서 검토·승인 후 반영한다.
- 2026-09-08 사용자 결정: Heartbeat 타입·필드·QoS, UI E-stop reason 0~6, 전체 대상 `all`, 대표 원인 발행, 3초 해제 조건을 확정하고 하드웨어 E-stop·manual reset은 제외한다. UI 요청 경로와 reason 우선순위는 상대 팀 검토 사항이다. 영향: 관제·AMR·시스템 모니터.
- 2026-09-08 사용자 결정: Ctrl+C/SIGINT 정상 종료는 `CONTROL_SHUTDOWN` 운영 이벤트로 분류하고, 재기동 후 새 session·상태 게이트·새 token·별도 command 순서를 지킨다. 영향: 관제·AMR·시스템 모니터, TBD-IF-011.

공용 계약과 시험 기준은 interfaces.md·integration.md·scenarios.md에 반영했다. 상대 단위 기능 문서는 직접 수정하지 않고 아래 계약을 수정 요청 절차로 전달한다.

| 상대 단위 반영 대상 | 필요한 변경 |
|---|---|
| TBD-IF-001 | CommandCheck enum·전이, 명령별 target, `parameters_json` 제거, reason 203~206 |
| TBD-IF-002 | control session, token ID, message sequence, 대상 holder를 유지한 회수 |
| TBD-IF-003 | RobotStatus safety_state·PatrolReport 수락과 command/mission/report ID 관계 |
| TBD-IF-004 | ControlHeartbeat, E-stop reason·대상·대표 원인·해제 규칙 |
| TBD-IF-005·006·007·011 | 공통 ID 형식과 source session·sequence 반영 |
| TBD-INT-001 | 실제 정지 확인 후 신규 holder token 발급 |
| TBD-INT-004 | 화재 mission 완료·도킹·token 중단·부저 정책 |
| Q-09·Q-12 | 공용 기준은 2초로 변경 완료, AMR 기능·시험 반영 필요 |

## TBD

| ID | 미정 사항 | 영향 단위 | 상태 |
|---|---|---|---|
| TBD-CTRL-001 | 명령 우선순위·동시 처리·STOP/CANCEL/RESUME 정책·재전송 | 관제·AMR | 공용 문서 반영 완료, ACCEPTED 누락 후 재전송 중단 여부·AMR 반영 검토 대기 |
| TBD-CTRL-002 | 안전구역 계산자·지도/동선 공급, rollback 확인·timeout·재시도 | 관제·AMR | AMR 제시안 대기 |
| TBD-CTRL-003 | 재개/교대 배터리 적격 조건·거리 점수·동점, 정상 연속 수신 정의 | 관제·AMR | 공용 문서 반영 완료, 점수 fixture·AMR 검토 대기 |
| TBD-CTRL-004 | System monitor UI의 OPERATOR 정지·해제 요청 API와 관제 응답 | 관제·System monitor | UI 경계 변경 검토 요청 중 |

공용 계약 TBD는 interfaces.md를 참조한다. 결정 시 요청서와 상대 단위 반영 상태를 연결한다.
