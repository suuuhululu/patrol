# AMR 개발 워크스페이스 인수인계

작성일: 2026-09-07 · 작업 브랜치: `feat/amr-safety-status`

## 1. 작업 범위와 현재 상태

조정묵 담당 범위는 공용 메시지 기반과 AMR Python 파일 7개, ROS 노드 3개다.

| 단계 | 대상 | 상태 |
|---|---|---|
| 1 | `patrol_interfaces`: MissionCommand, DriveToken, RobotStatus, PatrolReport, EStop 및 빌드 설정 | 구현·빌드·사용자 interface show 확인 완료 |
| 2 | `battery_monitor.py`: 배터리 분류·3초 상태 전이·ROS 구독/내부 상태 발행 | 구현·단위시험 완료, 사용자 ROS 토픽 시험 대기 |
| 3 | `drive_token_guard.py` | 미착수 |
| 4 | `estop_guard.py` | 미착수 |
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

터미널 2:

```bash
source /opt/ros/jazzy/setup.bash
ros2 topic pub -r 10 --times 35 /battery_state sensor_msgs/msg/BatteryState \
"{percentage: 0.15, power_supply_status: 2, present: true}"

ros2 topic echo /battery_status --once --qos-durability transient_local
```

3초 연속 입력 후 예상 값은 LOW에 해당하는 `data: 2`다. 발행이 끝난 뒤 3초 이상 기다리고 마지막 조회 명령을 다시 실행하면 UNKNOWN인 `data: 0`이어야 한다. 터미널 1은 `Ctrl+C`로 종료한다.

결과가 일치하면 2단계 통과를 기록하고 3단계 DriveToken 검증으로 진행한다. 실패하면 2단계 코드만 수정한다.

## 7. 결정·미완료 사항

TBD-AMR-003은 사용자의 권장안 승인으로 AMR 코드에 반영했으며 `docs/change_requests/CR-AMR_09-07_14-01_배터리_입력_정책.md`에 관제 검토를 요청했다. 실제 robot1·robot6 배터리 드라이버, 관제 연계, 도킹·교대 시험은 아직 수행하지 않았다.

현재 `patrol_amr`에는 `setup.py`, `package.xml`, 실행 entry point가 없다. 이는 9단계 패키지 통합 범위다. 2단계 시험은 Python 파일을 직접 실행한다. 이전 `final_turtlebot_ws`의 다른 실행 코드나 build/install/log 결과를 새 저장소로 복사하지 않는다.

작업 재개 전에 루트 `AGENTS.md`, `docs/architecture.md`, `docs/interfaces.md`, `docs/amr.md`를 확인한다. 기존 플로우차트는 설계 초안이며 확정 계약으로 사용하지 않는다. 다른 담당자의 변경과 미확정 TBD를 보존한다.
