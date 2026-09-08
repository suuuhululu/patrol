# AMR-16 실제 robot1 재시도·skip·안전 취소 시험

기준 코드: `patrol_amr` 0.4.0, 2026-09-08 로컬 작업 트리.

이 시험은 단위시험으로 대신할 수 없는 실제 경로를 확인한다.

`MissionCommand → mission_supervisor → PatrolScenario → Nav2GoalRunner →
NavigateToPose → collision_monitor → cmd_vel_safe →
local_safety_supervisor → cmd_vel → robot1`

## 합격 조건

1. `/robot1/cmd_vel` 발행자는 `local_safety_supervisor` 하나다.
2. 정상 설정에서 START_PATROL이 실제 Nav2 goal을 만들고 로봇이 W1으로 이동한다.
3. 시험 설정의 지도 밖 W1은 경로 성공 없이 네 번 실패한다. stock Nav2의
   회전·후진 recovery 동작은 발생할 수 있다.
4. 로그에 1·2·3회 실패 후 retry와 4회 최종 실패가 보이고, 이어서
   `MISSION_PATROLLING W2`가 보인다.
5. DriveToken 발행을 끊으면 1초 이내 goal이 취소되고 `cmd_vel`이 0이 된다.
6. 안전 취소 뒤 같은 goal을 재시도하거나 새 명령 없이 다시 출발하지 않는다.

시험 설정은 [amr16_retry_skip_test.yaml](../../src/patrol_amr/config/amr16_retry_skip_test.yaml)이다.
W1 `(100, 100)`은 지도 밖 실패 유도점이며 기본 실행에서는 사용되지 않는다.
로봇이 그 좌표까지 갈 수는 없지만 Nav2 BT의 recovery가 로봇을 회전·후진시킬
수 있으므로 주변 공간을 비워야 한다.
W2가 시작하면 정상 좌표로 실제 이동할 수 있으므로 작업자가 즉시 정지시킨다.

## 0. 현장 안전 준비

- robot1의 회전·짧은 후진 recovery 공간까지 비우고 작업자가 물리 E-stop에
  손을 둔다.
- 관제·다른 시험자가 같은 robot1에 명령하지 않는 단독 시험에서만 수행한다.
- 이미 `/robot1` localization/Nav2가 실행 중이면 중복 실행하지 않는다.
- 로컬 latch가 이미 걸렸다면 reset 계약이 없으므로 시험 노드를 재시작한다.

## 1. 빌드와 환경

모든 터미널에서 실제 설치 경로에 맞춰 TurtleBot4 underlay를 먼저 source한다.

```bash
cd /home/mu-01/patrol
source /opt/ros/jazzy/setup.bash
source /home/mu-01/turtlebot4_ws/install/setup.bash
source /home/mu-01/rokey_ws/install/setup.bash
colcon build --packages-select patrol_interfaces patrol_amr --symlink-install
source /home/mu-01/patrol/install/setup.bash
export ROS_DOMAIN_ID=6
unset ROS_LOCALHOST_ONLY
```

## 2. 중복 노드 확인

```bash
ros2 node list | sort
ros2 action list -t | grep -E '/robot1/(navigate_to_pose|dock|undock)'
timeout 5s ros2 topic echo /robot1/scan --once
timeout 5s ros2 topic echo /robot1/odom --once
```

기존 `/robot1` localization과 Nav2가 보이면 아래 launch에서
`start_localization:=false start_nav2:=false`를 쓴다. 보이지 않으면 두 값을
`true`로 바꾼다. `mission_supervisor`, `local_safety_supervisor`,
`status_reporter`가 이미 있으면 기존 시험 launch를 먼저 종료한다.
`scan`·`odom`이 한 번도 오지 않으면 robot1 또는 Discovery 연결부터 복구하고
주행 시험을 시작하지 않는다. 2026-09-08 자동 확인 시 현재 ROS 그래프에는
노드가 없었으므로, 별도 Nav2를 아직 띄우지 않았다면 아래 두 start 값을
`true`로 사용한다.

## 3. 실패 재시도·skip 설정으로 실제 경로 실행

터미널 1에서 계속 실행한다.

```bash
ros2 launch patrol_amr hardware_patrol.launch.py \
  robot_id:=robot1 \
  start_localization:=true \
  start_nav2:=true \
  start_local_safety:=true \
  start_status_reporter:=true \
  mission_params_file:=/home/mu-01/patrol/install/patrol_amr/share/patrol_amr/config/amr16_retry_skip_test.yaml \
  motion_enable_token:=ENABLE_ROBOT1_MOTION
```

터미널 2에서 연결을 확인한다.

```bash
ros2 topic info /robot1/cmd_vel_safe --verbose
ros2 topic info /robot1/cmd_vel --verbose
ros2 topic info /robot1/mission_command --verbose
ros2 action list -t | grep -E '/robot1/(navigate_to_pose|dock|undock)'
```

`cmd_vel_safe`에는 collision monitor publisher와 local safety subscription이,
`cmd_vel`에는 local safety publisher 하나가 있어야 한다.
Localization을 새로 시작했다면 RViz 또는 합의된 초기 pose 발행 절차로
robot1의 실제 초기 위치를 먼저 설정하고 `/robot1/amcl_pose`를 확인한다.

관제가 없는 단독 시험에서만 터미널 2에서 E-stop 비활성 상태를 한 번 보낸다.

```bash
ros2 topic pub --once \
  --qos-reliability reliable \
  --qos-durability transient_local \
  /control/estop patrol_interfaces/msg/EStop \
  "{target_robot_id: 'robot1', active: false, reason: 0, latched: false, sequence: 1}"
```

터미널 3에서 증가 sequence DriveToken을 계속 갱신한다.

```bash
cd /home/mu-01/patrol
source /opt/ros/jazzy/setup.bash
source /home/mu-01/patrol/install/setup.bash
export ROS_DOMAIN_ID=6
unset ROS_LOCALHOST_ONLY
python3 tests/integration/publish_drive_token.py \
  --robot-id robot1 \
  --session ctrl-20260908T160000-1 \
  --token tok-ctrl-20260908T160000-robot1-0001
```

터미널 2에서 `data: true`를 확인한 뒤에만 명령을 보낸다.

```bash
ros2 topic echo /robot1/motion_allowed --once \
  --qos-reliability reliable \
  --qos-durability transient_local

ros2 topic pub --once /robot1/mission_command \
  patrol_interfaces/msg/MissionCommand \
  "{command_id: 'cmd-ctrl-20260908T160000-1-robot1-start-0001', mission_id: 'msn-ctrl-20260908T160000-1-robot1-0001', robot_id: 'robot1', command: 1, target_id: '', issued_by: 'amr16-hardware-test', parameters_json: '{}'}"
```

터미널 1에서 다음 순서를 확인한다.

```text
W1 attempt 1/4 failed: ...; retrying
W1 attempt 2/4 failed: ...; retrying
W1 attempt 3/4 failed: ...; retrying
W1 failed after 4 attempts: ...
MISSION_PATROLLING W2
```

`MISSION_PATROLLING W2`가 보이는 즉시 터미널 3의 DriveToken을 `Ctrl+C`로
끊는다. 물리적으로 즉시 멈춰야 하면 로그를 기다리지 말고 E-stop을 누른다.

터미널 2에서 정지와 자동 재출발 없음을 확인한다.

```bash
ros2 topic echo /robot1/cmd_vel --once
ros2 topic echo /robot1/robot_status --once
```

`cmd_vel`의 linear·angular 값이 모두 0이고, 터미널 1에 motion authority 상실과
goal 취소가 보이며, DriveToken을 다시 발행하지 않는 동안 재출발하면 안 된다.

## 4. 정상 W1~W7 시험

실패 시험 launch를 종료하고 같은 명령에서
`mission_params_file`만 기본 파일로 바꿔 새 session·command·mission ID로
재실행한다.

```bash
ros2 launch patrol_amr hardware_patrol.launch.py \
  robot_id:=robot1 \
  start_localization:=true \
  start_nav2:=true \
  start_local_safety:=true \
  start_status_reporter:=true \
  mission_params_file:=/home/mu-01/patrol/install/patrol_amr/share/patrol_amr/config/patrol_params.yaml \
  motion_enable_token:=ENABLE_ROBOT1_MOTION
```

새 DriveToken session과 새 구조화 ID로 START_PATROL을 보내 W1~W7 이동과
마지막 도킹을 확인한다. 실제 도킹 센서 의미는 TBD-AMR-004가 남아 있으므로,
AMR-16 합격은 W1~W7의 Nav2 goal·feedback·최종 goal까지로 판정하고 도킹
성공 판정은 AMR-13에서 별도로 닫는다.

## 결과 기록

| 항목 | 실제 결과 |
|---|---|
| 최종 `cmd_vel` 발행자 1개 | 미실행 |
| 정상 W1 goal·feedback | 미실행 |
| 실패 W1 총 4회 | 미실행 |
| 실패 뒤 W2 skip 진행 | 미실행 |
| token 상실 시 1초 내 정지 | 미실행 |
| 안전 취소 뒤 자동 재출발 없음 | 미실행 |
| 정상 W1~W7 최종 goal | 미실행 |

사용자가 실제 결과를 확인한 뒤에만 이 표를 PASS로 바꾸고 AMR-16을
`완료 / 100%`로 표시한다.
