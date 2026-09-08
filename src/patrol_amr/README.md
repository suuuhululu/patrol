# patrol_amr

`robot1`과 `robot6`이 함께 사용하는 AMR ROS 2 패키지다. `robot_id` 하나로
ROS namespace와 메시지의 로봇 식별자를 정한다. 현재 구현은 DriveToken과
MissionCommand를 받은 뒤 언독하고 W1~W7을 차례로 이동한 다음 도킹한다.

## 실행 흐름

```mermaid
flowchart LR
    CMD[MissionCommand] --> MS[mission_supervisor]
    TOKEN[DriveToken] --> MS
    TOKEN --> SAFE[local_safety_supervisor]
    ESTOP[EStop] --> SAFE
    MS -->|Undock / NavigateToPose / Dock| NAV2[Nav2 + docking]
    NAV2 -->|cmd_vel_nav| SMOOTH[velocity_smoother]
    SMOOTH -->|cmd_vel_smoothed| COLLISION[collision_monitor]
    COLLISION -->|cmd_vel_safe<br/>TwistStamped| SAFE
    SAFE -->|motion_allowed| MS
    SAFE -->|cmd_vel<br/>Twist| DRIVER[Create 3]
    MS -->|mission_status.json| STATUS[status_reporter]
    MS -->|PatrolReport outbox| STATUS
    STATUS --> ROBOTSTATUS[/robotN/robot_status]
    STATUS --> REPORT[/robotN/patrol_report]
```

DriveToken만으로 임무가 시작되지는 않는다. 아래 조건이 모두 참이어야
START_PATROL을 수락한다.

- map_server, AMCL, Nav2가 active다.
- map frame의 AMCL pose, `/robotN/scan`, `/robotN/odom`을 받았다.
- `motion_enable_token`이 해당 로봇 값과 일치한다.
- DriveToken holder가 해당 로봇이고 1초 lease가 계속 갱신된다.
- E-stop이 해제되어 `motion_allowed=true`다.

실행 중 DriveToken이 만료·회수되거나 E-stop이 활성화되면 미션 Action을
취소한다. `local_safety_supervisor`도 독립적으로 최종 속도를 0으로 만든다.
Nav2 후보의 `header.stamp` age가 Q-17 0.5초를 초과해도 최종 속도는 0이다.

## 코드 분리

- `mission_command_parser.py`, `mission_command_callback.py`: ROS 명령 검증과 큐 제출
- `mission_arbiter.py`, `mission_worker.py`: 단일 임무 수명과 중단 처리
- `mission_controller.py`, `scenarios/`: 명령별 단계 선택과 W1~W7 시나리오
- `navigation_adapter.py`, `nav2_goal_runner.py`, `docking_runner.py`: Action 실행
- `drive_token_callback.py`, `mission_drive_token.py`: 미션 측 token 상태와 취소
- `motion_permission.py`: local safety의 권한 콜백
- `local_safety_supervisor.py`: token·E-stop·후보 신선도와 최종 `cmd_vel`
- `waypoint_repository.py`, `command_store.py`: 좌표 검증과 중복·checkpoint 저장
- `robot_readiness_callbacks.py`, `motion_gate.py`: AMCL·scan·odom 준비 상태
- `mission_state.py`, `mission_status_store.py`, `status_mission_bridge.py`:
  미션 상태의 프로세스 간 전달과 RobotStatus 미션 필드 변환
- `mission_reporter.py`, `patrol_report_outbox.py`,
  `patrol_report_adapter.py`: 종료 결과 검증·영속 큐·ROS 메시지 발행
- `status_reporter.py`: Q-02 RobotStatus와 AMR-07 PatrolReport 발행

파일별 callback·분기·실패 흐름은
[mission_navigation.md](docs/mission_navigation.md)에 있다.

## 빌드

이 컴퓨터에서는 TurtleBot4 관련 의존성이 별도 작업공간에 있으므로 처음
빌드할 때 해당 underlay를 source한다. 다른 컴퓨터도 같은 패키지를 apt로
설치하거나 자체 TurtleBot4 작업공간을 빌드한 뒤 그 경로를 source해야 한다.
절대 경로를 코드에 넣은 것이 아니다.

```bash
cd /home/mu-06/patrol
source /opt/ros/jazzy/setup.bash
source /home/mu-06/turtlebot4_ws/install/setup.bash
source /home/mu-06/rokey_ws/install/setup.bash

colcon build --packages-select patrol_interfaces patrol_amr --symlink-install
source /home/mu-06/patrol/install/setup.bash
```

빌드가 끝난 뒤 새 터미널의 일반 실행에서는 다음 두 줄로 현재 patrol
overlay까지 불러올 수 있다. 의존 작업공간의 위치가 다른 컴퓨터라면 그
컴퓨터에서 위 빌드 절차를 먼저 수행한다.

```bash
source /opt/ros/jazzy/setup.bash
source /home/mu-06/patrol/install/setup.bash
```

## Nav2가 이미 준비된 robot6의 다음 시험

아래 절차는 실제 로봇이 움직이는 현장 시험이다. Localization과 Nav2를
실행 중인 기존 터미널은 그대로 둔다. 같은 `/robot6` localization, Nav2,
mission_supervisor, local_safety_supervisor를 중복 실행하지 않는다.

### 터미널 1: 미션과 로컬 안전 실행 — 계속 켜 둠

```bash
cd /home/mu-06/patrol
source /opt/ros/jazzy/setup.bash
source /home/mu-06/patrol/install/setup.bash

export ROS_DOMAIN_ID=6
unset ROS_LOCALHOST_ONLY

ros2 launch patrol_amr hardware_patrol.launch.py \
  robot_id:=robot6 \
  start_localization:=false \
  start_nav2:=false \
  start_local_safety:=true \
  motion_enable_token:=ENABLE_ROBOT6_MOTION
```

### 터미널 2: 연결 확인 — 명령만 실행하고 종료

```bash
source /opt/ros/jazzy/setup.bash
source /home/mu-06/patrol/install/setup.bash
export ROS_DOMAIN_ID=6
unset ROS_LOCALHOST_ONLY

ros2 topic info /robot6/cmd_vel_safe --verbose
ros2 topic info /robot6/cmd_vel --verbose
ros2 topic info /robot6/mission_command --verbose
ros2 topic info /robot6/robot_status --verbose
ros2 topic info /robot6/patrol_report --verbose
```

기대 결과는 다음과 같다.

- `/robot6/cmd_vel_safe`: `collision_monitor` publisher와
  `local_safety_supervisor` subscription이 각각 있다.
- `/robot6/cmd_vel`: publisher가 `local_safety_supervisor` 하나다.
- `/robot6/mission_command`: `mission_supervisor` subscription이 하나다.
- `/robot6/robot_status`: `status_reporter` publisher가 하나다.
- `/robot6/patrol_report`: `status_reporter` publisher가 하나다.

### 터미널 2: 시험용 E-stop 해제 — 한 번 실행

실제 관제 Safety Arbiter가 `/control/estop`을 발행 중이면 그 관제 입력을
사용한다. 관제가 없는 단일 기능 시험에서만 다음 메시지를 발행한다.

```bash
ros2 topic pub --once \
  --qos-reliability reliable \
  --qos-durability transient_local \
  /control/estop \
  patrol_interfaces/msg/EStop \
  "{target_robot_id: 'robot6', active: false, reason: 0, sequence: 1}"
```

### 터미널 3: 시험용 DriveToken 갱신 — 계속 켜 둠

```bash
cd /home/mu-06/patrol
source /opt/ros/jazzy/setup.bash
source /home/mu-06/patrol/install/setup.bash
export ROS_DOMAIN_ID=6
unset ROS_LOCALHOST_ONLY

TOKEN_STAMP=$(date +%Y%m%dT%H%M%S)
python3 tests/integration/publish_drive_token.py \
  --robot-id robot6 \
  --session "ctrl-${TOKEN_STAMP}" \
  --token "tok-ctrl-${TOKEN_STAMP}-robot6-0001"
```

이 스크립트는 Q-01에 맞춰 5 Hz로 발행하면서 `message_sequence`를 증가시킨다.
`ros2 topic pub -r 5`는 같은 sequence를 반복하므로 lease를 갱신할 수 없다.

### 터미널 2: 주행 직전 상태 확인

```bash
ros2 topic echo /robot6/motion_allowed --once \
  --qos-reliability reliable \
  --qos-durability transient_local

ros2 topic echo /robot6/amcl_pose --once
ros2 action list -t | grep -E '/robot6/(navigate_to_pose|dock|undock)'
```

`motion_allowed.data: true`와 세 Action을 확인한 뒤 START_PATROL을 한 번
발행한다. 이 시점부터 실제 언독과 주행이 시작된다.

```bash
TEST_STAMP=$(date +%Y%m%dT%H%M%S)
MISSION_ID="msn-ctrl-${TEST_STAMP}-robot6-0001"

ros2 topic pub --once \
  /robot6/mission_command \
  patrol_interfaces/msg/MissionCommand \
  "{command_id: 'cmd-ctrl-${TEST_STAMP}-robot6-start-0001',
    mission_id: '${MISSION_ID}',
    robot_id: 'robot6',
    command: 1,
    target_id: 'robot6_default',
    issued_by: 'amr-hardware-test'}"
```

START_PATROL은 dock 상태를 확인해 필요할 때 Undock Action을 실행하고,
W1~W7 `NavigateToPose`를 순서대로 실행한 뒤 Dock Action을 실행한다. 일반
Nav2 실패·goal 거절은 최초 시도 뒤 최대 3번 더 실행한다. 총 4번 실패한
중간 W1~W6은 checkpoint를 다음 지점으로 넘기고 계속하며, 마지막 W7 실패는
순찰을 실패로 종료한다. STOP/CANCEL·DriveToken 상실·`motion_allowed=false`로
취소된 goal은 재시도하거나 다음 waypoint로 넘어가지 않는다.

### 시험 중 정지

같은 mission ID와 새 command ID로 STOP을 보낸다.

```bash
STOP_STAMP=$(date +%Y%m%dT%H%M%S)
ros2 topic pub --once \
  /robot6/mission_command \
  patrol_interfaces/msg/MissionCommand \
  "{command_id: 'cmd-ctrl-${STOP_STAMP}-robot6-stop-0002',
    mission_id: '${MISSION_ID}',
    robot_id: 'robot6',
    command: 0,
    issued_by: 'amr-hardware-test'}"
```

즉시 안전 차단하려면 DriveToken 터미널을 `Ctrl+C`로 종료한다. 최대 1초
안에 lease가 만료되어 최종 속도가 0이 된다. 새 명령 없이 자동 재출발하지
않는다. 시험을 더 하지 않을 때는 미션 launch를 종료하고, Localization과
Nav2도 사용이 끝났을 때만 각각 종료한다.

## 현재 남은 범위

- 실제 robot6 W1~W7·도킹 현장 검증과 IT-16 증거 수집
- PatrolReport 수신 애플리케이션 ACK·큐 삭제 조건 합의(TBD-IF-003)
- Detection yaw 후보와 Nav2 후보의 전환 정책(TBD-AMR-001)
- Keepout·안전구역 기능 및 현장 좌표 검증

robot1에서 AMR-16의 실패 재시도·중간 waypoint skip·안전 취소를 검증할
때는 [AMR-16 실제 로봇 시험](../../docs/development/amr16-robot-test.md)을
따른다. 전용 실패 유도 설정은 기본 launch에서 자동 선택되지 않는다.
