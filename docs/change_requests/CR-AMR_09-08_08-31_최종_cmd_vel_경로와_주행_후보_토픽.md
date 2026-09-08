# [AMR] 최종 cmd_vel 경로와 Nav2·yaw 주행 후보 토픽

- 상태: 합의 완료 · 코드 반영 중
- 최초 작성 시각: 2026-09-08 08:31 KST
- 요청자: 조정묵 (AMR)
- 요청 단위: AMR
- 대상 단위 및 로봇: 관제(Nav2 launch·remap 소유) / robot1·robot6
- 관련 TBD ID: TBD-IF-009(2026-09-08 결정). TBD-AMR-001(주행 중재)·TBD-AMR-006(로컬 정지·감속·장애물)은 이 요청으로 해결하지 않는다.
- 기준 문서·절: [interfaces.md 4절 토픽 트리](../interfaces.md#4-토픽-트리), [7절](../interfaces.md#7-keepout-parameter-api), [9절 Q-01](../interfaces.md#9-qos와-공통-시간거리-기준), [architecture.md](../architecture.md), [amr.md 2절·3.3·3.4절](../amr.md), [integration.md IT-16](../integration.md#4-통합시험-명세)
- 결정 일자·근거: 2026-09-08 AMR(조정묵)이 로컬 Jazzy 설치본 조사 결과를 근거로 AMR 측 안을 확정했다. 미션·내비게이션 담당 회신으로 TBD-IF-009를 결정했으며 세부 내용은 [확정 회신](CR-AMR_09-08_10-06_AMR_cmd_vel_계약_5개_확정_회신.md)에 기록한다.
- 코드 변경 승인 근거·범위: 2026-09-08 사용자가 AMR 측 계약을 확정했다. AMR 구현 범위는 `src/patrol_amr/patrol_amr/motion_guard.py`·`local_safety_supervisor.py`·`launch/amr_safety_status.launch.py`와 그 시험이다. Nav2 launch·params는 관제 담당이므로 AMR이 바꾸지 않는다.

## 변경 이유

5·6단계에서 `motion_guard.py`와 `local_safety_supervisor.py`를 구현할 때 최종 속도 출력 부분을 비워 두고 `motion_allowed`(`std_msgs/Bool`)만 발행했다. [amr.md 3.3·3.4절](../amr.md)에 기록한 대로 최종 토픽·타입이 TBD-IF-009라 추측해 구현하지 않았기 때문이다.

그 결과 현재 남은 문제는 다음과 같다.

1. `MotionGuard.evaluate()`가 받는 `candidate`는 `(linear, angular)` 실수 쌍이라는 임시 표현이고, 이를 실제로 채우는 구독자가 없다. 안전 게이트가 판정만 하고 속도를 실제로 차단하지 못한다.
2. 10단계 로컬 스모크(`tests/integration/amr_safety_status_smoke.py`)가 `motion_allowed`의 `false → true → false → true → false` 전이까지만 검증한다. [IT-16 최종 속도 경계](../integration.md#4-통합시험-명세)는 실행할 수 없다.
3. 박성현 담당의 Nav2 launch가 어느 토픽으로 속도를 내보내야 하는지 정해지지 않아, launch 통합(박성현 우선순위 7)과 AMR 안전 게이트가 서로를 기다린다.

interfaces.md 7절은 "local_safety_supervisor는 로봇별 최종 속도 출력의 유일한 발행자다. 전역 /cmd_vel을 두 로봇이 공유하도록 구성하지 않는다"까지만 확정했고, 실제 이름·타입·remap은 남겨 두었다.

### 로컬 Jazzy 설치본에서 확인한 사실

제안의 근거이며, 이 저장소의 계약이 아니라 설치된 상용 패키지의 동작이다. 확인 일자는 2026-09-08, 대상은 `/opt/ros/jazzy`다.

- `nav2_bringup/launch/navigation_launch.py`는 `controller_server`·`behavior_server`·`docking_server`의 `cmd_vel`을 전부 `cmd_vel_nav`로 remap한다.
- `nav2_bringup/params/nav2_params.yaml`의 `collision_monitor`는 `cmd_vel_in_topic: "cmd_vel_smoothed"`, `cmd_vel_out_topic: "cmd_vel"`이다.
- 따라서 Jazzy Nav2 표준 체인은 `cmd_vel_nav` → `velocity_smoother` → `cmd_vel_smoothed` → `collision_monitor` → `cmd_vel`이다.
- `nav2_util::TwistPublisher`는 기본으로 `geometry_msgs/msg/Twist`를 발행하고, 노드 parameter `enable_stamped_cmd_vel: true`일 때 `geometry_msgs/msg/TwistStamped`를 발행한다. 헤더 주석이 "기본은 하위 호환을 위해 Twist"라고 명시한다. `nav2_util::TwistSubscriber`는 두 타입을 모두 처리한다.
- `irobot_create_control/config/control.yaml`의 `diffdrive_controller`는 `use_stamped_vel: false`, `cmd_vel_timeout: 0.5`다. 구동부가 미stamped `Twist`를 기대한다는 뜻이다. 이 파일은 시뮬레이션 설정이므로 실기 확인이 필요하다.

## 변경 전 → 변경 후

공용 메시지(`patrol_interfaces`)는 추가·변경하지 않는다. 모두 표준 `geometry_msgs` 타입과 토픽 이름 결정이다.

### 결정 1 — Nav2 표준 체인의 끝단에만 삽입 (2026-09-08 AMR 확정)

로봇별 네임스페이스는 이미 확정된 `/robot1`·`/robot6` 규칙을 그대로 확장한다.

```text
Nav2 controller_server·behavior_server → /robotN/cmd_vel_nav       (Nav2 기본, 변경 없음)
  → velocity_smoother                  → /robotN/cmd_vel_smoothed  (Nav2 기본, 변경 없음)
  → collision_monitor                  → /robotN/cmd_vel_safe      ★ 여기만 변경
mission_supervisor yaw 정렬            → /robotN/cmd_vel_yaw       ★ 신규
  → local_safety_supervisor            → /robotN/cmd_vel           최종 출력, 구동부가 구독
```

| 항목 | 변경 전(미정) | 변경 후(AMR 확정) |
|---|---|---|
| Nav2 후보 입력 토픽 | 미정 | `/robotN/cmd_vel_safe` (collision_monitor의 `cmd_vel_out_topic`) |
| yaw 정렬 후보 입력 토픽 | 미정 | `/robotN/cmd_vel_yaw` |
| 최종 출력 토픽 | 미정 | `/robotN/cmd_vel` |
| 후보 입력 타입 | 미정 | `geometry_msgs/msg/TwistStamped` (`enable_stamped_cmd_vel: true`) |
| 최종 출력 타입 | 미정 | `geometry_msgs/msg/Twist` |
| Nav2 launch 변경량 | 미정 | `collision_monitor`의 `cmd_vel_out_topic`을 `cmd_vel` → `cmd_vel_safe` 한 줄 |

이 배치를 고른 이유다. `collision_monitor`를 체인에 남기는 쪽으로 확정했다.

- Nav2 내부 remap 3단을 손대지 않으므로 `nav2_bringup` 표준 launch를 거의 그대로 쓸 수 있다. 박성현 launch의 변경은 `cmd_vel_out_topic` 한 줄과 namespace 적용뿐이다.
- 구동부가 구독하는 이름 `cmd_vel`이 그대로 유지된다. 바뀌는 것은 발행자뿐(collision_monitor → local_safety_supervisor)이므로 TurtleBot4·Create 3 쪽 설정 변경이 없다.
- interfaces.md 7절의 "유일한 최종 발행자" 문장과 [IT-16](../integration.md#4-통합시험-명세)의 "최종 출력 발행권은 local_safety_supervisor 하나"가 구조적으로 성립한다. Nav2 어느 노드도 `cmd_vel`을 직접 발행하지 않는다.
- `collision_monitor`를 체인에 남겨 두면 Nav2의 장애물 정지가 후보 단계에서 이미 적용된다. TBD-AMR-006(로컬 정지 거리·감속)이 미정인 현재 상태에서 안전 방향으로 작동하며, TBD-AMR-006이 정해지면 local_safety_supervisor의 추가 판정을 그 위에 얹는다.

### 결정 2 — 후보는 TwistStamped, 최종 출력은 Twist (2026-09-08 AMR 확정)

후보 입력에만 `TwistStamped`를 쓰기로 확정했다.

- local_safety_supervisor가 후보의 신선도를 판정하려면 시각이 필요하다. `header.stamp` 없이는 Nav2가 죽어서 후보가 끊긴 것과 정지 명령을 구분할 수 없다.
- [DriveToken 요청서](CR-AMR_09-07_15-12_DriveToken_sequence_epoch와_holder_교체.md)에서 `header.stamp` age 검증을 보류한 이유는 PC 간 시계 동기가 보장되지 않아서였다. Nav2와 local_safety_supervisor는 **같은 AMR PC의 같은 시계**에서 돌기 때문에 그 이유가 여기에는 적용되지 않는다.
- Nav2 쪽 비용은 `enable_stamped_cmd_vel: true` parameter 하나다. `TwistPublisher`·`TwistSubscriber`가 공통으로 이 값을 읽으므로 `/**:` 블록에 한 번 넣으면 체인 전체가 일관되게 stamped로 동작한다.
- 최종 출력은 구동부 설정(`use_stamped_vel: false`)에 맞춰 미stamped `Twist`로 둔다. local_safety_supervisor가 stamped 후보를 받아 미stamped로 변환해 발행한다.

6단계 사용자 시험에서 겪은 DDS DEADLINE·DURABILITY 불일치([amr.md 3.4절](../amr.md))를 반복하지 않기 위해, 후보·최종 토픽의 QoS는 `RELIABLE`·`VOLATILE`·`KEEP_LAST(1)`을 제안하고 deadline·lifespan은 구독측에 걸지 않는다. Nav2 발행자가 명시하지 않는 정책을 구독측이 요구하면 메시지가 전혀 도달하지 않는다는 것을 이미 확인했다.

### 결정 3 — 후보 신선도 기준 Q-17 신설 요청 (2026-09-08 AMR 확정)

후보가 끊겼을 때 최종 출력을 정지로 내리는 기준이 필요하다. [amr.md 3절](../amr.md)이 임의 timeout 추가를 금지하므로, 새 숫자를 만들지 않고 이미 구동부가 쓰는 값에 맞췄다.

- **확정값: 0.5초.** 구동부 `diffdrive_controller`의 `cmd_vel_timeout: 0.5`와 같은 값이다. 후보의 `header.stamp` 기준 age가 0.5초를 넘으면 최종 출력을 `(0.0, 0.0)`으로 내린다.
- 검토한 대안: Nav2 `velocity_smoother`의 `velocity_timeout: 1.0`, Q-01 lease 1.0초. 구동부가 이미 0.5초에 자체 정지하므로 그보다 큰 값은 실효가 없다고 판단해 제외했다.
- 관제에는 [interfaces.md 9절](../interfaces.md#9-qos와-공통-시간거리-기준)에 **Q-17 후보 신선도**로 신설하는 것을 요청한다. 표 등재는 관제 회신 후에 한다.

### 결정하지 않은 것

이 요청서로 정하지 않으며 추측해 구현하지도 않는다.

- **Nav2 후보와 yaw 후보 사이의 중재**(둘이 동시에 올 때 무엇을 고르는가). TBD-AMR-001이며 `mission_supervisor` 담당이다. `local_safety_supervisor`는 중재하지 않고, 합의 전까지 후보 하나만 구독한다.
- 속도 상한·clamp·감속 프로파일·장애물 판정. TBD-AMR-006이다. `MotionGuard`는 지금처럼 통과 또는 `STOP=(0.0, 0.0)`만 한다.
- `/robotN` namespace를 Nav2 노드에 적용하는 **방식**(launch `namespace` 인자 대 topic prefix remap). namespace를 쓴다는 것 자체는 [architecture.md 2절](../architecture.md)에서 이미 확정됐고, 적용 방법만 박성현 launch 구조에 달려 있다.
- `/robotN/cmd_vel_yaw`의 **발행 주체**. 토픽 이름·타입만 계약에 예약하고 누가 발행하는지는 미정으로 둔다. `mission_supervisor`는 이 저장소에 없고 조정묵 작업 범위(AMR Python 7개·ROS 노드 3개) 밖이라, 근거 없이 배정하지 않는다.
- 실기 Create 3·TurtleBot4가 실제로 구독하는 토픽·타입. 위 확인은 시뮬레이션 설정 파일 기준이다.

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| AMR | 11~13단계로 구현. Q-17 신선도 판정 추가 → 후보 구독·최종 발행 배선 → launch·스모크 확장 | `src/patrol_amr/patrol_amr/motion_guard.py`, `local_safety_supervisor.py`, `launch/amr_safety_status.launch.py`, `tests/` | 조정묵 |
| 관제 | 아래 5개 질의 회신. Nav2 launch의 `cmd_vel_out_topic`·`enable_stamped_cmd_vel`·namespace 적용 | Nav2 bringup launch·params, `patrol_bringup/launch/` | 박성현 |
| System monitor | 해당 없음. 속도 토픽을 구독하지 않는다 | | |
| 비전 | 해당 없음. [Detection 정렬 요청](CR-관제_09-07_20-26_AMR_비전_Detection_정렬_계약.md)에서 detecting node가 속도를 발행하지 않는 것으로 이미 합의했다 | | |

AMR이 확정한 내용에 대해 관제 회신이 필요한 항목이다. 회신 전까지 AMR은 자기 코드만 구현하고 Nav2 설정은 건드리지 않는다.

1. 토픽 이름 3개(`cmd_vel_safe`·`cmd_vel_yaw`·`cmd_vel`)와 삽입 위치에 동의하는가. `collision_monitor`를 체인에 남기고 그 `cmd_vel_out_topic`만 바꾸는 방식에 동의하는가.
2. `enable_stamped_cmd_vel: true`를 Nav2 params에 적용해 줄 수 있는가. 적용이 어렵다면 후보 신선도 판정 수단을 다시 정해야 한다.
3. Q-17 후보 신선도 0.5초를 [interfaces.md 9절](../interfaces.md#9-qos와-공통-시간거리-기준)에 신설하는 데 동의하는가.
4. `/robotN` namespace를 Nav2 노드에 어떤 방식으로 적용하는가(launch `namespace` 인자 대 topic prefix remap). 적용 여부가 아니라 방식만 확인한다.
5. `/robotN/cmd_vel_yaw`를 누가 발행하는가. `mission_supervisor`가 맞다면 AMR-18·19 `recovery_supervisor`와의 소유 경계도 함께 확인한다.

**이미 확정되어 질의에서 제외한 것** — Nav2를 `/robot1`·`/robot6` namespace로 실행하는지 여부. [architecture.md 2절](../architecture.md)이 robot1 → `/robot1`, robot6 → `/robot6`을 namespace 열로 명시했고, `ROS_DOMAIN_ID=6` 단일 도메인을 두 로봇이 공유하며, [interfaces.md 7절](../interfaces.md#7-keepout-parameter-api)의 Keepout API가 이미 `/robot1/global_costmap/global_costmap`을 대상으로 한다. namespace 없이 실행하면 `/cmd_vel`·`/odom`·`/scan`·`/map`이 두 로봇 사이에서 충돌하고 Keepout 경로도 성립하지 않는다. 새 결정이 아니라 기존 확정 사항에서 따라 나오는 결론이다.

## 영향과 적용 순서

- 공용 메시지·enum·기존 토픽 계약을 바꾸지 않는다. `patrol_interfaces` 재빌드가 필요 없고 관제·System monitor·비전의 기존 구독은 영향을 받지 않는다.
- 합의 전까지 AMR은 현재 동작(`motion_allowed`만 발행)을 유지한다. 이 요청서만으로는 코드가 바뀌지 않으므로 혼합 버전 문제가 없다.
- 적용 순서는 **Nav2 launch의 `cmd_vel_out_topic` 변경과 local_safety_supervisor의 최종 발행 추가를 동시에** 해야 한다. 한쪽만 적용하면 `cmd_vel` 발행자가 없어(구동부 정지) 또는 둘(중복 발행) 상태가 된다. 전자는 안전 방향, 후자는 위험하므로 **local_safety_supervisor 발행 추가를 나중에** 한다.
- 되돌리려면 `cmd_vel_out_topic`을 `cmd_vel`로 되돌리고 local_safety_supervisor의 최종 발행을 제거한다. 저장 데이터·스키마 영향은 없다.
- 안전 영향: 적용 후 Nav2·yaw 후보가 안전 게이트를 통과해야만 구동부에 도달한다. token 만료·E-stop 활성 시 실제로 속도가 0이 되며, 현재처럼 `motion_allowed` 신호만 내리고 로봇이 계속 움직이는 상태가 사라진다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | 반영 완료, 실기 미확인 | `feat/amr-safety-status` 11~13단계. 사용자 ROS 토픽 시험 통과(2026-09-08) | 관제 회신 후 재확인, 로봇 실기, IT-16 |
| AMR / robot6 | 반영 완료, 실기 미확인 | 위와 같음. launch `robot_id:=robot6`으로 `/robot6` namespace 확인 | 위와 같음 |
| 관제 | 미반영 | | 위 5개 질의 회신, Nav2 params의 `cmd_vel_out_topic`·`enable_stamped_cmd_vel` 반영 |
| System monitor | 변경 불필요 | 속도 토픽 비구독 | |
| 비전 | 변경 불필요 | detecting node 속도 미발행으로 합의됨 | |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: [IT-16 최종 속도 경계](../integration.md#4-통합시험-명세). [IT-04 토큰 만료·회수](../integration.md#4-통합시험-명세)의 "실제 정지 조건"과 [IT-11 E-stop](../integration.md#4-통합시험-명세)도 최종 속도가 있어야 완결된다.
- 추가 시험·기대 결과: 후보 발행 중 token 만료 시 최종 `cmd_vel`이 `(0,0)`, E-stop 활성 시 즉시 `(0,0)`, 해제·유효 token 시 후보가 변형 없이 통과, 후보 단절 시 Q-17 기준으로 `(0,0)`, `cmd_vel` 발행자가 `local_safety_supervisor` 하나뿐임을 `ros2 topic info -v`로 확인.
- 실제 실행 결과와 증거: 2026-09-08 AMR 측 11~13단계를 구현하고 검증했다. 전체 단위시험 `Ran 114 tests` `OK`, 확장 스모크 `AMR_SMOKE_PASS`. `cmd_vel`은 `stop → candidate → stop_on_stale → stop_on_estop → candidate_after_release`로 전이했고, `/robot1/cmd_vel` 발행자는 `['local_safety_supervisor']` 하나였다. launch를 `robot_id:=robot6 candidate_topic:=/nav2/cmd_vel_out battery_state_topic:=/tb4/battery_state`로 실행해 namespace와 remap도 확인했다. **후보는 시험 스크립트가 발행한 것이며 실제 Nav2가 아니다.** 2026-09-08 사용자가 `ros2 run`으로 노드를 띄우고 손시험 절차를 수행해 통과를 확인했다.
- 미실행 또는 BLOCKED 항목: IT-16 전체(실제 Nav2 후보 필요), IT-04의 실제 정지 확인, IT-11의 물리 latch, 로봇 실기. 관제 회신과 Nav2 launch 병합 전까지 BLOCKED다. `cmd_vel_yaw`는 계약에만 예약했고 구독자가 없다.

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-08 08:31 | AMR | 제안 작성. 로컬 Jazzy 설치본의 Nav2 체인·TwistPublisher·Create 3 설정을 근거로 최소 변경안 제시 | 5·6단계에서 TBD-IF-009로 비워 둔 최종 출력이 IT-16과 launch 통합을 동시에 막고 있음 |
| 2026-09-08 09:10 | AMR | 4건 확정 — collision_monitor 유지, 후보 TwistStamped·최종 Twist, Q-17 0.5초, `cmd_vel_yaw`는 토픽만 예약. namespace 질의는 architecture.md 확정 사항이라 철회 | 사용자(조정묵) 결정. 근거는 각 결정 절에 기록 |
| 2026-09-08 | AMR | 확정 내용을 11~13단계로 구현·검증 완료. 관제 Nav2 설정은 건드리지 않았다 | 단위시험 114건 OK, 확장 스모크 `AMR_SMOKE_PASS`, 사용자 ROS 토픽 시험 통과 |
| 2026-09-08 10:06 | 박성현·AMR 미션·내비게이션 | 5개 질의 확정 회신 | [확정 회신](CR-AMR_09-08_10-06_AMR_cmd_vel_계약_5개_확정_회신.md) |
