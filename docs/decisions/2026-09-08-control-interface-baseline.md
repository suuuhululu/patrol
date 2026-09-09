# 관제 개발 인터페이스 v1.0 기준선

- 계약 버전: `v1.0`
- 기준선 ID: `CTRL-IF-2026-09-08`
- 상태: 현재 단계 계약 확정 · 로컬 소스·소비부 검증 완료 · 다중 PC 통합 검증 미실시
- 패키지 버전: `patrol_interfaces 1.0.0`
- 기준 소스: 이 문서와 함께 확정되는 v1.0 commit 및 메시지 manifest
- 결정 근거: [AMR 명령·Heartbeat·E-stop·상태 계약 확정 회신](../change_requests/CR-AMR_09-08_17-00_명령_Heartbeat_E-stop_상태_계약_확정_회신.md), [AMR 이중 Keepout parameter 계약](../change_requests/CR-AMR_09-08_13-02_이중_Keepout_parameter_계약.md), [TBD-IF-009 cmd_vel 확정](../change_requests/CR-AMR_09-08_08-31_최종_cmd_vel_경로와_주행_후보_토픽.md)

이 기준선은 관제 노드 개발에서 사용할 메시지 레이아웃과 확정 동작을 `v1.0`으로 고정한다. 아래 확정 범위만 v1.0 완료 조건이며 남은 TBD는 차기 버전으로 이관한다. 배포 릴리스나 장비 검증 완료를 뜻하지 않으며 Git release tag를 대신하지 않는다.

`patrol_interfaces 1.0.0`은 CMake에 등록된 15개 `.msg`의 wire schema를 하나의 배포 단위로 고정한다. 의미 계약의 일부가 차기 버전 TBD인 메시지도 v1.0에서 임의로 필드를 바꾸지 않는다. 네 팀은 같은 Git commit의 소스를 각 PC에서 빌드하고 `scripts/verify_interface_v1.py`가 출력하는 manifest SHA-256을 비교한다.

2026-09-08 로컬 빌드에서 소스 선언과 설치 Python 타입의 필드·상수가 일치했고, `message_manifest_sha256`은 `5db7945d3495d954c195935e96a499535f052578d6755be622cd3a223b6816d6`이다. 이 값은 주석·빈 줄을 제외하고 정규화한 메시지 15개의 wire 선언 식별자이며 Git commit을 대신하지 않는다. PC 1·2·4 설치 결과 비교와 실제 PC 간 DDS 통합시험은 아직 실행하지 않았다.

## 확정 범위

| 영역 | 이 기준선에서 고정하는 내용 |
|---|---|
| MissionCommand | command 0~5, 명령별 mission/target 조합, robot별 기본 patrol plan과 dock ID, `target_pose` 필드 유지·기본값 강제, `parameters_json` 제거 |
| CommandCheck | check_state 0~3, 정상·복구 예외·역방향 전이, ID 3종이 일치하는 `WAITING → EXECUTING` 수락과 즉시 재전송 중단, reason 203~206 |
| PatrolReport | 유효 ID의 최종 결과 수락, 중간 CommandCheck 누락 시 경고만 기록, `SAFE_ZONE_NOT_FOUND=400` 처리 |
| ControlHeartbeat | `header`, `control_session_id`, `uint64 sequence`, 5 Hz, AMR timeout 1초, BEST_EFFORT·VOLATILE·KEEP_LAST(3) |
| DriveToken | control session·token ID·message sequence 분리, 5 Hz·lease 1초, 빈 token ID 회수, 실제 정지 확인 후 holder 교대 |
| EStop | `target_robot_id`, `active`, 대표 `reason`, `sequence`; target은 `robot1`·`robot6`·`all`; reason 0~6; 대표 원인 우선순위 `SYSTEM_FAULT → UNKNOWN → OPERATOR → KEEPOUT_FAILURE → COMMUNICATION → OBSTACLE → TOKEN`; latch·manual reset·물리 E-stop 제외; 전체 원인 제거 3초 후 해제 |
| RobotStatus | safety_state 0~5와 의미, 실제 정지는 `motion_stopped`·속도·측정 age로 별도 확인 |
| Keepout | `base_keepout_filter.enabled=true` 상시 유지·관제 변경 금지, `center_corridor_keepout_filter.enabled`만 robot1·robot6 global/local costmap에서 transaction으로 변경 |
| 최종 속도 경로 | TBD-IF-009 해결: `/robotN/cmd_vel_safe`·`/robotN/cmd_vel_yaw`는 `TwistStamped`, `/robotN/cmd_vel`은 `Twist`; `local_safety_supervisor`가 최종 출력의 유일 발행자; Q-17 0.5초; namespace는 `robot_id`에서 파생; yaw 발행자는 `mission_supervisor` |
| 배터리·도킹 | SOC·충전 방향에 따른 `BatteryState` 분류와 도킹 성공용 충전 감지를 독립 판정; 도킹은 DOCKED 완료 센서+별도 충전 감지 신호 활성 2초 연속; `PATROL_READY`·`FULL`인 동안에도 충전 감지는 활성일 수 있음 |

START_PATROL의 `target_id`는 robot1=`robot1_default`, robot6=`robot6_default`다. DOCK은 robot1=`dock_1`, robot6=`dock_6`다. MOVE_TO_SAFE_ZONE은 target ID와 pose를 전달하지 않고 AMR이 안전구역 좌표를 계산한다.

## 차기 버전으로 이관한 미정 계약

- E-stop 원인별 활성·clear 조건
- E-stop TRANSIENT_LOCAL depth
- System monitor의 OPERATOR 정지·해제 요청 API
- 관제 전체 활성 원인 집합과 운영 이벤트의 공용 타입·토픽·QoS
- PatrolReport 수신 애플리케이션 ACK와 AMR 영속 큐 삭제 조건
- Keepout 상태 토픽, 탈출 경로 사전 검증과 대피 도착 보고 계약
- 도킹 완료 센서와 별도 충전 감지 신호의 출처·생성 기준, 화재 부저 제어자·해제 계약(TBD-AMR-004)
- timestamp 기반 DriveToken message age 검증

위 항목은 기존 TBD ID를 유지하며 v1.0 범위와 완료 조건에서 제외한다. 차기 버전에서 합의하기 전 임의로 채운 구현은 v1.0 준수로 인정하지 않는다.

## 기준 소스의 확인 필요 사항

- `src/patrol_interfaces/msg/RobotStatus.msg`의 `SAFETY_*` 상수는 v1.0에서 한 세트만 유지한다.
- `src/patrol_control`은 기준 소스에서 빈 패키지 자리만 존재한다. 관제 구현·시험 완료 상태로 해석하지 않는다.

## 변경·호환 규칙

1. 관제 구현은 이 기준선의 `patrol_interfaces`와 같은 wire 레이아웃을 사용한다.
2. `MissionCommand`, `ControlHeartbeat`, `EStop`의 구버전과 혼합 운영하지 않는다.
3. 이 확정 범위를 바꾸려면 영향 단위가 표시된 수정 요청서와 새 기준선 결정을 먼저 남긴다.
4. `v1.0`은 계약 문서 버전이다. 실제 배포 버전은 관련 코드 병합과 장비 검증 후 별도 Git tag로 기록한다.
5. 코드 반영·단위시험·통합시험 결과는 이 문서에 소급해 성공으로 기록하지 않고 각 기능 문서와 `integration.md`에 별도로 남긴다.
