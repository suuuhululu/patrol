# AMR 개발 워크스페이스 인수인계

작성일: 2026-09-07 · 최종 갱신: 2026-09-08 08:35 KST · 작업 브랜치: `feat/amr-safety-status`

## 1. 작업 범위와 현재 상태

조정묵 담당 범위는 공용 메시지 기반과 AMR Python 파일 7개, ROS 노드 3개다. 과거 업무 분장 자료의 `parking_interfaces`와 `final_turtlebot_pkg`는 현재 저장소 경로가 아니다. 현재 이름은 `patrol_interfaces`와 `patrol_amr`이며, 옛 이름의 패키지를 새로 만들지 않는다.

| 단계 | 대상 | 상태 |
|---|---|---|
| 1 | `patrol_interfaces`: MissionCommand, CommandCheck, DriveToken, RobotStatus, PatrolReport, EStop 및 빌드 설정 | 최신 interfaces.md 이름 반영·빌드·interface show 6종 확인 완료 |
| 2 | `battery_monitor.py`: 배터리 분류·3초 상태 전이·ROS 구독/내부 상태 발행 | 구현·단위시험·사용자 ROS 토픽 시험 통과 |
| 3 | `drive_token_guard.py`: control session·token ID·message sequence·Q-01 lease | 최신 이름 반영·단위시험 완료, 사용자 검토 대기 |
| 4 | `estop_guard.py`: target robot·reason·latched·sequence 반영 | 최신 이름 반영·단위시험 완료, 사용자 검토 대기 |
| 5 | `motion_guard.py`: token·E-stop 결합 최종 출력 게이트 (축소 범위) | 구현·단위시험 완료, 사용자 검토 대기 |
| 6 | `local_safety_supervisor.py` ROS 노드 (축소 범위) | 구현·단위시험·사용자 ROS 토픽 시험 통과 |
| 7 | `robot_status_state.py`: 독립 상태 축·현재/마지막 유효 pose snapshot | 구현·단위시험 완료, 사용자 검토 대기 |
| 8 | `status_reporter.py` ROS 노드 (확정 입력 연결 범위) | 구현·단위시험·사용자 ROS 토픽 시험 통과 |
| 9 | `patrol_amr` 패키지 설정·실행 등록·통합 | 구현·회귀시험·`ros2 launch` 통합 실행 확인 완료, 사용자 검토 대기 |
| 10 | 단일 robot AMR 로컬 ROS 통합 스모크 시험(구현된 두 경로만) | 자동시험 PASS·사용자 확인 완료(2026-09-08). 전체 시스템 IT는 미실행 |
| 11 | `motion_guard.py` Q-17 후보 신선도 판정 | 구현·단위시험 26건 완료. 10단계 스모크 회귀 PASS, 사용자 검토 대기 |

최종 ROS 노드는 `battery_monitor`, `local_safety_supervisor`, `status_reporter` 세 개다. guard와 state 파일은 해당 노드가 사용하는 일반 Python 모듈이다. 한 단계씩 구현하고 사용자 시험 통과 확인 전에는 다음 단계로 넘어가지 않는다.

11단계 이후 계획은 [11절](#11-11단계-이후-실행-계획--2026-09-08)에 있다. 11~13단계는 관제 회신 없이 지금 착수할 수 있고, 14단계부터는 TBD 해소 또는 타 담당자 코드 병합이 선행되어야 한다.

### 최신 재개 체크포인트 — 2026-09-08 08:35 KST

- 현재 로컬 HEAD는 `9eb151f`(`test(amr): add stage 10 local integration smoke`)이고 브랜치는 `feat/amr-safety-status`다. `origin/feat/amr-safety-status`와 앞뒤 차이가 없다(`0 0`). 1~10단계가 모두 push되어 있으므로 다른 컴퓨터에서 clone/pull로 현재 상태를 재현할 수 있다.
- 2026-09-08 08:29 KST 재검증: `colcon build --packages-select patrol_interfaces patrol_amr` `2 packages finished`, 단위시험 `Ran 89 tests`/`OK`, 10단계 스모크 `STAGE10_PASS`. `motion_allowed=false,true,false,true,false`, `battery_state=0,2,0`, `status_sequence=1..19`. 10단계는 사용자 확인까지 통과 처리했다.
- 다음 작업은 11단계 코드가 아니라 **TBD-IF-009 계약 결정**이다. 근거와 제안은 [요청서](../change_requests/CR-AMR_09-08_08-31_최종_cmd_vel_경로와_주행_후보_토픽.md)에 있고 아래 10.2절에 요약했다.
- 아래 이력 항목의 `0efa7fa` 언급은 당시 기록이며 현재 HEAD가 아니다.
- 2026-09-07 20:32 KST 재검증에서 `patrol_interfaces` 빌드는 `1 package finished`, 전체 단위시험은 `Ran 89 tests`와 `OK`, `git diff --check`는 출력 없이 통과했다.
- 6단계 사용자 ROS 토픽 시험 중 drive_token의 `DEADLINE` 불일치와 E-stop의 `DURABILITY` 불일치를 확인했다. drive_token 구독측 deadline 문제는 `13f0412`에서 수정했고, E-stop은 계약에 맞는 QoS 옵션을 시험 명령에 지정해야 한다.
- 위 수정 이후 17:19 KST 사용자 재시험에서 노드의 최초 `motion_allowed=false`, echo 수신, QoS를 맞춘 E-stop 해제 메시지의 구독자 매칭과 1회 발행까지 확인했다. 이 시점의 `false` 유지는 DriveToken을 아직 입력하지 않았으므로 정상이다.
- 17:28 KST 사용자가 이어서 DriveToken 수락 시 `false → true`, 3초 lease 만료 시 `true → false` 전이를 확인했다. 6단계의 최소 ROS 토픽 통과 기준을 충족하여 완료 처리했다. 실제 최종 속도·장애물·로봇 실기 시험은 이 축소 범위에 포함되지 않는다.
- 사용자 요청으로 1~6단계의 공용 이름을 최신 `interfaces.md`에 맞췄다. CommandCheck 추가, MissionCommand의 mission ID, DriveToken의 control session/token ID/message sequence, EStop의 target/reason/latched, RobotStatus의 `_state` 및 구조화 상태 필드, PatrolReport의 ID·시간 필드를 반영했다. 공용 패키지 빌드와 메시지 6종 조회를 통과했다.
- `drive_token_guard`는 같은 control session 단위로 message sequence를 비교하도록, `estop_guard`는 자기 `target_robot_id`만 반영하도록 수정했다. 미정인 E-stop 전체 대상 문자열과 reason/safety enum 숫자는 만들지 않았다.
- 8단계 `status_reporter.py`를 추가했다. battery enum·원본 SOC는 연결했고 Q-02 2 Hz/변경 최대 10 Hz와 status sequence를 구현했다. 위치·odometry·mission·accepted token의 내부 입력 계약은 없어 안전한 미연결 값으로 남겼다. 8단계 단위시험 9개, 전체 89개가 통과했다.
- 사용자가 6.6절의 8단계 ROS 토픽 시험을 수행했다고 알려 와 8단계를 완료 처리했다. 이 문서를 갱신한 세션은 사용자 터미널의 출력 값을 직접 보지 않았으므로, 개별 필드 값은 사용자 확인에 근거한다.
- 위 사용자 시험에 앞서 같은 절차를 격리 도메인에서 헤드리스로 사전 실행했다. `battery_state`의 `0 → 2 → 0`, `battery_soc: 0.15`, `status_sequence`의 연속 증가, QoS 경고 없음을 확인했다. 6단계에서 겪은 DEADLINE·DURABILITY 불일치가 8단계에는 없다는 것을 미리 확인하기 위한 것이다.
- 9단계를 구현했다. `patrol_amr`을 ament_python 패키지로 만들고 entry point 3개와 launch 1개를 등록했으며, `local_safety_supervisor`·`status_reporter`의 sibling import를 `from patrol_amr import ...` 패키지 import로 전환했다. 상세는 아래 6.7절에 있다.
- `0efa7fa` 커밋은 9단계 작업과 병행해 열려 있던 다른 작업 세션에서 만들어졌다. 내용을 대조한 결과 1~9단계 코드·메시지·시험·패키지 설정이 모두 온전히 들어갔고 누락이나 덮어쓰기는 없었다. 같은 저장소에 두 세션을 동시에 열면 이런 교차 커밋이 생기므로 한 번에 한 세션만 쓰는 편이 안전하다.
- 10단계 로컬 스모크까지 자동 검증했다. 다음 개발 재개 지점은 10절의 재정리된 우선순위와 상태표를 따른다.
- 이전에 기록했던 작업 루트 아래 중첩 `patrol/` 디렉터리는 현재 존재하지 않는다. 작업 루트는 `/home/mu-01/patrol` 하나다.

### 다른 컴퓨터로 옮기기 전 확인 순서

1. 이전 컴퓨터에서 저장소·브랜치·HEAD·변경 파일을 확인한다.

```bash
cd ~/patrol
git rev-parse --show-toplevel
git branch --show-current
git log -1 --oneline
git status --short --branch
```

첫 명령은 실제 저장소 루트, 두 번째는 브랜치, 세 번째는 마지막 커밋, 네 번째는 원격 차이와 미커밋·미추적 파일을 보여 준다. 현재 예상값은 루트 `/home/mu-01/patrol`, 브랜치 `feat/amr-safety-status`, HEAD `0efa7fa`, 원격보다 `ahead 29`이며, 미커밋 변경은 이 문서뿐이다.

2. 변경 내용에 공백 오류가 없는지 확인한다.

```bash
git diff --check
git diff --stat
```

첫 명령은 잘못된 공백이 없으면 아무것도 출력하지 않는다. 두 번째는 추적 중인 수정 파일의 변경량을 요약한다. `git diff --stat`에는 새 미추적 파일이 나타나지 않으므로 반드시 앞 단계의 `git status`도 함께 본다.

3. 1~10단계 코드는 `9eb151f`까지 커밋·push가 끝났다. 새 커밋을 더 쌓으면 push한 뒤 이 절의 해시를 갱신한다.

4. 새 컴퓨터에서는 다음 3절의 clone·브랜치 전환 순서를 실행한다. 미push 커밋이 남아 있으면 그것부터 push한다.

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

for name in MissionCommand CommandCheck DriveToken RobotStatus PatrolReport EStop
do
  echo "===== $name ====="
  ros2 interface show patrol_interfaces/msg/$name
done
```

예상 결과는 `1 package finished`, `~/patrol/install/patrol_interfaces` 경로, 메시지 6종의 필드 출력이다. `Unknown package`가 나오면 현재 경로·브랜치·빌드 결과와 `source install/local_setup.bash` 실행 여부를 확인한다.

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
source install/local_setup.bash
ros2 run patrol_amr battery_monitor
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

- `observe(control_session_id, token_id, holder_robot_id, lease_seconds, message_sequence, now)`가 수락·폐기 사유를 `TokenVerdict`로 반환한다. 폐기 사유에는 `OTHER_HOLDER`, `REVOKED`, `STALE_CONTROL_SESSION`, `STALE_MESSAGE_SEQUENCE`, `INVALID_LEASE`가 있다.
- `authority(now)`가 `GRANTED`·`MISSING`·`EXPIRED`를 반환한다. 각각 600 DRIVE_TOKEN_MISSING, 601 DRIVE_TOKEN_EXPIRED에 대응한다.
- 같은 `control_session_id`에서는 token ID가 바뀌어도 message sequence 하한을 유지하고, 새 control session에서만 하한을 다시 시작한다. 경과 판정은 호출자가 넘기는 로컬 monotonic 초만 사용하며 폐기된 메시지는 lease를 연장하지 않는다.

단위시험:

```bash
cd ~/patrol
python3 -m unittest discover -s tests -p test_drive_token_guard.py -v
```

예상 결과는 `Ran 19 tests`와 `OK`다. 배터리와 함께 실행하면 현재 합계는 26개다.

이 모듈은 ROS 토픽 시험 대상이 아니다. 실제 `/control/drive_token` 구독과 정지 출력은 6단계에서 붙인다. 상세 설계와 TBD-IF-002로 남긴 부분은 [amr.md 3.1절](../amr.md#31-drive_token_guardpy--구현-대조-완료)에 있다.

## 6.2 4단계 구현 내용

`src/patrol_amr/patrol_amr/estop_guard.py`는 3단계와 같이 일반 Python 모듈이며 6단계 `local_safety_supervisor`가 사용한다. `/control/estop` 관측을 반영만 하고 속도를 발행하지 않는다.

- `EStopGuard(robot_id)`가 로봇 대상을 먼저 고정하고, `observe(target_robot_id, active, reason, latched, sequence)`가 `ACCEPTED`/`OTHER_TARGET`/`STALE_SEQUENCE`를 반환한다.
- 자기 로봇 대상의 `active`·`reason`·`latched`만 반영한다. `stopped`는 `active or latched`라 latch가 남아 있으면 active=false여도 정지를 유지한다. 다른 로봇 대상 메시지는 공통 stream sequence만 기억하고 상태에는 적용하지 않는다.
- 관측 전 기본 상태는 정지다. reason 숫자와 전체 대상 문자열, 물리 E-stop의 로컬 reset API는 TBD-IF-004라 추측하지 않았다. 상세는 [amr.md 3.2절](../amr.md#32-estop_guardpy--구현-대조-완료)에 있다.

단위시험:

```bash
cd ~/patrol
python3 -m unittest discover -s tests -p test_estop_guard.py -v
```

예상 결과는 `Ran 10 tests`와 `OK`다. 배터리·DriveToken·E-stop 합계는 36개다.

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

예상 결과는 `Ran 13 tests`와 `OK`다. 2~5단계 합계는 49개다.

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

첫 명령은 저장소 루트로 이동하고, 두 번째 명령은 ROS 그래프 없이 `SafetyGate`의 조합 규칙과 E-stop 해제 로그 선택을 시험한다. 예상 결과는 `Ran 14 tests`와 `OK`다. 2~6단계 합계는 63개다.

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
- 브랜치는 `feat/amr-safety-status`여야 한다. 현재 로컬 HEAD는 `0efa7fa`이며 1~9단계 코드가 여기에 모두 들어가 있다. 다른 컴퓨터에서는 1절의 push가 끝난 뒤 이 해시를 확인하고 시험한다. `main`이 나오면 6단계 시험 대상이 아니다.

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
ros2 run patrol_amr local_safety_supervisor --ros-args -p robot_id:=robot1
```

- 9단계에서 `setup.py`와 entry point를 등록했으므로 `ros2 run`으로 실행한다. 파일 직접 실행은 패키지 import로 바뀌어 더 이상 동작하지 않는다.
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
  "{target_robot_id: 'robot1', active: false, reason: 0, latched: false, sequence: 1}"
```

- `--once`는 시험 메시지 하나만 발행하고 종료한다.
- `active: false`는 관제가 E-stop 해제 상태를 알렸다는 뜻이다. AMR이 자체적으로 해제를 결정한다는 뜻은 아니다.
- 아직 DriveToken이 없으므로 `motion_allowed`는 계속 `false`다. 다만 수락된 관측이 최초 안전 기본값 `active=true`에서 `false`로 바뀌었으므로, 터미널 1에는 `E_STOP_AUTO_RELEASED robot_id=robot1 target_robot_id='robot1' sequence=1` 로그가 나와야 한다. 같은 상태를 반복하거나 낮은·동일 sequence가 폐기되면 이 로그를 다시 남기지 않는다.

#### 4. 터미널 3 — 3초 DriveToken 입력과 lease 만료 확인

같은 터미널 3에서 이어서 실행한다.

```bash
ros2 topic pub --once \
  --qos-reliability best_effort \
  --qos-durability volatile \
  /control/drive_token patrol_interfaces/msg/DriveToken \
  "{control_session_id: 'ctrl-video-test', token_id: 'tok-video-test-robot1-0001', holder_robot_id: 'robot1', lease_duration: {sec: 3, nanosec: 0}, message_sequence: 1}"
```

- `holder_robot_id: robot1`은 터미널 1의 `robot_id` 파라미터와 일치해야 한다.
- `lease_duration`은 이 권한의 유효시간을 3초로 지정한다.
- 이 메시지가 수락되면 터미널 2에 `data: true`, 약 3초 뒤 새 메시지 없이 `data: false`가 차례로 나와야 한다.
- 터미널 1에는 `motion allowed: True blocked_reasons: []` 뒤에 `motion allowed: False blocked_reasons: ['drive_token_not_granted']`가 나와야 한다.

#### 5. 선택 시험 — E-stop의 즉시 차단과 해제 반영

먼저 E-stop을 시험할 시간을 확보하도록 30초짜리 새 token을 준다. 같은 control session에서는 token ID가 바뀌어도 `message_sequence`를 계속 증가시켜야 한다.

```bash
ros2 topic pub --once \
  --qos-reliability best_effort \
  --qos-durability volatile \
  /control/drive_token patrol_interfaces/msg/DriveToken \
  "{control_session_id: 'ctrl-video-test', token_id: 'tok-video-test-robot1-0002', holder_robot_id: 'robot1', lease_duration: {sec: 30, nanosec: 0}, message_sequence: 2}"
```

`data: true`를 확인한 뒤 E-stop을 활성화한다.

```bash
ros2 topic pub --once \
  --qos-durability transient_local \
  --qos-reliability reliable \
  /control/estop patrol_interfaces/msg/EStop \
  "{target_robot_id: 'robot1', active: true, reason: 2, latched: false, sequence: 2}"
```

즉시 `data: false`가 나와야 한다. 이어서 더 큰 sequence로 관제의 해제 상태를 전달한다.

```bash
ros2 topic pub --once \
  --qos-durability transient_local \
  --qos-reliability reliable \
  /control/estop patrol_interfaces/msg/EStop \
  "{target_robot_id: 'robot1', active: false, reason: 0, latched: false, sequence: 3}"
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
- DriveToken을 `-r 5`로 발행하면서 동일한 YAML과 동일한 `message_sequence`를 반복하면 첫 메시지 외에는 재수신으로 폐기되어 lease도 연장되지 않는다. 실제 관제 발행자는 같은 `control_session_id` 안에서 매번 message sequence를 증가시켜야 한다. 새 control session에서만 1부터 다시 시작한다.
- E-stop도 마지막 수락 sequence 이하의 메시지는 폐기한다. 상태를 바꿀 때마다 `1 → 2 → 3`처럼 증가시킨다.

## 6.5 7단계 구현 내용과 시험 순서

`src/patrol_amr/patrol_amr/robot_status_state.py`는 8단계 `status_reporter`가 방송할 내용을 미리 정리하는 **로봇 상태 메모장**이다. ROS 노드가 아니므로 터미널 여러 개나 `ros2 topic` 명령은 필요 없다.

- 상태를 `operational_state`, `mission_state`, `docking_state`, `battery_state`, `safety_state` 다섯 칸으로 따로 보관한다. 예를 들어 “이동 중”과 “순찰 중”을 하나의 상태로 합치지 않는다.
- 시작할 때는 운행 상태 UNKNOWN, 임무 NONE, 도킹 UNKNOWN, 배터리 UNKNOWN, 현재 위치 무효다. 아직 받은 정보가 없는데 READY라고 거짓 보고하지 않는 안전한 초기값이다.
- `update_states()`는 값이 실제로 달라졌을 때만 `revision`을 올린다. 이 값은 다음 단계가 “상태가 바뀌었으니 즉시 방송할까?”를 판단할 때 쓰는 내부 번호다.
- `observe_pose()`는 유효한 현재 위치를 받으면 마지막 유효 위치도 함께 저장한다. 이후 위치가 무효가 되어도 마지막 유효 위치는 남겨 복구 참고용으로 쓸 수 있게 한다. 단, `pose_valid=false`인 현재 위치를 주행 가능한 위치로 바꾸지는 않는다.
- `snapshot()`은 마지막 유효 위치가 몇 초 전 측정인지 계산하고, 호출자가 나중에 내용을 바꿔도 내부 메모장이 훼손되지 않도록 복사본을 반환한다.

### 새 interfaces.md 반영 확인

2026-09-07 사용자 요청으로 공용 `src/patrol_interfaces/msg/RobotStatus.msg`도 새 문서에 맞췄다.

| 새 interfaces.md | 반영한 RobotStatus.msg | 상태 |
|---|---|---|
| `operational_state` 등 5개 상태 축 | 같은 `_state` 필드명 | 완료 |
| `source_session_id`, `status_sequence` | 같은 필드명·uint64 | 완료 |
| `active_command_id`, `active_mission_id` | 같은 필드명 | 완료 |
| `accepted_token_id`, `token_valid` | 같은 필드명 | 완료 |
| `battery_soc`, `battery_timestamp` | 같은 필드명 | 완료 |
| string `current_waypoint_id`, `scan_state` | 같은 string 타입 | 필드 반영 완료, 상세 동작 TBD |
| `safety_state` | uint8 필드만 존재 | 이름 완료, enum 숫자 TBD-IF-003 |

이름·필드 동기화와 safety/scan의 의미 확정은 구분한다. 메시지는 빌드할 수 있고 8단계도 값을 전송할 수 있지만, safety 숫자별 뜻은 합의 전까지 해석하면 안 된다.

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

새 코드 때문에 기존 배터리·token·E-stop·motion·local safety가 깨지지 않았는지 함께 확인한다. 최신 인터페이스 이름 반영과 8단계 추가 후 전체 예상 결과는 `Ran 89 tests`와 `OK`다.

시행 순서는 **7단계 단독 시험 → 전체 회귀시험**이다. 첫 시험이 실패하면 전체 시험으로 넘어가지 말고 실패한 테스트 이름과 traceback부터 확인한다. 7단계는 ROS 통신 코드가 아니므로 사용자 수동 토픽 시험은 없고, 실제 `/robot1/robot_status` 확인은 8단계에서 진행한다.

## 6.6 8단계 구현 내용과 시험 순서

`src/patrol_amr/patrol_amr/status_reporter.py`는 7단계 상태 메모장을 `patrol_interfaces/msg/RobotStatus`로 바꿔 `/{robot}/robot_status`에 방송하는 ROS 노드다.

- `PublicationGate`: 처음에는 즉시 한 번, 이후 평상시는 0.5초마다(2 Hz), battery enum 변경은 직전 발행으로부터 최소 0.1초 뒤(최대 10 Hz)에 발행한다.
- `StatusSequence`: 프로세스가 시작될 때 0에서 준비하고 실제 메시지마다 `1, 2, 3...`으로 증가시킨다.
- `battery_status`를 구독해 `battery_state`를 갱신하고, 원본 `battery_state`에서 유효한 `battery_soc`와 센서 timestamp를 보존한다.
- `robot_id`, `source_session_id`, `safety_state`는 필수 parameter다. safety enum 숫자가 TBD라 기본값을 몰래 넣지 않고, 실행자가 시험 또는 합의된 값을 명시해야 한다.
- mission·docking·위치 유효성·odometry·accepted token의 내부 입력 토픽은 아직 계약이 없다. 따라서 현재는 UNKNOWN/빈 ID/false로 내고 속도와 미수신 SOC는 NaN으로 표시한다. 이 부분은 “완료된 실제 로봇 전체 상태”가 아니라 확정 입력만 연결한 8단계 축소 범위다.

### 8단계 단위시험

1. 저장소 루트로 이동한다.

```bash
cd ~/patrol
```

2. 8단계 시간·설정·sequence 로직만 시험한다.

```bash
python3 -m unittest discover -s tests -p test_status_reporter.py -v
```

예상 결과는 `Ran 9 tests`와 `OK`다. ROS 그래프 없이 2 Hz/10 Hz 제한, 필수 parameter 검증, status sequence를 검사한다.

3. 전체 회귀시험을 실행한다.

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

예상 결과는 `Ran 89 tests`와 `OK`다.

### 8단계 사용자 ROS 토픽 시험

시행 순서는 **공용 메시지 빌드 → 터미널 1 battery_monitor → 터미널 2 status_reporter → 터미널 3 echo → 터미널 4 배터리 입력**이다.

#### 0. 공용 메시지 빌드

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
colcon build --packages-select patrol_interfaces
source install/local_setup.bash
ros2 interface show patrol_interfaces/msg/RobotStatus
```

새 `_state` 이름과 `source_session_id`, `status_sequence`, `battery_soc` 등이 보이면 준비 완료다. 예전 `operational`, `mission`, `token` 필드가 보이면 overlay를 다시 source해야 한다.

#### 1. 터미널 1 — 배터리 상태 변환 노드

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
ros2 run patrol_amr battery_monitor
```

원본 배터리 입력을 3초 규칙에 따라 내부 `battery_status`로 바꾼다. 시험이 끝날 때까지 켜 둔다.

#### 2. 터미널 2 — status_reporter 실행

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
ros2 run patrol_amr status_reporter \
  --ros-args \
  -p robot_id:=robot1 \
  -p source_session_id:=robot1-20260907T200000 \
  -p safety_state:=0
```

- `robot_id`는 출력 토픽을 `/robot1/robot_status`로 정한다.
- `source_session_id`는 이번 reporter 실행을 구분한다. 재시작할 때 값을 바꾼다.
- `safety_state:=0`은 이번 단계에서 **전송만 확인하는 임시 시험 숫자**다. 아직 `0=UNKNOWN`이라고 팀 계약을 확정한 것이 아니다.
- 예상 시작 로그는 `status reporter ready: robot_id=robot1 ...`이다.

#### 3. 터미널 3 — RobotStatus 연속 관찰

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
ros2 topic echo --no-daemon \
  --qos-reliability reliable \
  --qos-durability volatile \
  /robot1/robot_status patrol_interfaces/msg/RobotStatus
```

약 0.5초마다 메시지가 나오고 `status_sequence`가 계속 증가해야 한다. 최초에는 `operational_state: 0`, `mission_state: 0`, `docking_state: 0`, `battery_state: 0`, `pose_valid: false`, `token_valid: false`가 정상이다.

#### 4. 터미널 4 — LOW 배터리 입력

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
ros2 topic pub -r 10 --times 35 \
  /battery_state sensor_msgs/msg/BatteryState \
  "{percentage: 0.15, power_supply_status: 2, present: true}"
```

3초 연속 입력 후 터미널 1에는 `battery status: LOW`, 터미널 3의 RobotStatus에는 `battery_state: 2`와 `battery_soc: 0.15`가 보여야 한다. 발행 종료 후 배터리 입력이 3초 끊기면 `battery_state: 0`으로 돌아간다.

#### 5. 종료·통과 기준

터미널 1~3은 각각 `Ctrl+C`로 종료한다. 통과 기준은 다음과 같다.

- `/robot1/robot_status`가 약 2 Hz로 연속 출력됨
- `status_sequence`가 매 메시지 증가함
- 초기 `battery_state: 0`
- LOW 입력 3초 뒤 `battery_state: 2`, `battery_soc: 0.15`
- 입력 중단 뒤 `battery_state: 0`
- 새 필드 이름으로 출력되고 `AttributeError`가 없음

pose·실제 속도·motion_stopped·token·mission 필드는 이번 시험의 통과 대상이 아니다. 해당 내부 입력 계약을 정한 뒤 확장한다.

배터리 원본 입력이 끊겼을 때 `battery_monitor`가 내보내는 `battery_state`는 UNKNOWN(0)으로 돌아가지만, 현재 `status_reporter`에는 원본 SOC의 별도 stale timeout이 없다. 따라서 마지막 `battery_soc: 0.15`와 timestamp가 남을 수 있다. 이번 8단계 통과 기준은 `battery_state`의 `0 → 2 → 0` 전이이며, SOC stale 처리 정책은 계약 후 확장한다.

## 6.7 9단계 구현 내용과 확인 순서

`src/patrol_amr`를 ament_python 패키지로 만들어 세 노드를 `ros2 run`·`ros2 launch`로 실행할 수 있게 했다. 표준은 저장소에 이미 있는 `patrol_vision`을 따랐다.

추가한 파일은 다음과 같다.

| 파일 | 역할 |
|---|---|
| `package.xml` | 패키지 이름·의존성. `rclpy`, `std_msgs`, `sensor_msgs`, `builtin_interfaces`, `patrol_interfaces`, `launch`, `launch_ros`를 exec_depend로 선언한다 |
| `setup.py` | entry point 3개와 launch 파일 설치 |
| `setup.cfg` | 실행 파일을 `lib/patrol_amr`에 설치 |
| `resource/patrol_amr` | ament index 등록용 빈 표식 |
| `patrol_amr/__init__.py` | 디렉터리를 Python 패키지로 만든다 |
| `launch/amr_safety_status.launch.py` | 세 노드를 한 번에 실행 |

### import 방식 전환

`local_safety_supervisor.py`와 `status_reporter.py`는 `import robot_status_state as rss` 같은 평면 import를 썼다. 이는 파일을 직접 실행할 때 Python이 그 파일의 디렉터리를 `sys.path`에 넣어 주는 것에 의존한 방식이라, entry point로 설치하면 `ModuleNotFoundError`가 난다. 9단계에서 `from patrol_amr import ...` 형태로 바꿨다.

이에 따라 `tests/test_local_safety_supervisor.py`와 `tests/test_status_reporter.py`의 `sys.path` 대상도 `src/patrol_amr/patrol_amr`에서 패키지 루트 `src/patrol_amr`로 옮겼다. 나머지 시험 5개는 `importlib`로 파일 경로를 직접 읽고 대상 모듈이 서로를 import하지 않아 영향이 없다.

**대신 Python 파일 직접 실행은 더 이상 동작하지 않는다.** 2·6·8단계 시험 명령을 모두 `ros2 run` 기준으로 갱신했다.

### launch 파일의 필수 인자

`robot_id`, `source_session_id`, `safety_state` 세 인자에 기본값을 두지 않았다. `safety_state`의 enum 숫자는 TBD-IF-003으로 미정이라 임의의 기본값을 넣으면 계약을 지어내는 것이 되고, `source_session_id`는 실행마다 달라져야 하며, `robot_id`는 로봇마다 다르기 때문이다. 인자를 빼고 실행하면 launch가 어느 인자가 빠졌는지 알리고 종료한다.

노드의 상대 토픽은 2·6·8단계에서 검증한 루트 namespace 그대로 두었다. 한 ROS 도메인에서 robot1과 robot6을 동시에 띄우려면 namespace 또는 토픽 계약이 필요하나 아직 합의되지 않았으므로 여기서 정하지 않았다.

### 9단계 확인 순서

시행 순서는 **빌드 → entry point 조회 → 필수 인자 확인 → launch 통합 실행 → 배터리 입력**이다.

#### 0. 빌드

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
colcon build --packages-select patrol_interfaces patrol_amr
source install/local_setup.bash
```

예상 결과는 `2 packages finished`다.

#### 1. entry point 조회

```bash
ros2 pkg executables patrol_amr
```

`battery_monitor`, `local_safety_supervisor`, `status_reporter` 세 줄이 나와야 한다.

#### 2. 필수 인자 누락 확인

```bash
ros2 launch patrol_amr amr_safety_status.launch.py
```

`missing required argument 'robot_id'`로 끝나야 한다. 기본값을 몰래 채우지 않는다는 증거다.

#### 3. 터미널 1 — launch 통합 실행

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
ros2 launch patrol_amr amr_safety_status.launch.py \
  robot_id:=robot1 \
  source_session_id:=robot1-20260907T213000 \
  safety_state:=0
```

세 노드의 `process started`와 `status reporter ready: robot_id=robot1`이 보여야 한다. `ModuleNotFoundError`가 나오면 import 전환이나 빌드가 반영되지 않은 것이다.

#### 4. 터미널 2 — RobotStatus 관찰

터미널 1이 뜬 뒤 실행한다.

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
ros2 topic echo --no-daemon \
  --qos-reliability reliable \
  --qos-durability volatile \
  /robot1/robot_status patrol_interfaces/msg/RobotStatus
```

`source_session_id`에 launch에서 넘긴 값이 그대로 보여야 한다.

#### 5. 터미널 3 — LOW 배터리 입력

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
ros2 topic pub -r 10 --times 35 \
  /battery_state sensor_msgs/msg/BatteryState \
  "{percentage: 0.15, power_supply_status: 2, present: true}"
```

#### 6. 통과 기준

8단계와 같은 동작이 패키지 실행 형태에서도 재현되는지 본다.

- `ros2 pkg executables patrol_amr`에 세 노드가 나옴
- 필수 인자 누락 시 launch가 인자 이름을 알리고 종료함
- `ros2 launch`로 세 노드가 함께 뜨고 `ModuleNotFoundError`가 없음
- `/robot1/robot_status`의 `source_session_id`가 launch 인자와 일치함
- `battery_state`가 `0 → 2 → 0`으로 전이하고 `status_sequence`가 계속 증가함

2026-09-07 21:30 KST 자동 확인에서 위 다섯 항목이 모두 재현됐다. `battery_state`는 0에서 2를 거쳐 0으로 돌아왔고 `status_sequence`는 15에서 38까지 끊김 없이 증가했으며 `source_session_id`는 넘긴 값과 일치했다. 전체 회귀시험은 `Ran 89 tests`와 `OK`였다.


## 7. 결정·미완료 사항

TBD-AMR-003은 사용자의 권장안 승인으로 AMR 코드에 반영했으며 `docs/change_requests/CR-AMR_09-07_14-01_배터리_입력_정책.md`에 관제 검토를 요청했다. 실제 robot1·robot6 배터리 드라이버, 관제 연계, 도킹·교대 시험은 아직 수행하지 않았다.

9단계에서 `patrol_amr`에 `package.xml`, `setup.py`, `setup.cfg`, entry point 3개와 launch 1개를 추가했다. 따라서 `battery_monitor`, `local_safety_supervisor`, `status_reporter`는 모두 `ros2 run` 또는 `ros2 launch`로 실행한다. 패키지 import로 전환했으므로 Python 파일 직접 실행은 더 이상 동작하지 않는다. 이전 `final_turtlebot_ws`의 다른 실행 코드나 build/install/log 결과를 새 저장소로 복사하지 않는다.

`src/patrol_amr/.gitkeep`은 빈 디렉터리를 유지하려고 두었던 파일인데 9단계에서 실제 패키지 내용이 생겨 더 이상 필요하지 않다. 삭제는 기능과 관계없는 별도 정리로 남겼다. 10단계는 전체 시스템 통합이 아니라 현재 구현된 두 ROS 경로의 단일 robot 로컬 스모크로 범위를 확정했다.

작업 재개 전에 루트 `AGENTS.md`, `docs/architecture.md`, `docs/interfaces.md`, `docs/amr.md`를 확인한다. 기존 플로우차트는 설계 초안이며 확정 계약으로 사용하지 않는다. 다른 담당자의 변경과 미확정 TBD를 보존한다.

## 8. AMR Detection 구현 여부

2026-09-07 실제 소스·메시지·실행 등록·시험을 대조한 결과, **AMR OAK-D 기반 Detection은 설계만 있고 실행 코드는 구현되지 않았다.** [AMR Detection 설계](../amr.md#6-로컬-detection과-증적)에 있는 다음 흐름을 현재 구현 완료로 해석하지 않는다.

```text
지점 도착 → 90도 회전 → 객체 후보 감지 → 객체 방향으로 yaw 정렬
→ 1초 재탐지 → DetectionEvent 확정 → 이벤트·증적 발행
→ 부저/알람 → 원래 각도로 복귀
```

현재 AMR 쪽에 없는 항목은 다음과 같다.

- `DetectionCandidate.msg`, `DetectionEvent.msg`와 증적 메시지·토픽
- OAK-D 영상 구독, bbox/화재·이상 후보 생성 ROS 노드
- 후보 방향으로 yaw를 정렬하고 1초 동안 재탐지하는 상태 기계
- 확정 이벤트 ID 생성과 `DetectionEvent` 발행자
- 증적 생성·저장·전송·ACK·재전송
- 화재 부저/오디오 제어와 원래 회전각 복귀
- 위 동작의 launch 등록 및 단위·ROS 통합시험

`PatrolReport.msg`의 `FIRE_DETECTED=702`는 실패·상태 설명에 쓰는 reason code 상수일 뿐 감지 코드가 아니다. `RobotStatus.msg`의 `scan_state`도 문자열 필드만 존재하며 `status_reporter`가 감지 입력을 구독하거나 이 값을 채우지 않는다.

미구현 이유는 [interfaces.md](../interfaces.md)의 TBD-IF-006·007에서 Candidate/Event 필드·enum·토픽·QoS와 증적 전달·ACK·재전송 계약이 아직 정해지지 않았고, TBD-AMR-001·004에서 정렬·재탐지·부저 조건이 남아 있기 때문이다. 미정 값을 새로 지어내 구현하지 않는다. 이 계약들이 합의되기 전 AMR Detection 종단시험은 `BLOCKED`다.

별도 개발 단위인 PC 4의 `src/patrol_vision`에는 CCTV 차량 감지 코드가 있다. `gate_cam.py`는 차량의 선 통과를 재확인해 `/vision/cctv/gate_event`, `center_cam.py`는 주차·출차를 확인해 `/vision/cctv/center_event`, `cam_master.py`는 이를 검증해 `/vision/cctv/patrol_allowed`를 발행한다. 이는 차량 출입 상태용 `CameraState` 파이프라인이며 AMR의 화재·이상 Detection 구현으로 계산하지 않는다. 또한 현재 CCTV 코드는 모델 경로가 다른 PC에 고정돼 있고 저장소에 weight가 없으며 launch·기능시험도 없다.

8단계는 배터리 기반 `RobotStatus` 발행을 확인하는 축소 시험이므로 Detection 없이 진행할 수 있다. 8단계가 통과해도 Detection, 증적, 부저가 구현 또는 검증됐다는 뜻은 아니다.

## 9. 다음 작업 재개 순서

1. 현재 작업은 `9eb151f`까지 커밋·push가 끝났다. 새 컴퓨터에서는 2~4절 순서로 브랜치를 가져온다.
2. `colcon build --packages-select patrol_interfaces patrol_amr`로 두 패키지를 빌드한다.
3. 전체 회귀시험을 실행해 `Ran 89 tests`, `OK`를 확인한다.
4. 10단계 스모크를 실행해 `STAGE10_PASS`를 확인한다(10.1절의 명령 한 줄). 9단계 확인이 필요하면 6.7절 순서를 따른다.
5. 아래 10.2절의 재정리된 업무 범위와 차단 요인 구분을 확인한다. **다음 작업은 코드가 아니라 TBD 결정이다.**
6. AMR Detection은 8절의 TBD가 해소되고 별도 구현 승인을 받은 뒤 다룬다.

## 10. 재정리된 조정묵 작업 범위와 현재 상태

2026-09-07 사용자가 전달한 새 업무 분장을 기준으로 한다. 아래 상태는 **현재 `feat/amr-safety-status` 소스에서 직접 확인한 상태**다. 박성현 담당 코드가 다른 브랜치·컴퓨터에 있다는 보고는 현재 브랜치에 병합되기 전까지 `외부 구현 보고/현재 브랜치 미확인`으로 구분한다.

| 우선 | 조정묵 남은 항목 | 현재 상태 |
|---|---|---|
| 1 | `final_turtlebot_pkg` → `patrol_amr` 이관 방식 확정 | 이 브랜치는 `patrol_amr` 사용 완료. 박성현 launch·브랜치와 즉시 합의·병합 확인 필요 |
| 2 | 업무분장표의 I-02 패키지 등록 | 9단계 완료: package.xml·setup.py·entry point 3개·launch 등록. 아래 시스템 통합 I-02와 같은 이름인지 구분 필요 |
| 3 | cmd_vel 경로 확정(TBD-IF-009) | 미정·미구현. Nav2 출력 → local_safety_supervisor → 최종 발행 계약과 박성현 launch remap 합의 필요 |
| 4 | AMR-18·19 `recovery_supervisor.py` | 미착수. 현재 파일 없음. 박성현의 nav2_client·mission 코드가 현재 브랜치에 병합된 뒤 goal/spin 취소·30초 재개를 연결해야 함 |
| 5 | AMR-07 PatrolReport 발행 | 메시지 정의만 있음. publisher 없음. 박성현 체크포인트/mission 결과 입력과 연결 필요 |
| 6 | AMR-11 물리 E-stop latch | 부분 완료: 수신한 `latched`는 반영. 로컬 물리 latch·수동 reset 경로는 TBD-IF-004 해소 전 미구현 |
| 7 | I-03·T-01·T-03·T-04 | 전체 미실행. 이번 10단계는 구현된 배터리·token·E-stop 경로만 부분 검증 |

조정묵 목록에서 제외된 `nav2_client.py`(AMR-16)와 `command_store.py`(AMR-05)는 박성현 구현 완료 보고 항목이다. 두 파일은 현재 브랜치에는 없으므로 병합 전에는 로컬 완료로 판정하지 않는다. AMR-09 KeepoutFilter는 새 분장 설명과 시트 담당자가 충돌하므로 담당자를 확인하기 전 수정하지 않는다.

| 항목 | 현재 브랜치 기준 진행 상태 |
|---|---|
| AMR-03 | `patrol_interfaces` 구현·빌드 완료. 타 팀의 `parking_interfaces`와 명칭/계약 통합은 별도 확인 필요 |
| AMR-04 | token holder·session·sequence·monotonic lease 구현. 송신 timestamp message-age 검증은 미완료 |
| AMR-05 | 박성현 구현 완료 보고, 현재 브랜치에 `command_store.py` 없음 |
| AMR-06 | RobotStatus 2 Hz·변경 제한·배터리 연결 완료. pose/mission/docking/token/safety 실입력은 미연결 |
| AMR-07 | PatrolReport 메시지만 있고 발행 로직 미구현 |
| AMR-08~10 | 현재 AMR 브랜치에 좌표·Keepout·안전구역 실행 코드 없음. AMR-09 담당 충돌 확인 필요 |
| AMR-11 | E-stop active와 입력 latch 반영 완료, 물리 로컬 latch/reset·정지 품질은 미완료/TBD |
| AMR-12 | 7값 enum·SOC 밴드·3초 전이 구현 및 ROS 경로 검증 완료 |
| AMR-13 | 도킹 실행·성공 판정 미구현 |
| AMR-14 | Detection·증적·부저 미구현, TBD 때문에 BLOCKED |
| AMR-15 | robot6 LiDAR 위치 검증 미구현/TBD |
| AMR-16 | 박성현 구현 완료 보고, 현재 브랜치에 `nav2_client.py` 없음 |
| AMR-17 | 박성현 담당 실주행 검증 대기, 현재 브랜치에 순찰 실행 코드 없음 |
| AMR-18·19 | 조정묵 신규 담당, 미착수 |
| AMR-20 | heartbeat 타입 계약 TBD-IF-004로 BLOCKED |
| T-01 | AMR-03·04·06의 로컬 부분만 검증. 두 로봇/명령/pose/report/복구는 미실행 |
| T-02 | 박성현 범위, 미실행 |
| T-03 | token·비물리 E-stop의 `motion_allowed` 부분만 검증. 물리 latch·최종 cmd_vel은 미실행 |
| T-04 | 배터리 enum·stale 부분만 검증. 도킹·교대는 미실행 |
| T-05 | Detection 계약·구현 부재로 BLOCKED |
| I-01·02·03 | 전체 종단 통합은 선행 구현·팀 합의 전 NOT_RUN/BLOCKED |

### 10.1 10단계 로컬 ROS 통합 스모크 결과

검증 범위는 다음 두 경로뿐이다.

```text
/battery_state → battery_monitor → /battery_status
→ status_reporter → /robot1/robot_status

/control/estop + /control/drive_token
→ local_safety_supervisor → /motion_allowed
```

재현 스크립트는 `tests/integration/amr_safety_status_smoke.py`다. 실행 순서는 **두 패키지 빌드 → overlay source → 단위시험 89개 → 격리된 로컬 DDS 스모크**다.

```bash
cd ~/patrol
source /opt/ros/jazzy/setup.bash
colcon build --packages-select patrol_interfaces patrol_amr
source install/local_setup.bash
python3 -m unittest discover -s tests -p "test_*.py" -v
PYTHONDONTWRITEBYTECODE=1 PATROL_STAGE10_DOMAIN_ID=127 \
  python3 tests/integration/amr_safety_status_smoke.py
```

`PATROL_STAGE10_DOMAIN_ID=127`은 실제 로봇 도메인과 분리하기 위한 시험 프로세스 전용 값이며 시스템 설정을 바꾸지 않는다. 스크립트는 세 노드를 launch하고 QoS에 맞는 입력을 발행한 뒤 반드시 종료한다.

2026-09-07 21:49 KST 결과: 두 패키지 빌드 성공, 단위시험 `Ran 89 tests`/`OK`, 실제 DDS 스모크 `STAGE10_PASS`. `motion_allowed`는 `false → true → false → true → false`, `battery_state`는 `0 → 2 → 0`, RobotStatus는 20건을 받았고 `status_sequence`는 `3 → 22`로 증가했다.

이는 IT-03·04·11·13의 현재 구현 부분만 검증한 것이다. `motion_allowed`는 아직 RobotStatus의 safety/token 필드에 연결되지 않았고 최종 cmd_vel도 발행하지 않는다. heartbeat·mission·PatrolReport·pose/odom·도킹·교대·Detection·두 로봇·다중 PC 시험은 PASS로 선언하지 않는다.

### 10.2 다음 작업의 차단 요인 구분 — 2026-09-08

2026-09-08 사용자가 전달한 재정리 업무 분장의 조정묵 항목 7개를 **실제로 무엇이 막고 있는지**로 다시 분류했다. "TBD를 정해야 다음 작업이 된다"는 판단은 절반만 맞다. 세 종류가 섞여 있다.

| 우선 | 항목 | 실제 차단 요인 | 분류 |
|---|---|---|---|
| 1 | `final_turtlebot_pkg` → `patrol_amr` 이관 | TBD 아님. 이 브랜치는 이미 `patrol_amr`로 완료. 박성현 코드를 어디에 넣을지 **사람 합의**만 남음 | 합의 |
| 2 | I-02 패키지 등록 | 없음. 9단계에서 `package.xml`·`setup.py`·entry point 3개·launch 등록 완료 | 완료 |
| 3 | cmd_vel 경로 | **TBD-IF-009 OPEN** | TBD |
| 4 | AMR-18·19 `recovery_supervisor.py` | **TBD-AMR-005 OPEN**(STOP/CANCEL 차이·재개 지점) + `nav2_client.py` 미병합 | TBD + 병합 |
| 5 | AMR-07 PatrolReport 발행 | **TBD-IF-003 잔여**(waypoint·visit·scan 타입, safety enum 수치) + 박성현 체크포인트 입력 | TBD + 병합 |
| 6 | AMR-11 물리 E-stop latch | **TBD-IF-004 잔여**(수동 reset 요청 경로, reason enum) | TBD |
| 7 | I-03·T-01·T-03·T-04 | 위 항목들의 결과 | 후속 |

따라서 **2번은 이미 끝났고, 1번은 TBD가 아니며, 3~6번은 전부 TBD 결정이 선행되어야 한다.** 코드를 더 쓸 수 있는 지점이 사실상 없다.

병합 대기 항목의 근거다. 2026-09-08 `origin/main`·`origin/control`·`origin/feature/sysmon`·`origin/feature/vision` 네 브랜치를 모두 조회한 결과 `src/patrol_amr/` 아래에 `.gitkeep`밖에 없다. `nav2_client.py`·`command_store.py`는 **어느 원격 브랜치에도 없다.** 구현 완료 보고는 아직 이 저장소에 반영되지 않았다.

우선순위 3(TBD-IF-009)을 먼저 처리한 이유는 다음과 같다.

- 조정묵 항목 중 다른 사람의 코드 병합 없이 **혼자 제안까지 진행할 수 있는 유일한 TBD**다.
- 박성현 우선순위 7 "launch 통합"과 같은 지점을 가리킨다. 여기가 정해지지 않으면 양쪽 launch가 서로를 기다린다.
- 풀리면 `MotionGuard.evaluate()`가 실제 속도를 게이팅하게 되어 IT-16이 열리고, IT-04·IT-11의 "실제 정지" 확인도 가능해진다.

제안 내용은 [요청서](../change_requests/CR-AMR_09-08_08-31_최종_cmd_vel_경로와_주행_후보_토픽.md)에 있다. 요약하면 Nav2 Jazzy 표준 체인(`cmd_vel_nav` → `cmd_vel_smoothed` → `cmd_vel`)의 **끝단에만** `local_safety_supervisor`를 끼워 넣는 안이다. 박성현 launch의 변경은 `collision_monitor`의 `cmd_vel_out_topic`을 `cmd_vel` → `cmd_vel_safe`로 바꾸는 한 줄이며, 구동부가 구독하는 `cmd_vel` 이름은 그대로 유지되고 발행자만 바뀐다. 관제 회신이 필요한 질의 5개를 요청서 하단에 적었다.

미정 값을 새로 만들지 않는다는 규칙을 유지했다. 후보 신선도 timeout은 값을 확정하지 않고 Q-17 신설 요청으로 제시했으며, Nav2·yaw 후보 중재(TBD-AMR-001)와 속도 상한·감속(TBD-AMR-006)은 이 요청서 범위에서 제외했다.

### 10.3 TBD-IF-009 확정 내용 — 2026-09-08

사용자(조정묵)가 AMR 측 계약을 확정했다. 근거와 전문은 [요청서](../change_requests/CR-AMR_09-08_08-31_최종_cmd_vel_경로와_주행_후보_토픽.md)에 있다.

| 결정 | 내용 | 근거 |
|---|---|---|
| 체인 끝단 | `collision_monitor`를 남기고 그 `cmd_vel_out_topic`만 `cmd_vel` → `cmd_vel_safe`로 변경 | Nav2 표준 체인 유지, TBD-AMR-006 미정 상태에서 Nav2 장애물 정지 보존 |
| 최종 출력 | `/robotN/cmd_vel`, `geometry_msgs/msg/Twist` | 구동부 `diffdrive_controller`가 `use_stamped_vel: false` |
| 후보 입력 | `/robotN/cmd_vel_safe`, `/robotN/cmd_vel_yaw`, `geometry_msgs/msg/TwistStamped` | `enable_stamped_cmd_vel: true`. 같은 PC·같은 시계라 `header.stamp` 비교가 유효 |
| Q-17 후보 신선도 | 0.5초. 초과 시 최종 출력 `(0.0, 0.0)` | 구동부 `cmd_vel_timeout: 0.5`와 동일. 새 숫자를 만들지 않음 |
| QoS | `RELIABLE`·`VOLATILE`·`KEEP_LAST(1)`, 구독측 deadline·lifespan 미요청 | 6단계 DEADLINE 불일치 재발 방지 |
| `cmd_vel_yaw` 발행 주체 | 토픽·타입만 예약, 주체는 미정 | `mission_supervisor`가 저장소에 없고 조정묵 범위 밖 |

namespace 질의는 철회했다. [architecture.md 2절](../architecture.md)이 robot1 → `/robot1`, robot6 → `/robot6`을 명시하고 `ROS_DOMAIN_ID=6` 단일 도메인을 공유하므로, namespace 없이 Nav2를 띄우면 `/cmd_vel`·`/odom`·`/scan`·`/map`이 충돌하고 Keepout 경로도 성립하지 않는다. 새 결정이 아니라 확정 사항의 귀결이다.

## 11. 11단계 이후 실행 계획 — 2026-09-08

1~10단계와 같은 규칙을 유지한다. **한 단계마다 구현 → 시험을 끝내고, 사용자 통과 확인 전에는 다음 단계로 넘어가지 않는다.** 순수 Python 모듈은 단위시험까지, ROS 노드는 사용자 ROS 토픽 시험까지가 한 단계다.

| 단계 | 대상 | 시험 | 착수 가능 |
|---|---|---|---|
| 11 | `motion_guard.py`에 Q-17 후보 신선도 판정 추가 | 단위시험 | **완료 (2026-09-08)** |
| 12 | `local_safety_supervisor.py`에 후보 구독·최종 `cmd_vel` 발행 배선 | 단위시험 + 사용자 ROS 토픽 시험 | **지금 가능** |
| 13 | launch 인자 추가와 스모크 확장 | `ros2 launch` 통합 + 확장 스모크 | **지금 가능** |
| 14 | 실제 Nav2 후보와 연동해 IT-16 부분 실행 | 통합시험 | 관제 회신 + 박성현 launch 병합 후 |
| 15 | AMR-11 물리 E-stop latch·수동 reset | 단위 + 사용자 ROS 토픽 시험 | TBD-IF-004 잔여 해소 후 |
| 16 | AMR-18·19 `recovery_supervisor.py` | 단위 + 사용자 ROS 토픽 시험 | TBD-AMR-005 해소 + `nav2_client.py` 병합 후 |
| 17 | AMR-07 `PatrolReport` 발행 | 단위 + 사용자 ROS 토픽 시험 | TBD-IF-003 잔여 해소 + 박성현 체크포인트 병합 후 |
| 18 | I-03·T-01·T-03·T-04 | 통합시험 | 위 전부 완료 후 |

11~13단계는 관제 회신 없이도 진행한다. AMR 자기 코드만 바꾸고 Nav2 launch·params는 건드리지 않으므로, 회신이 늦어도 AMR 쪽 구현·시험은 끝내 둘 수 있다. 회신 결과가 다르면 토픽 이름 상수만 고치면 된다.

### 11단계 — `motion_guard.py` 후보 신선도 판정 · 완료 2026-09-08

구현 상세는 [amr.md 3.3절](../amr.md#33-motion_guardpy--구현-대조-완료)에 있다. 요약하면 다음과 같다.

- 게이트를 둘로 나눴다. `blocked_reasons()`는 **권한** 게이트(token·E-stop)로 그대로 두고, `evaluate()`만 **출력** 게이트로 후보 유무·신선도를 더한다. Nav2 후보가 있는지는 주행이 허용되는지와 다른 질문이라 합치지 않았다.
- `CANDIDATE_MAX_AGE_SECONDS = 0.5`(Q-17). 사유는 `CANDIDATE_MISSING`(한 번도 못 받음)과 `CANDIDATE_STALE`(받았으나 낡음)로 구분한다.
- `evaluate(drive_token_granted, estop_active, candidate, candidate_age)`로 인자가 4개가 됐다. `candidate`와 `candidate_age`는 짝으로만 받는다.
- 상태 비저장 원칙 유지 — age는 호출자가 재어 넘기므로 이 모듈에 시계가 없다.

**이 단계에서 노드가 깨지지 않은 이유**: `local_safety_supervisor`는 `blocked_reasons()`만 호출하고 `evaluate()`를 쓰지 않는다. `blocked_reasons()` 시그니처·동작을 건드리지 않았으므로 6단계 `motion_allowed`는 그대로다.

시험 결과 (2026-09-08):

- `tests/test_motion_guard.py` 26건. 경계값 0.499·0.5·0.501초, 후보 없음과 낡음의 사유 구분, 미래 stamp 통과, 세 사유 동시 보고, 권한 게이트가 후보 유무에 영향받지 않음, 짝 강제.
- 전체 단위시험 `Ran 102 tests` `OK` (11단계 전 89건 + 13건).
- 10단계 스모크 회귀 `STAGE10_PASS`. `motion_allowed`는 여전히 `false → true → false → true → false`다.
- 사용자 ROS 시험은 불필요하다. 순수 Python 모듈이며 ROS 경로 변화가 없다.

### 12단계 — `local_safety_supervisor.py` 배선

- 구현: `cmd_vel_safe`(TwistStamped) 구독, `cmd_vel`(Twist) 발행, `MotionGuard.evaluate()`를 실제 후보에 연결. `motion_allowed`는 시험·디버그용으로 남긴다. 기존 0.1초 신선도 타이머가 후보 stale 전이도 함께 처리한다.
- QoS: 후보·최종 모두 `RELIABLE`·`VOLATILE`·`KEEP_LAST(1)`. 구독측에서 deadline·lifespan을 요청하지 않는다.
- 시험: `SafetyGate` 단위시험 확장 + 사용자 ROS 토픽 시험. 터미널 순서는 ① `local_safety_supervisor` 실행 ② `cmd_vel` 연속 관찰 ③ E-stop 해제·DriveToken 입력 ④ 후보 발행·중단.
- 통과 기준: 후보가 변형 없이 통과, token 만료 시 `(0,0)`, E-stop 활성 시 `(0,0)`, 후보 중단 0.5초 후 `(0,0)`.

### 13단계 — launch·스모크 확장

- 구현: `amr_safety_status.launch.py`에 namespace·토픽 인자를 추가하고, `tests/integration/amr_safety_status_smoke.py`에 최종 `cmd_vel` 경로 검증을 넣는다.
- 시험: `ros2 launch` 통합 실행 + 확장 스모크.
- 통과 기준: 스모크 PASS와 함께 `ros2 topic info /robot1/cmd_vel -v`의 발행자가 `local_safety_supervisor` 하나뿐임을 확인한다. IT-16의 "최종 출력 발행권은 하나"를 로컬 범위에서 검증하는 것이며, 실제 Nav2 후보를 쓰는 IT-16 전체는 14단계다.

### 14단계 이후

15~17단계의 순서는 의존성이 적은 것부터다. AMR-11은 TBD 하나만 풀리면 되고 남의 코드가 필요 없다. AMR-18·19와 AMR-07은 TBD와 병합 두 가지가 모두 필요하다. 세 단계 모두 착수 전에 해당 TBD의 잔여 항목이 실제로 닫혔는지 [interfaces.md TBD 표](../interfaces.md#tbd)에서 확인하고, 미정 값을 지어내지 않는다.

## 12. 남은 작업의 노드·파일·기능 매핑 — 2026-09-08

11절의 단계 계획을 **어느 노드·파일의 어떤 기능인지**로 다시 정리했다. 아래 상태는 2026-09-08 `feat/amr-safety-status` 소스에서 직접 확인한 것이다.

### 12.1 ROS 노드

#### `local_safety_supervisor` (265줄) — 로컬 안전과 최종 속도 출력

| 구분 | 내용 |
|---|---|
| 현재 구독 | `/control/drive_token`(DriveToken), `/control/estop`(EStop) |
| 현재 발행 | `motion_allowed`(std_msgs/Bool) |
| 현재 타이머 | 0.1초 신선도 재확인 (`RECHECK_PERIOD_SECONDS`) |
| 필수 parameter | `robot_id` |

남은 기능은 두 가지다.

- **최종 속도 출력** — 12단계. `cmd_vel_safe`·`cmd_vel_yaw`(TwistStamped)를 구독하고 `MotionGuard.evaluate()`로 게이팅해 `/robotN/cmd_vel`(Twist)을 발행한다. 지금은 `blocked_reasons()`로 차단 여부만 판정하고 실제 속도를 다루지 않는다. `motion_allowed`는 시험·디버그용으로 남긴다.
- **물리 E-stop latch 반영** — 15단계. `estop_guard`의 로컬 latch 확장분을 이 노드가 사용한다. 현재는 관제가 보낸 `latched` 값을 반영할 뿐 로컬 물리 버튼 경로가 없다.

#### `status_reporter` (240줄) — 상태·결과 보고

| 구분 | 내용 |
|---|---|
| 현재 구독 | `battery_status`(내부), `/battery_state`(sensor_msgs/BatteryState) |
| 현재 발행 | `/robotN/robot_status`(RobotStatus) |
| 구현된 정책 | Q-02 정기 2 Hz·변경 시 최대 10 Hz, `status_sequence` 단조 증가 |
| 필수 parameter | `robot_id`, `source_session_id`, `safety_state` |

RobotStatus 27개 필드 중 **현재 안전한 미연결 값으로 두고 있는 것**이다. 코드에 `No agreed odometry/token/mission source is connected yet.`로 표시돼 있다.

| 필드 | 현재 값 | 연결하려면 |
|---|---|---|
| `linear_velocity`·`angular_velocity` | `NaN` | 12단계의 최종 cmd_vel 또는 odometry |
| `motion_stopped` | `false` | 12단계의 최종 cmd_vel |
| `accepted_token_id`·`token_valid` | `''`, `false` | `local_safety_supervisor`의 token 판정 |
| `operational_state`·`mission_state`·`docking_state` | `robot_status_state` 기본값 | 박성현 mission 코드 병합 |
| `pose`·`pose_valid`·`last_valid_pose` | 미입력 | AMCL·odom 구독, 박성현 Nav2 병합 |
| `current_waypoint_id`·`scan_state` | `''` | TBD-IF-003 잔여(타입 미정) |
| `safety_state` | parameter 고정값 | TBD-IF-003 잔여(enum 수치 미정) |
| `reason_code`·`reason` | 미설정 | 보고 정책 확정 후 |

추가로 **`PatrolReport` 발행(AMR-07)이 이 노드에 붙는다** — 17단계. 메시지 정의는 있으나 publisher가 없다. `/robotN/patrol_report`로 `result`(SUCCEEDED/FAILED/CANCELED)와 `reason_code` 32종을 명령·임무 ID에 연결해 발행해야 하며, 입력은 박성현 체크포인트·mission 결과다.

#### `battery_monitor` (208줄) — 배터리 분류

구독 `/battery_state`, 발행 `battery_status`, 0.1초 신선도 타이머. **AMR-12 범위는 완료됐고 남은 기능이 없다.** 7값 enum·SOC 밴드·3초 전이·stale 복귀까지 단위시험과 ROS 경로 검증을 마쳤다. 도킹 실행(AMR-13)과 교대(T-04)는 이 노드가 아니라 별도 미구현 영역이다.

#### `recovery_supervisor` — 파일 없음, 신규 (AMR-18·19)

새 분장에서 조정묵이 새로 받은 항목이다. 기능은 **중단 시 Nav2 goal·spin 취소, 30초 타이머, 재개, 토큰 반납**이다. 16단계이며 다음 두 가지가 모두 필요하다.

- `nav2_client.py`(박성현) 병합 — goal·spin을 취소할 대상 API가 저장소에 없다.
- TBD-AMR-005 해소 — STOP과 CANCEL의 임무 보존·종료 차이, 재개 지점이 미정이다.

**범위 확인 필요:** 이 문서 1절은 조정묵 범위를 "AMR Python 파일 7개, ROS 노드 3개"로 적고 있다. `recovery_supervisor`는 8번째 파일이며 Nav2 action client가 필요하므로 4번째 ROS 노드가 된다. 새 분장이 기존 범위를 넓힌 것이므로 착수 전에 확인한다.

### 12.2 순수 Python 모듈

ROS에 의존하지 않으며 위 노드들이 import해서 쓴다.

| 파일 | 줄 | 현재 기능 | 남은 기능 | 단계 |
|---|---|---|---|---|
| `drive_token_guard.py` | 201 | control session·token ID·message sequence·Q-01 lease 판정 | 송신 timestamp 기반 message age (TBD-IF-002 잔여, 현재는 QoS가 담당한다고 해석) | 없음 |
| `estop_guard.py` | 93 | 자기 `target_robot_id`의 active·reason·latched 반영, sequence 하한 | **물리 E-stop 로컬 latch와 수동 reset 경로** (TBD-IF-004 잔여) | 15 |
| `motion_guard.py` | 97 | token·E-stop AND 게이트, STOP=(0,0) 반환, 상태 비저장 | **Q-17 후보 신선도 0.5초 판정.** 속도 상한·감속·장애물은 TBD-AMR-006로 계속 BLOCKED | 11 |
| `robot_status_state.py` | 272 | operational·mission·docking 독립 상태 축, 현재·마지막 유효 pose snapshot | 실입력 연결(mission·docking·pose). 자료구조는 이미 있고 채워 줄 쪽이 없다 | 17 |

### 12.3 단계 → 노드·파일 대응

| 단계 | 노드·파일 | 기능 |
|---|---|---|
| 11 | `motion_guard.py` | Q-17 후보 신선도 판정 추가 |
| 12 | `local_safety_supervisor.py` | 후보 구독·최종 `cmd_vel` 발행 배선 |
| 13 | `launch/amr_safety_status.launch.py`, `tests/integration/amr_safety_status_smoke.py` | launch 인자 추가, 스모크에 최종 속도 경로 검증 |
| 14 | (변경 없음) | 실제 Nav2 후보로 IT-16 부분 실행 |
| 15 | `estop_guard.py` → `local_safety_supervisor.py` | 물리 latch·수동 reset |
| 16 | `recovery_supervisor.py` (신규) | goal·spin 취소, 30초 타이머, 재개, 토큰 반납 |
| 17 | `robot_status_state.py` → `status_reporter.py` | mission·pose 입력 연결, `PatrolReport` 발행 |
| 18 | (변경 없음) | I-03·T-01·T-03·T-04 통합시험 |

### 12.4 조정묵 범위 밖이거나 BLOCKED

| 항목 | 상태 |
|---|---|
| AMR-14 Detection·증적·부저 | 실행 코드 없음. TBD-IF-006·007, TBD-AMR-001·004로 BLOCKED (8절) |
| AMR-13 도킹 실행·성공 판정 | 미구현 |
| AMR-08~10 좌표·Keepout·안전구역 | 현재 브랜치에 실행 코드 없음. AMR-09는 담당자 충돌 확인 필요 |
| AMR-15 robot6 LiDAR 위치 검증 | 미구현/TBD |
| AMR-16 `nav2_client.py`, AMR-05 `command_store.py` | 박성현 구현 보고. 어느 원격 브랜치에도 없음 |
