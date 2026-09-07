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
| 5 | `motion_guard.py`: token·E-stop 결합 최종 출력 게이트 (축소 범위) | 구현·단위시험 완료, 사용자 검토 대기 |
| 6 | `local_safety_supervisor.py` ROS 노드 (축소 범위) | 구현·단위시험·사용자 ROS 토픽 시험 통과 |
| 7 | `robot_status_state.py`: 독립 상태 축·현재/마지막 유효 pose snapshot | 구현·단위시험 완료, 사용자 검토 대기 |
| 8 | `status_reporter.py` ROS 노드 | 미착수 |
| 9 | `patrol_amr` 패키지 설정·실행 등록·통합 | 미착수 |
| 10 | 통합시험 | 미착수 |

최종 ROS 노드는 `battery_monitor`, `local_safety_supervisor`, `status_reporter` 세 개다. guard와 state 파일은 해당 노드가 사용하는 일반 Python 모듈이다. 한 단계씩 구현하고 사용자 시험 통과 확인 전에는 다음 단계로 넘어가지 않는다.

2026-09-07 17:12 KST 진행 상황:

- 작업 브랜치 HEAD는 `13f0412`(`fix(amr): drop drive_token subscriber deadline QoS`)다. 이 브랜치는 현재 `origin/feat/amr-safety-status`보다 10개 커밋 앞서 있으므로, 다른 환경에서 이어서 작업하기 전 원격 push 여부를 확인해야 한다.
- 1~6단계에 해당하는 단위시험은 E-stop 해제 로그 추가 전 73개가 모두 통과했다. 2026-09-07 18:34 KST E-stop 해제 로그 구현과 시험 3개를 추가했고, 변경 후 6단계 단독 14개와 전체 76개가 모두 통과했다.
- 6단계 사용자 ROS 토픽 시험 중 drive_token의 `DEADLINE` 불일치와 E-stop의 `DURABILITY` 불일치를 확인했다. drive_token 구독측 deadline 문제는 `13f0412`에서 수정했고, E-stop은 계약에 맞는 QoS 옵션을 시험 명령에 지정해야 한다.
- 위 수정 이후 17:19 KST 사용자 재시험에서 노드의 최초 `motion_allowed=false`, echo 수신, QoS를 맞춘 E-stop 해제 메시지의 구독자 매칭과 1회 발행까지 확인했다. 이 시점의 `false` 유지는 DriveToken을 아직 입력하지 않았으므로 정상이다.
- 17:28 KST 사용자가 이어서 DriveToken 수락 시 `false → true`, 3초 lease 만료 시 `true → false` 전이를 확인했다. 6단계의 최소 ROS 토픽 통과 기준을 충족하여 완료 처리했다. 실제 최종 속도·장애물·로봇 실기 시험은 이 축소 범위에 포함되지 않는다.
- 사용자 7단계 진행 승인 후 `robot_status_state.py`와 단위시험 17개를 추가했다. 새 `interfaces.md`의 `_state` 필드 이름을 내부 모델에 반영했고, 현재 `RobotStatus.msg`가 예전 이름과 제안 필드를 유지하는 불일치를 확인했다. 공용 메시지는 7단계 범위에서 수정하지 않았으며 8단계 전에 동기화가 필요하다.
- 작업 루트 아래 추적되지 않는 중첩 저장소 `patrol/`이 있다. 삭제 여부는 결정하지 않았으며, 시험은 바깥 작업 루트에서 수행해야 한다.

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

## 6.3 5단계 구현 내용과 범위 축소

`src/patrol_amr/patrol_amr/motion_guard.py`는 3·4단계와 같은 일반 Python 모듈이다. 원래 파일명이 함의하는 장애물 회피·정지 거리·감속은 TBD-AMR-006이 전부 미정으로 남긴 부분이라, 진행 전 사용자에게 확인하고 범위를 좁혔다.

- 구현한 것: token 미부여 또는 E-stop 활성 중 하나라도 해당하면 속도 후보를 버리고 정지(0.0, 0.0)를 출력하는 AND 게이트. 3·4단계 가드의 판정을 그대로 입력받는다.
- 구현하지 않은 것: Nav2·yaw 후보 중 선택(TBD-AMR-001), 장애물 감지·감속·정지 거리·센서 고장 판정(TBD-AMR-006), 속도 상한, 최종 발행 타입(TBD-IF-009). 실제 로봇 사양·물리량이 필요해 근거 없이 구현하면 안전성이 검증되지 않은 채 "구현됨"으로 보일 위험이 있었다.

단위시험:

```bash
cd ~/patrol
python3 -m unittest discover -s tests -p test_motion_guard.py -v
```

예상 결과는 `Ran 10 tests`와 `OK`다. 지금까지 네 파일을 함께 돌리려면 `-p "test_*.py"`를 쓴다. 예상 결과는 `Ran 59 tests`와 `OK`다.

이 모듈도 ROS 토픽 시험 대상이 아니다. 남겨둔 장애물·감속 범위는 TBD-AMR-006 해결과 로봇 실기 이후에 별도로 다룬다. 상세는 [amr.md 3.3절](../amr.md#33-motion_guardpy--구현-대조-완료)에 있다.

## 6.4 6단계 구현 내용과 범위

`src/patrol_amr/patrol_amr/local_safety_supervisor.py`는 3~5단계 가드를 실제 ROS 노드로 묶은 첫 지점이다. 5단계와 같은 이유로 진행 전 범위를 확인했다.

- 구현한 것: `/control/drive_token`·`/control/estop`을 실제 구독해 3·4단계 가드에 반영하고, 결합 결과를 AMR 내부 신호 `motion_allowed`(`std_msgs/Bool`)로 발행한다. drive_token의 Q-01 lease가 메시지 없이도 시계로 만료되도록 0.1초 재확인 타이머를 둔다(`battery_monitor`의 신선도 검사와 같은 간격).
- 구현하지 않은 것: 실제 속도 후보 입력과 최종 속도 발행. Nav2·yaw 후보 중재(TBD-AMR-001)는 `mission_supervisor` 담당이며 이 작업 범위(AMR Python 파일 7개·ROS 노드 3개) 밖이고, 최종 발행 타입(TBD-IF-009)도 미정이다. `MotionGuard.evaluate()`는 준비돼 있지만 아직 실제 후보로 호출되지 않는다.
- `robot_id`는 필수 ROS parameter다. 미지정·오지정 시 노드가 시작하지 않는다.

단위시험 (ROS 불필요, `SafetyGate`는 순수 Python):

```bash
cd ~/patrol
python3 -m unittest discover -s tests -p test_local_safety_supervisor.py -v
```

첫 명령은 저장소 루트로 이동하고, 두 번째 명령은 ROS 그래프 없이 `SafetyGate`의 조합 규칙과 E-stop 해제 로그 선택을 시험한다. 예상 결과는 `Ran 14 tests`와 `OK`다. 지금까지 다섯 파일을 함께 돌리려면 `-p "test_*.py"`를 쓴다. 예상 결과는 `Ran 76 tests`와 `OK`다. 2026-09-07 18:34 KST에 두 결과를 확인했다.

이 노드는 2단계·6단계처럼 실제 ROS 토픽 시험 대상이다. 상세는 [amr.md 3.4절](../amr.md#34-local_safety_supervisorpy--구현-대조-완료-축소-범위)에 있다.

### 6단계 사용자 ROS 토픽 시험 순서

이 시험의 목적은 다음 세 가지를 순서대로 확인하는 것이다.

1. 메시지가 없을 때 안전 기본값인 `motion_allowed=false`인지 확인한다.
2. E-stop이 해제되고 유효한 robot1 DriveToken이 있을 때만 `true`가 되는지 확인한다.
3. 새 메시지가 없어도 token lease가 만료되면 다시 `false`가 되는지 확인한다.

명령은 아래의 **사전 확인 → 터미널 1 → 터미널 2 → 터미널 3** 순서로 실행한다. 각 터미널의 `source`는 해당 터미널에만 적용되므로 생략하거나 다른 터미널에서 대신 실행할 수 없다. 모든 터미널은 같은 `ROS_DOMAIN_ID`와 기존 Discovery 설정을 사용해야 하며, TB4 Onboard/Offboard Discovery 설정을 시험 편의를 위해 제거하지 않는다.

#### 0. 사전 확인 — 저장소·브랜치·메시지 빌드

먼저 어느 저장소를 시험하는지 확인한다.

```bash
cd ~/patrol
git rev-parse --show-toplevel
git branch --show-current
git log -1 --oneline
```

- `cd`는 모든 상대 경로의 기준을 저장소 루트로 맞춘다.
- `git rev-parse`는 중첩 clone이 아닌 바깥 `~/patrol`을 보고 있는지 확인한다.
- 브랜치는 `feat/amr-safety-status`, HEAD는 `13f0412` 이상이어야 한다. `main` 또는 `~/patrol/patrol`이 나오면 6단계 시험 대상이 아니다.

다음으로 ROS 기본 환경을 읽고 공용 메시지 패키지를 빌드한다.

```bash
source /opt/ros/jazzy/setup.bash
colcon build --packages-select patrol_interfaces
source install/local_setup.bash
ros2 interface show patrol_interfaces/msg/DriveToken
ros2 interface show patrol_interfaces/msg/EStop
```

- 첫 `source`는 ROS 2 Jazzy 명령과 기본 메시지를 현재 셸에 등록한다.
- `colcon build --packages-select`는 6단계가 구독하는 공용 메시지 패키지만 빌드한다. `patrol_amr` 자체의 패키지 등록은 9단계 범위라 아직 빌드하지 않는다.
- 두 번째 `source`는 방금 빌드한 `patrol_interfaces`를 현재 셸에서 찾게 한다.
- 마지막 두 명령은 메시지 타입이 실제로 조회되는지 확인한다. `Unknown package`면 다음 단계로 진행하지 않고 빌드 결과와 overlay source를 먼저 고친다.

#### 1. 터미널 1 — local_safety_supervisor 실행

새 터미널에서 실행한다.

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
python3 src/patrol_amr/patrol_amr/local_safety_supervisor.py \
  --ros-args -p robot_id:=robot1
```

- `python3 ...local_safety_supervisor.py`는 ROS 노드를 직접 실행한다. 아직 9단계의 `setup.py`와 entry point가 없으므로 `ros2 run`을 사용하지 않는다.
- `--ros-args -p robot_id:=robot1`은 이 노드가 robot1의 token만 자신의 주행 권한으로 인정하도록 필수 파라미터를 전달한다.
- 이 터미널은 시험이 끝날 때까지 켜 둔다. 최초 예상 로그는 `motion allowed: False blocked_reasons: ['drive_token_not_granted', 'estop_active']`다.

#### 2. 터미널 2 — motion_allowed 연속 관찰

터미널 1을 켠 다음 새 터미널에서 실행한다.

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
ros2 topic echo --no-daemon \
  --qos-durability transient_local \
  --qos-reliability reliable \
  /motion_allowed std_msgs/msg/Bool
```

- `topic echo`는 안전 판정 결과를 계속 출력한다. 발행 명령보다 먼저 실행해야 짧은 상태 전이도 놓치지 않는다.
- `--no-daemon`은 다른 Discovery 설정으로 시작된 ROS daemon의 조회 결과가 섞이는 것을 피한다.
- durability와 reliability는 `motion_allowed` 발행자의 QoS에 맞추고, 늦게 구독해도 마지막 상태를 받게 한다.
- 최초 예상 출력은 `data: false`다. 이 터미널도 시험이 끝날 때까지 켜 둔다.

#### 3. 터미널 3 — E-stop 해제 상태 입력

터미널 2까지 켠 다음 새 터미널에서 실행한다.

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
ros2 topic pub --once \
  --qos-durability transient_local \
  --qos-reliability reliable \
  /control/estop patrol_interfaces/msg/EStop \
  "{active: false, cause: 0, physical: false, source: 'test', sequence: 1}"
```

- `--once`는 시험 메시지 하나만 발행하고 종료한다.
- `active: false`는 관제가 E-stop 해제 상태를 알렸다는 뜻이다. AMR이 자체적으로 해제를 결정한다는 뜻은 아니다.
- 아직 DriveToken이 없으므로 `motion_allowed`는 계속 `false`다. 다만 수락된 관측이 최초 안전 기본값 `active=true`에서 `false`로 바뀌었으므로, 터미널 1에는 `E_STOP_AUTO_RELEASED robot_id=robot1 source='test' sequence=1` 로그가 나와야 한다. 같은 상태를 반복하거나 낮은·동일 sequence가 폐기되면 이 로그를 다시 남기지 않는다.

#### 4. 터미널 3 — 3초 DriveToken 입력과 lease 만료 확인

같은 터미널 3에서 이어서 실행한다.

```bash
ros2 topic pub --once \
  --qos-reliability best_effort \
  --qos-durability volatile \
  /control/drive_token patrol_interfaces/msg/DriveToken \
  "{token: 'lease-test', holder_robot_id: 'robot1', lease_duration: {sec: 3, nanosec: 0}, sequence: 1}"
```

- `holder_robot_id: robot1`은 터미널 1의 `robot_id` 파라미터와 일치해야 한다.
- `lease_duration`은 이 권한의 유효시간을 3초로 지정한다.
- 이 메시지가 수락되면 터미널 2에 `data: true`, 약 3초 뒤 새 메시지 없이 `data: false`가 차례로 나와야 한다.
- 터미널 1에는 `motion allowed: True blocked_reasons: []` 뒤에 `motion allowed: False blocked_reasons: ['drive_token_not_granted']`가 나와야 한다.

#### 5. 선택 시험 — E-stop의 즉시 차단과 해제 반영

먼저 E-stop을 시험할 시간을 확보하도록 30초짜리 새 token을 준다. token 문자열이 바뀌면 새 epoch이므로 sequence를 1부터 사용할 수 있다.

```bash
ros2 topic pub --once \
  --qos-reliability best_effort \
  --qos-durability volatile \
  /control/drive_token patrol_interfaces/msg/DriveToken \
  "{token: 'estop-test', holder_robot_id: 'robot1', lease_duration: {sec: 30, nanosec: 0}, sequence: 1}"
```

`data: true`를 확인한 뒤 E-stop을 활성화한다.

```bash
ros2 topic pub --once \
  --qos-durability transient_local \
  --qos-reliability reliable \
  /control/estop patrol_interfaces/msg/EStop \
  "{active: true, cause: 2, physical: false, source: 'test', sequence: 2}"
```

즉시 `data: false`가 나와야 한다. 이어서 더 큰 sequence로 관제의 해제 상태를 전달한다.

```bash
ros2 topic pub --once \
  --qos-durability transient_local \
  --qos-reliability reliable \
  /control/estop patrol_interfaces/msg/EStop \
  "{active: false, cause: 0, physical: false, source: 'test', sequence: 3}"
```

30초 token이 아직 유효하면 `data: true`로 돌아온다. 이 결과는 E-stop 해제를 자동 주행 재개로 판단했다는 뜻이 아니라, 이번 축소 범위의 내부 안전 게이트가 허용 상태로 돌아왔다는 뜻이다. 실제 임무 재개 조건은 아직 별도 범위다.

#### 6. 종료와 통과 기준

발행 명령은 `--once`라 자동 종료된다. 터미널 2의 echo와 터미널 1의 노드는 각각 `Ctrl+C`로 종료한다.

6단계 사용자 ROS 토픽 시험의 최소 통과 기준은 다음과 같다.

- 최초 `false` 확인
- E-stop 해제 입력 후 `E_STOP_AUTO_RELEASED` 로그 확인
- E-stop 해제와 유효 token이 모두 있을 때만 `true` 확인
- 3초 token이 새 메시지 없이 만료된 뒤 `false` 확인
- 선택 E-stop 시험을 수행했다면 활성 즉시 `false`, 더 큰 sequence의 해제 상태 반영 확인
- `DEADLINE` 또는 `DURABILITY` QoS 불일치 경고가 없을 것

2026-09-07 17:28 KST 사용자가 최초 `false`, 유효 token 수락 후 `true`, 3초 lease 만료 후 `false`를 확인하여 6단계 최소 ROS 토픽 시험을 통과 처리했다.

### QoS·sequence 시험 시 유의사항 (2026-09-07 사용자 시험 중 발견·수정)

- `/control/drive_token`은 일반 `ros2 topic pub`으로도 호환되지만, 위 시험 명령에는 의도를 분명히 하려고 BEST_EFFORT·VOLATILE을 명시했다.
- `/control/estop`은 노드가 TRANSIENT_LOCAL·RELIABLE을 요구한다(9절). `ros2 topic pub` 기본값이 VOLATILE이면 `Last incompatible policy: DURABILITY` 경고와 함께 메시지가 전달되지 않는다. 위 두 QoS 옵션을 반드시 함께 사용한다.
- 최초 구현에는 drive_token 구독에도 9절의 "deadline 200ms"를 요청 QoS로 걸었으나, `ros2 topic pub`을 포함해 deadline을 명시하지 않는 발행자와 DDS 계층에서 호환되지 않아 메시지가 전혀 도달하지 않는 것을 확인했다. 구독측 deadline 요청은 `13f0412`에서 제거했다. 신선도는 이미 구현된 Q-01 lease 만료가 담당한다. 근거는 [amr.md 3.4절](../amr.md#34-local_safety_supervisorpy--구현-대조-완료-축소-범위)에 있다.
- DriveToken을 `-r 5`로 발행하면서 동일한 YAML과 동일한 `sequence`를 반복하면, 첫 메시지 외에는 재수신으로 폐기된다. 따라서 lease도 연장되지 않는다. 실제 관제 발행자는 발행할 때마다 sequence를 증가시켜야 하며, 단순 CLI 시험은 위처럼 `--once`와 명시적인 lease 만료를 사용한다.
- E-stop도 마지막 수락 sequence 이하의 메시지는 폐기한다. 상태를 바꿀 때마다 `1 → 2 → 3`처럼 증가시킨다.

## 6.5 7단계 구현 내용과 시험 순서

`src/patrol_amr/patrol_amr/robot_status_state.py`는 8단계 `status_reporter`가 방송할 내용을 미리 정리하는 **로봇 상태 메모장**이다. ROS 노드가 아니므로 터미널 여러 개나 `ros2 topic` 명령은 필요 없다.

- 상태를 `operational_state`, `mission_state`, `docking_state`, `battery_state`, `safety_state` 다섯 칸으로 따로 보관한다. 예를 들어 “이동 중”과 “순찰 중”을 하나의 상태로 합치지 않는다.
- 시작할 때는 운행 상태 UNKNOWN, 임무 NONE, 도킹 UNKNOWN, 배터리 UNKNOWN, 현재 위치 무효다. 아직 받은 정보가 없는데 READY라고 거짓 보고하지 않는 안전한 초기값이다.
- `update_states()`는 값이 실제로 달라졌을 때만 `revision`을 올린다. 이 값은 다음 단계가 “상태가 바뀌었으니 즉시 방송할까?”를 판단할 때 쓰는 내부 번호다.
- `observe_pose()`는 유효한 현재 위치를 받으면 마지막 유효 위치도 함께 저장한다. 이후 위치가 무효가 되어도 마지막 유효 위치는 남겨 복구 참고용으로 쓸 수 있게 한다. 단, `pose_valid=false`인 현재 위치를 주행 가능한 위치로 바꾸지는 않는다.
- `snapshot()`은 마지막 유효 위치가 몇 초 전 측정인지 계산하고, 호출자가 나중에 내용을 바꿔도 내부 메모장이 훼손되지 않도록 복사본을 반환한다.

### 새 interfaces.md 반영 확인

7단계 내부 이름은 새 문서에 맞췄다. 그러나 공용 `src/patrol_interfaces/msg/RobotStatus.msg`는 아직 아래처럼 이전 이름·구조다.

| 새 interfaces.md | 현재 RobotStatus.msg | 판단 |
|---|---|---|
| `operational_state` | `operational` | 이름 동기화 필요 |
| `mission_state` | `mission` | 이름 동기화 필요 |
| `docking_state` | `docking` | 이름 동기화 필요 |
| `battery_state` | `battery` | 이름 동기화 필요 |
| `safety_state` | `safety` | 이름과 enum 합의 필요 |
| `active_command_id`, `active_mission_id` | `command_id`만 존재 | 필드 동기화 필요 |
| `accepted_token_id`, `token_valid` | 없음 | 필드 동기화 필요 |
| `battery_soc`, `battery_timestamp` | `battery_percentage`만 존재 | 이름·필드 동기화 필요 |
| string `current_waypoint_id`, `scan_state` | uint 숫자 필드 | TBD-IF-003 합의 필요 |

공용 메시지는 AMR·관제·시스템 모니터가 함께 쓰므로 7단계 승인만으로 변경하지 않았다. 기존 [관제 요청서](../change_requests/CR-관제_09-07_15-55_AMR_명령_토큰_상태_안전_계약_변경.md)가 이 동기화를 요청하고 있다. 8단계 `status_reporter`는 실제 `.msg` 필드에 값을 넣어야 하므로, 구현 전에 공용 메시지 변경 범위와 safety/waypoint/scan 잔여 타입을 확정해야 한다.

### 단위시험 실행 순서

1. 저장소 루트로 이동한다.

```bash
cd ~/patrol
```

이 명령은 아래 상대 경로가 바깥 작업 루트의 `tests`와 `src`를 바라보게 한다. 중첩된 `~/patrol/patrol`에서 실행하지 않는다.

2. 7단계 시험만 실행한다.

```bash
python3 -m unittest discover -s tests -p test_robot_status_state.py -v
```

`unittest discover`가 `tests` 폴더에서 7단계 시험 파일 하나를 찾아 상세 모드로 실행한다. ROS를 source하거나 노드를 켤 필요가 없다. 예상 결과는 `Ran 17 tests`와 `OK`다.

3. 1~7단계 전체 회귀시험을 실행한다.

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

새 코드 때문에 기존 배터리·token·E-stop·motion·local safety가 깨지지 않았는지 함께 확인한다. 7단계 추가 후 예상 결과는 `Ran 93 tests`와 `OK`다.

시행 순서는 **7단계 단독 시험 → 전체 회귀시험**이다. 첫 시험이 실패하면 전체 시험으로 넘어가지 말고 실패한 테스트 이름과 traceback부터 확인한다. 7단계는 ROS 통신 코드가 아니므로 사용자 수동 토픽 시험은 없고, 실제 `/robot1/robot_status` 확인은 8단계에서 진행한다.

## 7. 결정·미완료 사항

TBD-AMR-003은 사용자의 권장안 승인으로 AMR 코드에 반영했으며 `docs/change_requests/CR-AMR_09-07_14-01_배터리_입력_정책.md`에 관제 검토를 요청했다. 실제 robot1·robot6 배터리 드라이버, 관제 연계, 도킹·교대 시험은 아직 수행하지 않았다.

현재 `patrol_amr`에는 `setup.py`, `package.xml`, 실행 entry point가 없다. 이는 9단계 패키지 통합 범위다. 2단계 시험은 Python 파일을 직접 실행한다. 이전 `final_turtlebot_ws`의 다른 실행 코드나 build/install/log 결과를 새 저장소로 복사하지 않는다.

작업 재개 전에 루트 `AGENTS.md`, `docs/architecture.md`, `docs/interfaces.md`, `docs/amr.md`를 확인한다. 기존 플로우차트는 설계 초안이며 확정 계약으로 사용하지 않는다. 다른 담당자의 변경과 미확정 TBD를 보존한다.
