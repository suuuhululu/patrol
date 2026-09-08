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

- AMR-03과 AMR-12만 사용자 표에서 이미 100%다.
- 18단계 `patrol_report.py`는 AMR-07의 구성·동일 ID 재사용과 전체 wire 필드 변환·발행/QoS helper까지 구현했다. mission 입력·영속 outbox trigger가 없으므로 AMR-07은 아직 100%가 아니다.
- 20단계 AMR-05의 첫 구현으로 `command_store.py`에 재시작 영속 중복 제거, 상태·완료 report 보존, Q-14 retention을 추가했다. public CommandCheck 숫자와 mission ROS adapter가 없어 AMR-05는 아직 100%가 아니다.
- 23단계 AMR-20의 확정 부분으로 `heartbeat_guard.py`에 session·sequence와 1초 초과 timeout을 추가했다. wire 메시지 타입과 최종 안전 ROS 배선이 없어 AMR-20은 아직 100%가 아니다.
- 최신 `origin/main`에는 `nav2_client.py`, `mission_supervisor`, `command_store.py`, 관제 통합 launch가 없다.
- 따라서 다음은 19단계다. 타 담당 코드의 실제 위치/병합 일정을 확인하고, 없으면 현재 계약으로 직접 구현 가능한 범위와 반드시 먼저 결정할 TBD를 분리한다.
- 진행 중에는 이 문서의 행별 gate를 닫은 증거를 추가한다. 하위 체크만 끝났을 때는 `부분 구현`으로 기록하고 행 상태를 `완료`로 바꾸지 않는다.
