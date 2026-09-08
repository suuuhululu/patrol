# AMR 업무표 100% 완료 계획

기준일: 2026-09-08 · 기준 자료: 사용자가 제공한 AMR 업무표 이미지

## 1. 완료 판정 원칙

이 문서는 기존의 구현 단계 숫자가 아니라 업무표의 각 행을 최종 완료 단위로 삼는다. 중간 모듈·단위시험·문서만 끝난 상태는 해당 행의 구현 증거일 뿐 100%가 아니다.

한 행은 다음 조건을 모두 만족할 때만 100%로 처리한다.

1. 표에 적힌 기능이 실제 실행 경로에 연결되어 있다.
2. 관련 단위시험과 로컬 자동시험이 통과한다.
3. 표에 요구된 ROS 토픽·통합·실기시험이 통과한다.
4. 관련 TBD가 결정됐거나, 그 기능이 TBD 값을 사용하지 않는다는 근거가 문서에 있다.
5. 타 담당 코드와의 병합·계약 대조가 끝났다.
6. 코드별 Mermaid flowchart, 시험 명령, 기대 결과, 실제 결과가 최신 코드와 일치한다.

퍼센트는 작업량 추정치가 아니라 사용자 업무표의 기준값으로 보존한다. 임의로 10%·20%씩 올리지 않는다. 각 행의 100% gate가 모두 닫혔을 때 `완료 / 100%`로 한 번에 갱신한다.

현재 작업은 로컬 `codex/amr-row-completion` 브랜치에서만 진행한다. 사용자가 다시 요청하기 전에는 commit·push·fetch·merge 등 Git 작업을 하지 않고 `main`을 변경하지 않는다.

## 2. 기능 구현 단계

각 단계는 **기능 구현 → 단위·로컬 자동시험**을 한 묶음으로 수행한다. 실제 장비·다중 PC가 필요한 시험은 28~29단계에서 다시 종단 검증한다.

| 단계 | 목표 행 | 구현 종료 조건 |
|---|---|---|
| 19 | 공통 선행조건 | 최신 `main` 기준 통합 브랜치 정리, 타 담당 코드 확보, 관련 TBD별 결정/요청서/영향 파일 확정 |
| 20 | AMR-04·05·06·07 | token·command 저장/중복 방지·RobotStatus 27필드·PatrolReport publisher/영속 outbox를 실제 mission 입력에 연결 |
| 21 | AMR-08·09·10·16 | map/TF·Keepout·safe-zone·공통 Nav2 경로를 robot1/robot6 namespace로 연결 |
| 22 | AMR-12·13 | 배터리 회귀를 유지하며 도킹 진입·timeout·성공 3초 판정·실패 보고 연결 |
| 23 | AMR-11·20 | 물리 E-stop local latch와 승인된 수동 reset, heartbeat watchdog을 최종 정지 경로에 연결 |
| 24 | AMR-14·15 | OAK-D detection·증적·화재 부저와 robot6 LiDAR 위치 검증 연결 |
| 25 | AMR-17 | START_PATROL부터 완료·PatrolReport까지 정상 순찰 전체 경로 연결 |
| 26 | AMR-18·19 | 안전 중단·복구·RESUME_PATROL·재개 지점·token 반납 경로 연결 |
| 27 | AMR-03~20 기능 감사 | 18개 기능 행 각각의 100% gate, flowchart, 단위·로컬 자동시험 증거 대조 |

## 3. 업무 행별 100% gate

아래 `기준 %`는 사용자 업무표 이미지의 값이다. 이후 구현이 추가됐더라도 최종 gate가 남아 있으면 100%로 선언하지 않는다.

| 업무 행 | 기준 % | 100%가 되기 위해 남은 종단 조건 | 구현 단계 |
|---|---:|---|---:|
| AMR-03 공용 메시지 패키지 구현·검증 | 100 | 현재 계약 6종 빌드·`interface show` 회귀 유지 | 27 |
| AMR-04 drive_token 로컬 검증·만료 | 90 | 실제 ROS 연동에서 정상 token, 역순·만료·회수, 최종 주행 정지 확인 | 20 |
| AMR-05 명령 수신·검증·중복 제거 | 80 | `command_store` 병합/구현, ACK·중복·충돌·24시간/1,000개 보존, 재시작 영속 시험 | 20 |
| AMR-06 RobotStatus 상태 모델·발행 | 60 | mission/docking/safety/waypoint/scan/reason 포함 27필드 실제 입력 연결과 상태 전이·2/10 Hz ROS 시험 | 20 |
| AMR-07 status_reporter·PatrolReport | 10 | terminal mission 입력, ROS publisher, 성공·실패·취소, UNREPORTED 경계, 영속 재전송·중복 제거 시험 | 20 |
| AMR-08 맵·도크·마스크 좌표 정합 | 20 | P1~P7·도크 pose·Keepout mask의 map frame 수치 확정, robot1/robot6 map↔TF 실측 | 21 |
| AMR-09 KeepoutFilter 구성 | 0 | mask server·costmap filter info server·enabled/read-back·Q-07 대기·IT-08 | 21 |
| AMR-10 안전구역 이동 실행 | 0 | MOVE_TO_SAFE_ZONE 후보 이동·도착 보고, 무후보 정지와 SAFE_ZONE_NOT_FOUND 보고 | 21 |
| AMR-11 estop_guard 로컬 반영·정지 latch | 40 | 실제 물리 버튼, 관제 E-stop, local latch, 승인된 수동 reset/권한/ACK를 최종 속도에서 실기 확인 | 23 |
| AMR-12 배터리 상태 enum 보고 | 100 | 기존 7값·경계·3초 유지·CRITICAL 즉시 시험 회귀 유지 | 22 |
| AMR-13 도킹 실행·성공 판정 | 50 | DOCKING 진입, 60초 내 접점/완료 센서 3초 연속, timeout/실패 report, 새 mission 중복 없음 | 22 |
| AMR-14 로컬 Detection·증적·화재 부저 | 0 | yaw 정렬·1초 연속 탐지·중복 제거·증적·ON/OFF·T-14 | 24 |
| AMR-15 AMR2 LiDAR 위치 검증 | 60 | robot6 대상·연산 위치·요청/결과·timeout 계약과 Q-06/Q-15 실기 | 24 |
| AMR-16 공통 Nav2 연결·재시도 | 70 | goal 발행·feedback·실패 3회 재시도·waypoint skip·최종 goal·안전 공통 경로, 4개 경로 실기 | 21 |
| AMR-17 정상 순찰 시나리오 실행 | 60 | START_PATROL→undock→P1~P7→scan→완료 처리와 W-01·중복·지점 skip·최종 PatrolReport | 25 |
| AMR-18 안전 중단·복구 대응 | 60 | goal/spin 취소, 상태 정지, 복구 후 관제 명령 대기, 통신 복구만으로 자동 출발하지 않음 | 26 |
| AMR-19 순찰 재개 시나리오 | 30 | RESUME_PATROL 재개 지점, 추가 token 미발급 시 정지, 30초 초과 token 반납 | 26 |
| AMR-20 heartbeat watchdog | 0 | heartbeat 계약 확정, 1.0초 초과 안전 정지, timer·주기·timeout 시험 | 23 |

## 4. 정식 테스트·통합 단계

기능 행이 구현됐어도 아래 시험 행이 따로 100%가 되지 않으면 전체 완료가 아니다.

| 단계 | 목표 행 | 기준 % | 100% 종료 조건 |
|---|---|---:|---|
| 28 | T-01 통신·명령·상태 테스트 | 40 | robot1/robot6 discovery·식별, 중복 명령, token 역순·만료, RobotStatus·PatrolReport 단절/복구, 실주행, lease 연장 없음 |
| 28 | T-02 대피·Keepout 테스트 | 20 | permit false/true, Keepout ON/OFF, 대피·재개, 안전구역 없음, rollback 실패 수립 |
| 28 | T-03 로컬 안전·E-stop 테스트 | 30 | 물리·비물리 E-stop, token 만료, Nav2/yaw 동시 후보, 충돌 속도, 최종 속도 발행자 1개와 안전 차단 우회 없음 |
| 28 | T-04 배터리·도킹 테스트 | 40 | SOC 경계·유지, 도킹 성공·접점 단절·timeout, 두 로봇 교대 시험 |
| 28 | T-05 Detection·증적·화재 테스트 | 0 | yaw 정렬·연속 탐지·중복 event·증적 순서 변경·전송/DB 실패·화재 부저 시험 |
| 29 | I-01 AMR 공통 모듈 결합 | 30 | guard·supervisor·battery·monitor·robot_status_state·status_reporter 및 추가 모듈 결합, 정상·실패 경로 단위시험 PASS |
| 29 | I-02 patrol_amr 패키지·ROS 노드 통합 | 40 | setup/package/entry point/launch, 전체 노드 빌드·실행·토픽 연결 확인 |
| 29 | I-03 AMR 로컬 통합시험 | 30 | token·만료·회수·E-stop·Nav2/yaw·battery·RobotStatus·PatrolReport 전체 경로, robot1/robot6 별도 PASS |
| 30 | 전체 100% 감사 | - | AMR 18행 + T 5행 + I 3행 모두 `완료 / 100%`, 미실행 시험·OPEN blocker 0건 |

## 5. 현재 체크포인트와 다음 행동

- 2026-09-08 20단계 확정 부분: 신규 명령 1회 dispatch, 현재 ACK 재응답, 충돌 거절, 완료 report 재전달 판정, 재연결 epoch report replay를 구현했다. 전체 자동시험은 `Ran 231 tests`/`OK`다.
- 21단계 첫 구현으로 실제 좌표에 비의존적인 Q-08 안전구역 후보 판정·선택·`SAFE_ZONE_NOT_FOUND` 결정을 추가했다. 실제 map·mask·P1~P7·도크·안전구역 좌표는 저장소에 없어 AMR-08·09·10·16은 아직 100%가 아니다.
- 사용자가 제공한 `final_project_map`(126×90, 0.05 m/px, origin `[-5.801,-3.430,0]`)과 WP1~WP7을 패키지에 추가했다. 빨간 기본 Keepout 2개와 노란 중앙통로 Keepout 1개를 별도 마스크로 생성했다. 도크 pose·안전구역 후보 좌표, 실제 Nav2 filter 활성 정책·parameter·통합이 남아 AMR-08·09·10·16은 아직 100%가 아니다.
- 빨간 기본 mask는 상시, 노란 중앙통로 mask는 관제가 `/vision/cctv/patrol_allowed=false`를 받았을 때 활성하는 정책으로 자산에 분리했다. 자동시험 `Ran 250 tests`/`OK`, 두 패키지 빌드 성공이다.
- 21단계 Nav2 이중 Keepout 연결로 기존 TurtleBot4 parameter에 적용하는 overlay, robot1·robot6 namespace launch, base/center mask server와 filter info server lifecycle 구성을 추가했다. 기본 filter는 항상 ON, 중앙통로 filter만 관제 transaction 대상으로 분리했다. 전체 자동시험 `Ran 255 tests`/`OK`, 두 패키지 빌드와 launch 인자 검증이 성공했다. 관제 적용·read-back·rollback과 양쪽 로봇 실기는 [이중 Keepout parameter 요청서](../change_requests/CR-AMR_09-08_13-02_이중_Keepout_parameter_계약.md) 합의 후 남는다.
- 병합된 실제 production 경로 `mission_supervisor → PatrolScenario → NavigationAdapter → Nav2GoalRunner`에 AMR-16 정책을 연결했다. 일반 Nav2 실패·거절은 최초 1회 뒤 최대 3회 재시도하고, 중간 W1~W6의 네 번째 실패는 checkpoint를 넘겨 다음 WP로 진행하며 마지막 W7 실패는 종료한다. 안전 권한 상실·취소는 재시도하지 않는다. robot1·robot6 실기 전에는 AMR-16을 100%로 표시하지 않는다.
- 종단 ROS 연결을 막는 5개 공유 계약은 [AMR 수정 요청서](../change_requests/CR-AMR_09-08_11-48_명령_상태_보고_종단_계약.md)로 분리했다. 미정 숫자·payload·상태 전이는 임의로 확정하지 않았다.
- 다음 기능은 사용자의 `진행` 확인 후에만 시작한다.
- AMR-03과 AMR-12만 사용자 표에서 이미 100%다.
- 18단계 `patrol_report.py`는 AMR-07의 구성·동일 ID 재사용과 전체 wire 필드 변환·발행/QoS helper까지 구현했다. mission 입력·영속 outbox trigger가 없으므로 AMR-07은 아직 100%가 아니다.
- 20단계 AMR-05의 첫 구현으로 `command_store.py`에 재시작 영속 중복 제거, 상태·완료 report 보존, Q-14 retention을 추가했다. public CommandCheck 숫자와 mission ROS adapter가 없어 AMR-05는 아직 100%가 아니다.
- `command_store`와 `patrol_report` 사이에 canonical report JSON 영속·재시작 복원을 연결했다. command/robot ID 불일치도 차단한다. ROS mission adapter와 재전송 trigger가 남아 있어 AMR-05·07은 아직 100%가 아니다.
- AMR-06의 active command/mission ID, waypoint, scan, reason code/detail을 상태 모델에 원자 저장하고 RobotStatus wire 필드까지 매핑했다. 실제 mission adapter 입력이 없어 AMR-06은 아직 100%가 아니다.
- 23단계 AMR-20의 확정 부분으로 `heartbeat_guard.py`에 session·sequence와 1초 초과 timeout을 추가했다. wire 메시지 타입과 최종 안전 ROS 배선이 없어 AMR-20은 아직 100%가 아니다.
- 현재 로컬 작업에는 `mission_supervisor`, 실제 Nav2·도킹 adapter, `command_store.py`, robot1·robot6 hardware launch가 있다. 병합 충돌은 양쪽 자산·의존성을 모두 보존해 정리했다.
- 현재는 21단계다. AMR-16 production 연결은 구현됐고, [실제 robot1 시험](amr16-robot-test.md)의 재시도·skip·안전 취소·최종 goal PASS 전까지 70%로 유지한다. AMR-08·09·10은 map/TF 실측·관제 transaction·안전구역 입력이 별도로 남는다.
- AMR-16 production 연결 자동검증은 전체 단위시험 `Ran 352 tests` / `OK`, `patrol_interfaces`·`patrol_amr` symlink 빌드 성공이다. 이는 실기 PASS를 대신하지 않는다.
- 20단계 AMR-05·06의 남은 조각이던 **mission ROS adapter** 를 `command_gateway.py` 로 구현했다. `mission_ingress.py` 가 docstring 에서 예고한 "future ROS mission node" 다. entry point 4번째 노드이며 `mission_command` 를 구독해 `command_check` 를 발행하고, SQLite 저장소는 `~/.local/state/patrol_amr/<robot>/` 에 두어 재빌드가 실행 이력을 지우지 않는다.
- 내부 신호 3개는 뜻을 하나씩만 갖는다. `command_dispatch`(1회 실행), `active_command`(현재 명령 정체), `report_replay_request`(보존 report 재전송). **durability 를 일부러 다르게 뒀다** — dispatch·replay 는 VOLATILE 이어야 늦게 붙은 구독자에게 과거 신호가 재전달되어 명령이 두 번 실행되는 일이 없고, active_command 는 상태이므로 TRANSIENT_LOCAL 이어야 늦게 뜬 status_reporter 가 빈 ID 를 내보내지 않는다. 첫 구현에서 이 불일치로 값이 전달되지 않는 것을 실측하고 고쳤다.
- PatrolReport 발행은 이 노드에 넣지 않았다. AMR-07 은 다른 담당의 행이고, 한 report 토픽에 발행자가 둘이면 cmd_vel 단일 발행자 규칙이 막으려는 것과 같은 실패가 된다. 완료 명령 재수신 시에는 `report_replay_request` 로 command_id 만 넘긴다.
- `check_state` 정수 3개와 거절 reason code 2개는 필수 parameter 다. TBD-IF-001 의 열린 항목이라 숫자를 만들지 않았고, 없으면 노드가 시작을 거부한다. `status_reporter` 의 `safety_state` 와 같은 방식이다.
- AMR-06 의 `active_command_id`·`active_mission_id` 를 `status_reporter` 가 `active_command` 구독으로 채우도록 연결했다. 거절된 명령은 현재 명령이 아니므로 반영하지 않는다. **종료 시 값을 비우는 경로는 없다** — 명령이 종료 상태에 도달했음을 저장소에 표시하는 주체가 A1 mission owner 이고 아직 없다. 마지막 수락 명령을 유지하는 것은 이 로봇이 아는 사실이며 TBD-AMR-005 의 전이 규칙을 추측한 것이 아니다.
- 자동 검증(2026-09-08): 전체 단위시험 `Ran 289 tests`, 실패 1건은 `turtlebot4_navigation` 미설치 환경 사유다. 스모크 `AMR_SMOKE_PASS`. 격리 도메인에서 신규 1회 dispatch·중복 무dispatch·ID 충돌 거절과 RobotStatus 의 active ID 반영·거절 시 유지를 확인했다.
- AMR-05·06 은 여전히 100% 가 아니다. AMR-05 는 24시간/1,000개 보존과 재시작 영속 ROS 시험이, AMR-06 은 mission·docking 축 입력과 2/10 Hz ROS 시험이 남는다.
- 진행 중에는 이 문서의 행별 gate를 닫은 증거를 추가한다. 하위 체크만 끝났을 때는 `부분 구현`으로 기록하고 행 상태를 `완료`로 바꾸지 않는다.
