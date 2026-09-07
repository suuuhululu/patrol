# AMR 개발 워크스페이스 인수인계

작성일: 2026-09-07 · 작업 브랜치: `feat/amr-safety-status`

## 1. 작업 범위와 현재 상태

조정묵 담당 범위는 공용 메시지 기반과 AMR Python 파일 7개, ROS 노드 3개다.

| 단계 | 대상 | 상태 |
|---|---|---|
| 1 | `patrol_interfaces`: MissionCommand, DriveToken, RobotStatus, PatrolReport, EStop 및 빌드 설정 | 구현·빌드·사용자 interface show 확인 완료 |
| 2 | `battery_monitor.py`: 배터리 분류·3초 상태 전이·ROS 구독/내부 상태 발행 | 구현·단위시험·사용자 ROS 토픽 시험 통과 |
| 3 | `drive_token_guard.py`: DriveToken 수락 규칙·Q-01 로컬 lease | 구현·단위시험 완료, 사용자 검토 대기 |
| 4 | `estop_guard.py`: EStop 반영·sequence 역순 폐기 | 구현·단위시험 완료, 사용자 검토 대기 |
| 5 | `motion_guard.py` | 미착수 |
| 6 | `local_safety_supervisor.py` ROS 노드 | 미착수 |
| 7 | `robot_status_state.py` | 미착수 |
| 8 | `status_reporter.py` ROS 노드 | 미착수 |
| 9 | `patrol_amr` 패키지 설정·실행 등록·통합 | 미착수 |
| 10 | 통합시험 | 미착수 |

최종 ROS 노드는 `battery_monitor`, `local_safety_supervisor`, `status_reporter` 세 개다. guard와 state 파일은 해당 노드가 사용하는 일반 Python 모듈이다. 한 단계씩 구현하고 사용자 시험 통과 확인 전에는 다음 단계로 넘어가지 않는다.

## 2. 새 컴퓨터 준비

추가 패키지를 설치하지 않는다는 작업 원칙에 따라, 새 컴퓨터에 Ubuntu 24.04, ROS 2 Jazzy, Python 3.12 계열, Git과 colcon이 이미 있어야 한다. 다음 명령으로 확인한다.

```bash
ls /opt/ros/jazzy/setup.bash
python3 --version
git --version
colcon --help
```

어느 하나라도 없으면 임의로 설치하지 말고 기존 프로젝트 환경 담당자에게 확인한다.

## 3. GitHub에서 작업 가져오기

이 브랜치가 원격에 push된 뒤 새 컴퓨터에서 실행한다.

```bash
cd ~
git clone https://github.com/suuuhululu/patrol.git
cd patrol
git fetch origin
git switch --track origin/feat/amr-safety-status
git status
git branch --show-current
```

예상 결과는 깨끗한 작업 트리와 현재 브랜치 `feat/amr-safety-status`다. 브랜치가 아직 원격에 없으면 이전 컴퓨터에서 push가 끝나지 않은 것이므로 파일을 다시 만들지 않는다.

매 터미널에서 ROS 환경을 먼저 적용한다.

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
```

## 4. 1단계 재검증

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
colcon build --packages-select patrol_interfaces
source install/local_setup.bash
ros2 pkg prefix patrol_interfaces

for name in MissionCommand DriveToken RobotStatus PatrolReport EStop
do
  echo "===== $name ====="
  ros2 interface show patrol_interfaces/msg/$name
done
```

예상 결과는 `1 package finished`, `~/patrol/install/patrol_interfaces` 경로, 메시지 5종의 필드 출력이다. `Unknown package`가 나오면 현재 경로·브랜치·빌드 결과와 `source install/local_setup.bash` 실행 여부를 확인한다.

메시지 원본 주석에는 이전 워크스페이스의 제안과 과거 요청서 표현이 남아 있다. 현재 계약과 TBD 상태는 `src/patrol_interfaces/README.md`와 `docs/interfaces.md`를 기준으로 해석한다.

## 5. 2단계 구현 내용

`src/patrol_amr/patrol_amr/battery_monitor.py`는 상대 토픽 `battery_state`를 `sensor_msgs/msg/BatteryState`로 구독한다.

- `CHARGING`·`FULL`: 충전 방향
- `DISCHARGING`: 방전 방향
- 다른 status, `present=false`, NaN, SOC 범위 밖: 즉시 UNKNOWN
- 3초 미수신: 즉시 UNKNOWN
- 방전 SOC 10% 미만: CRITICAL 즉시
- 그 밖의 유효 상태: 같은 조건을 3초 연속 관측한 뒤 전환
- 결과: 상대 토픽 `battery_status`의 `std_msgs/msg/UInt8`

상태 숫자는 UNKNOWN=0, CRITICAL=1, LOW=2, NORMAL=3, CHARGING=4, PATROL_READY=5, FULL=6이다. `battery_status`는 AMR 내부 연결이며 공용 BatteryEvent 계약을 추가한 것이 아니다.

단위시험:

```bash
cd ~/patrol
python3 -m unittest discover -s tests -p test_battery_monitor.py -v
```

예상 결과는 `Ran 7 tests`와 `OK`다.

## 6. 2단계 사용자 ROS 토픽 시험

터미널 1:

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
python3 src/patrol_amr/patrol_amr/battery_monitor.py
```

초기 예상 로그는 `battery status: UNKNOWN`이다.

터미널 2는 발행보다 **먼저** 띄워 계속 구독한다.

```bash
source /opt/ros/jazzy/setup.bash
ros2 topic echo /battery_status --qos-durability transient_local
```

터미널 3에서 발행한다.

```bash
source /opt/ros/jazzy/setup.bash
ros2 topic pub -r 10 --times 35 /battery_state sensor_msgs/msg/BatteryState \
"{percentage: 0.15, power_supply_status: 2, present: true}"
```

3초 연속 입력 후 예상 값은 LOW에 해당하는 `data: 2`다. 발행이 끝나고 3초 이상 지나면 UNKNOWN인 `data: 0`이 이어서 찍힌다. 터미널 1·2는 `Ctrl+C`로 종료한다.

`--once`로 그때그때 조회하지 않는다. 새 프로세스가 매번 discovery를 하는 동안 노드가 이미 다음 상태로 넘어가, LOW를 기다리는 자리에서 마지막 latch 값인 `data: 0`을 받아 거짓 실패로 보인다. 2026-09-07 이 현상을 실제로 관측했다.

`ros2 topic echo`가 `does not appear to be published yet`으로 끝나면 노드가 아니라 CLI 조회 경로를 먼저 의심한다. 타입 조회는 `ros2 daemon`을 거치므로, 데몬이 켜질 때와 다른 discovery 설정에서 실행하면 노드를 못 본다. `--no-daemon`을 붙이면 데몬을 건너뛴다. 이때도 노드 로그 자체는 유효한 증거다. `_publish_if_changed()`가 발행과 로그를 같은 블록에서 함께 실행하므로 **로그 한 줄이 곧 토픽에 나간 값 하나**다.

확인 항목은 3초 유지 전이(SOC 0.15 → LOW), 미수신 3초 복귀(UNKNOWN), CRITICAL 즉시 전이(SOC 0.05), SOC 경계(0.19/0.20), 충전 방향(status 1, SOC 0.85 → FULL)이다. CRITICAL은 1초만 발행해도 전이해야 한다. 3초 유지 규칙을 탄다면 전이할 수 없으므로 즉시성의 증거가 된다.

2026-09-07 사용자가 CRITICAL 즉시 전이를 확인하여 2단계를 통과 처리했다. 나머지 항목은 같은 코드로 개발 워크스페이스에서 확인했으며, robot1·robot6 실기와 실제 배터리 드라이버 연동은 미실행이다.

## 6.1 3단계 구현 내용

`src/patrol_amr/patrol_amr/drive_token_guard.py`는 ROS 노드가 아니라 6단계 `local_safety_supervisor`가 사용하는 일반 Python 모듈이다. `/control/drive_token` 관측을 받아 주행 권한만 판정하고 속도를 발행하지 않는다.

- `observe(token, holder_robot_id, lease_seconds, sequence, now)`가 수락·폐기 사유를 `TokenVerdict`로 반환한다. 폐기 사유는 `OTHER_HOLDER`, `REVOKED`, `STALE_SEQUENCE`, `INVALID_LEASE`다.
- `authority(now)`가 `GRANTED`·`MISSING`·`EXPIRED`를 반환한다. 각각 600 DRIVE_TOKEN_MISSING, 601 DRIVE_TOKEN_EXPIRED에 대응한다.
- 경과 판정은 호출자가 넘기는 로컬 monotonic 초만 사용한다. 폐기된 메시지는 lease를 연장하지 않는다.

단위시험:

```bash
cd ~/patrol
python3 -m unittest discover -s tests -p test_drive_token_guard.py -v
```

예상 결과는 `Ran 22 tests`와 `OK`다. 두 단계를 함께 돌리려면 `-p "test_*.py"`를 쓴다. 예상 결과는 `Ran 29 tests`와 `OK`다.

이 모듈은 ROS 토픽 시험 대상이 아니다. 실제 `/control/drive_token` 구독과 정지 출력은 6단계에서 붙인다. 상세 설계와 TBD-IF-002로 남긴 부분은 [amr.md 3.1절](../amr.md#31-drive_token_guardpy--구현-대조-완료)에 있다.

## 6.2 4단계 구현 내용

`src/patrol_amr/patrol_amr/estop_guard.py`는 3단계와 같이 일반 Python 모듈이며 6단계 `local_safety_supervisor`가 사용한다. `/control/estop` 관측을 반영만 하고 속도를 발행하지 않는다.

- `observe(active, cause, physical, source, sequence, activated_at_seconds, release_condition_started_at_seconds)`가 `ACCEPTED`/`STALE_SEQUENCE`를 반환한다. `active`는 즉시 반영하고, 로컬 타이머·heartbeat timeout은 두지 않는다(TBD-IF-004).
- 관측 전 기본 상태는 정지다. `DriveTokenGuard`와 달리 `robot_id`가 없다 — EStop.msg에 holder 필드가 없어 공통 토픽 하나를 모든 로봇이 동일하게 반영한다.
- 물리 E-stop의 로컬 방어적 latch와 `E_STOP_RELEASE_CONDITION_STARTED`/`_CANCELED` 판정은 미구현이다. 계약에 근거가 없어 추측하지 않았다. 상세는 [amr.md 3.2절](../amr.md#32-estop_guardpy--구현-대조-완료)에 있다.

단위시험:

```bash
cd ~/patrol
python3 -m unittest discover -s tests -p test_estop_guard.py -v
```

예상 결과는 `Ran 17 tests`와 `OK`다. 지금까지 세 파일을 함께 돌리려면 `-p "test_*.py"`를 쓴다. 예상 결과는 `Ran 49 tests`와 `OK`다.

이 모듈도 ROS 토픽 시험 대상이 아니다. 실제 `/control/estop` 구독과 정지 출력은 6단계에서 붙인다.

## 7. 결정·미완료 사항

TBD-AMR-003은 사용자의 권장안 승인으로 AMR 코드에 반영했으며 `docs/change_requests/CR-AMR_09-07_14-01_배터리_입력_정책.md`에 관제 검토를 요청했다. 실제 robot1·robot6 배터리 드라이버, 관제 연계, 도킹·교대 시험은 아직 수행하지 않았다.

현재 `patrol_amr`에는 `setup.py`, `package.xml`, 실행 entry point가 없다. 이는 9단계 패키지 통합 범위다. 2단계 시험은 Python 파일을 직접 실행한다. 이전 `final_turtlebot_ws`의 다른 실행 코드나 build/install/log 결과를 새 저장소로 복사하지 않는다.

작업 재개 전에 루트 `AGENTS.md`, `docs/architecture.md`, `docs/interfaces.md`, `docs/amr.md`를 확인한다. 기존 플로우차트는 설계 초안이며 확정 계약으로 사용하지 않는다. 다른 담당자의 변경과 미확정 TBD를 보존한다.
