# [AMR] cmd_vel 계약 5개 확정 회신

- 상태: 합의 (AMR 내부 담당 간 회신 완료 · 코드 반영 중)
- 최초 작성 시각: 2026-09-08 10:06 KST
- 요청자: 박성현
- 요청 단위: AMR(미션·내비게이션)
- 대상 단위 및 로봇: AMR(로컬 안전·미션·내비게이션) / robot1·robot6
- 관련 TBD ID: TBD-IF-009, TBD-AMR-001
- 기준 문서·절: [interfaces.md 7절·9절](../interfaces.md), [architecture.md 2절](../architecture.md), [amr.md 2절·3.3·3.4절](../amr.md), [integration.md IT-16](../integration.md), [AMR 원 요청서](CR-AMR_09-08_08-31_최종_cmd_vel_경로와_주행_후보_토픽.md)
- 결정 일자·근거: 2026-09-08. AMR 요청서, ROS 2 Jazzy Nav2 표준 속도 체인, 로컬 TurtleBot4 `nav2.yaml`과 현재 미션·내비게이션 launch를 대조하여 확정했다.
- 코드 변경 승인 근거·범위: AMR 미션·내비게이션 담당 범위의 Nav2 launch·프로젝트 전용 params와 박성현 담당 `mission_supervisor` yaw 후보 발행 구조에 반영한다. 조정묵 담당 `local_safety_supervisor` 내부 구현은 임의 수정하지 않는다.

## 변경 이유

AMR 측 `local_safety_supervisor`는 DriveToken·E-stop·후보 신선도를 판정하고 최종 속도를 발행하도록 구현됐지만, 현재 관제 Nav2 launch는 TurtleBot4 기본 설정을 그대로 사용해 `collision_monitor`가 `cmd_vel`을 직접 발행한다. 이 상태에서는 최종 속도 발행자가 둘이 되거나 안전 게이트를 우회할 수 있다.

다섯 질의의 AMR 미션·내비게이션 담당 결정을 명시하여 Nav2 설정과 AMR 안전 노드를 같은 계약으로 연결한다. 이 합의는 최종 속도 경로를 확정하며, yaw 제어 수치와 두 후보 사이의 세부 중재는 TBD-AMR-001에서 계속 관리한다.

## 확정 회신

### 1. 토픽 이름과 삽입 위치

AMR 제안에 동의한다. 로봇별 최종 경로를 다음과 같이 고정한다.

```text
Nav2 controller·behavior·docking
  → /robotN/cmd_vel_nav
velocity_smoother
  → /robotN/cmd_vel_smoothed
collision_monitor
  → /robotN/cmd_vel_safe       geometry_msgs/msg/TwistStamped

mission_supervisor의 yaw 정렬 모듈
  → /robotN/cmd_vel_yaw        geometry_msgs/msg/TwistStamped

local_safety_supervisor
  → /robotN/cmd_vel            geometry_msgs/msg/Twist
Create 3 구동부
```

`collision_monitor`는 제거하지 않는다. `cmd_vel_out_topic`만 상대 이름 `cmd_vel`에서 `cmd_vel_safe`로 변경한다. `/robotN/cmd_vel`의 유일한 발행자는 `local_safety_supervisor`로 고정한다.

### 2. enable_stamped_cmd_vel 적용

적용 가능하며 `true`로 확정한다. 후보 구간인 Nav2 controller부터 `collision_monitor`까지 `TwistStamped`를 사용하고, `local_safety_supervisor`가 최종 출력에서 `Twist`로 변환한다.

현재 로컬 TurtleBot4 `config/nav2.yaml`은 관련 Nav2 노드에 이미 `enable_stamped_cmd_vel: true`가 설정돼 있다. 설치 워크스페이스 파일을 직접 수정하지 않고, 저장소의 프로젝트 전용 Nav2 params에도 이 값을 명시·유지한다.

### 3. Q-17 후보 신선도

Q-17을 0.5초로 신설하는 데 동의한다. `cmd_vel_safe` 또는 향후 중재된 yaw 후보의 `header.stamp`가 수신 시각 기준 0.5초를 초과하면 `local_safety_supervisor`가 최종 `/robotN/cmd_vel`에 0 속도를 발행한다.

0.5초는 Create 3 구동부의 기존 `cmd_vel_timeout`과 같아, 상위 안전 게이트와 구동부의 정지 기준이 어긋나지 않는다. 후보 유실은 주행 권한 회수와 구분하여 기록하되 출력은 정지로 한다.

### 4. /robotN namespace 적용 방식

launch namespace 방식으로 확정한다. `robot_id`를 단일 launch 인자로 받고 그 값에서 namespace를 파생한다.

- robot1: `robot_id=robot1`, namespace `/robot1`
- robot6: `robot_id=robot6`, namespace `/robot6`
- Nav2는 상위 `GroupAction`의 `PushRosNamespace(robot_id)`로 노드 namespace를 적용한다.
- 포함하는 `navigation_launch.py`에는 같은 namespace 값을 전달하여 `RewrittenYaml(root_key=namespace)`가 같은 로봇의 parameter 블록을 읽게 한다.
- 데이터 토픽은 `cmd_vel_safe`, `cmd_vel_yaw`, `cmd_vel`, `scan`, `odom`, `map`처럼 상대 이름을 사용한다. 토픽마다 `/robotN` 접두사를 수동으로 반복하지 않는다.
- 공용 관제 토픽 `/control/drive_token`과 `/control/estop`은 계약대로 절대 이름을 유지한다.

`PushRosNamespace`와 수동 `/robotN/...` prefix remap을 같은 토픽에 중복 적용하지 않는다. `robot_id`와 별도의 namespace 인자를 동시에 노출하지 않아 두 값이 어긋나는 설정도 차단한다.

### 5. cmd_vel_yaw 발행 주체

`/robotN/cmd_vel_yaw`의 유일한 발행 주체는 `mission_supervisor`로 확정한다. 비전팀 `detecting node`는 DetectionCandidate만 제공하고 속도를 발행하지 않는다.

파일 책임은 다음처럼 분리한다.

- `mission_supervisor`: 현재 mission·안전 상태에 따라 yaw 정렬 시작·중단·종료를 조정하고 `cmd_vel_yaw` publisher를 소유한다.
- `yaw_alignment_controller.py`: 오차에서 각속도 후보를 계산하는 ROS 비의존 로직을 담당한다.
- Detection callback 모듈: candidate ID·관측 갱신과 정렬 요청 전달만 담당한다.
- `recovery_supervisor`: 통신 단절·복구 시 goal과 yaw 정렬 취소를 요청하며 속도 후보나 최종 `cmd_vel`을 직접 발행하지 않는다.
- `local_safety_supervisor`: 선택된 후보에 DriveToken·E-stop·Q-17을 적용하고 최종 `cmd_vel`만 발행한다.

현재 W1~W7 순찰에는 yaw 후보를 사용하지 않는다. yaw publisher의 소유자만 이번 계약에서 확정하며, yaw 속도·오차·timeout과 Nav2/yaw 후보 전환 조건은 TBD-AMR-001 합의와 모의시험 후 활성화한다.

## 변경 전 → 변경 후

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| Nav2 안전 후보 | `collision_monitor → cmd_vel` | `collision_monitor → cmd_vel_safe` |
| 후보 메시지 | 경로별 미정 | `TwistStamped` |
| 최종 출력 | 발행 주체 충돌 가능 | `local_safety_supervisor → cmd_vel` (`Twist`) |
| 후보 신선도 | 미정 | Q-17, 0.5초 |
| namespace | 적용 여부만 확정 | `robot_id`에서 파생한 launch namespace |
| yaw 발행자 | 미정 | `mission_supervisor` |

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| AMR(미션·내비게이션) | 프로젝트 전용 Nav2 params에서 `cmd_vel_out_topic: cmd_vel_safe`와 stamped 설정 유지, robot_id 기반 namespace launch 적용 | `patrol_bringup/launch/`, Nav2 params | 박성현 |
| AMR | 본 회신을 원 요청서와 interfaces.md에 반영하고 관제 Nav2 후보와 결합 검증 | `patrol_amr`, `local_safety_supervisor` | 조정묵 |
| AMR·관제 | yaw 수치·timeout·후보 전환 조건을 TBD-AMR-001에서 후속 합의 | `mission_supervisor`, yaw 정렬 모듈 | 박성현·조정묵 |
| System monitor | 변경 없음. 속도 토픽 비구독 | 해당 없음 | 해당 없음 |
| 비전 | 변경 없음. detecting node는 속도를 발행하지 않음 | DetectionCandidate 제공 | 비전 |

## 영향과 적용 순서

1. `patrol_amr` 안전 노드가 포함된 팀원 브랜치를 관제 작업 브랜치와 통합한다.
2. 설치된 TurtleBot4 설정을 직접 수정하지 않고 프로젝트 전용 Nav2 params를 만든다.
3. Nav2 `collision_monitor` 출력을 `cmd_vel_safe`로 바꾼다.
4. `local_safety_supervisor`를 같은 robot namespace로 실행한다.
5. 무동작 상태에서 후보 통과·0.5초 stale·token 만료·E-stop 정지를 확인한다.
6. `/robotN/cmd_vel` publisher가 `local_safety_supervisor` 하나인지 확인한 뒤 실주행한다.

Nav2 remap만 먼저 적용하면 최종 속도 발행자가 없어 로봇이 정지한다. `local_safety_supervisor`만 먼저 연결하고 기존 `collision_monitor → cmd_vel`을 남기면 최종 발행자가 둘이 되므로 실제 주행을 금지한다. 두 설정을 같은 배포 단위로 적용한다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | AMR 코드 반영 완료, 관제 결합 전 | `feat/amr-safety-status` stage 11~13 | Nav2 결합·실기·IT-16 |
| AMR / robot6 | AMR 코드 반영 완료, 관제 결합 전 | `feat/amr-safety-status` stage 11~13 | Nav2 결합·실기·IT-16 |
| AMR 미션·내비게이션 | 계약 합의, 코드 반영 중 | 본 회신 | launch·params 빌드·실기 검증 |
| System monitor | 변경 불필요 | 속도 토픽 비구독 | 없음 |
| 비전 | 변경 불필요 | 속도 미발행 계약 | 없음 |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: IT-04, IT-11, IT-16
- `/robotN/cmd_vel_nav → cmd_vel_smoothed → cmd_vel_safe → cmd_vel`의 타입과 publisher/subscriber를 `ros2 topic info --verbose`로 확인한다.
- 후보가 유효하고 DriveToken이 있을 때 후보가 통과해야 한다.
- 후보가 0.5초보다 오래되거나 DriveToken이 만료되거나 E-stop이 활성화되면 최종 출력이 0이어야 한다.
- `/robotN/cmd_vel` publisher는 `local_safety_supervisor` 하나여야 한다.
- robot1·robot6 각각 namespace 충돌 없이 같은 시험을 통과해야 한다.
- 실제 실행 결과와 증거: 코드 반영 후 단위시험까지 완료했으며 실제 Nav2 후보·로봇 주행은 NOT_RUN
- 미실행 또는 BLOCKED 항목: 실제 Nav2 후보 결합과 robot1·robot6 실주행은 현장 검증 대기이며, yaw 중재는 TBD-AMR-001 후속 합의 전까지 BLOCKED

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-08 08:31 | 조정묵·AMR | 최종 속도 경로와 후보 토픽 제안 | Jazzy Nav2 표준 체인과 AMR 안전 노드 구현 |
| 2026-09-08 10:06 | 박성현·AMR 미션·내비게이션 | 질의 1~4 동의, yaw 발행자는 mission_supervisor로 확정 | 현재 Nav2 launch·TurtleBot4 params·시나리오 모듈 분리 원칙 대조 |
