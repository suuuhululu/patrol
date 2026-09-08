# [AMR] patrol_interfaces 패키지명 통합

- 상태: 반영 중
- 최초 작성 시각: 2026-09-07 17:27 KST
- 요청자: 박성현
- 요청 단위: AMR
- 대상 단위 및 로봇: AMR 공용 인터페이스, robot1·robot6
- 관련 TBD ID: TBD-IF-001
- 기준 문서·절: `docs/interfaces.md`, `docs/amr.md` 1.2절
- 결정 일자·근거: 2026-09-07 `origin/main`과 `origin/feat/amr-safety-status`의 `src/patrol_interfaces` 및 실제 MissionCommand 토픽 시험 대조
- 코드 변경 승인 근거·범위: 2026-09-07 사용자 요청으로 공용 메시지 코드를 최신 문서에 맞게 수정하도록 명시 승인됨

## 변경 이유

변경 전 `origin/main`의 공용 패키지 경로와 ROS 패키지명은
`patrol_interfaces`지만 `CameraState.msg`만 포함했다. AMR 팀 브랜치의 같은 경로에는
`MissionCommand`, `DriveToken`, `RobotStatus`, `PatrolReport`, `EStop`이
있으나 `package.xml`의 이름과 `CMakeLists.txt`의 project가
`parking_interfaces`로 남아 있다. 이 상태로 병합하면 소비 코드의
`from patrol_interfaces.msg import MissionCommand`와 패키지 빌드 결과가
일치하지 않는다.

격리 작업공간에서 AMR 팀 브랜치 사본의 두 메타데이터를
`patrol_interfaces`로 맞춘 뒤 `final_turtlebot_pkg`와 함께 빌드하고,
`/robot6/mission_command`에 실제 생성 메시지를 발행했다. 구독 타입 확인과
mission supervisor 콜백 수신은 통과했다.

## 변경 전 → 변경 후

변경 전:

- main: 경로·패키지명 `patrol_interfaces`, `CameraState.msg` 보유
- AMR 팀 브랜치: 경로 `patrol_interfaces`, 선언된 패키지명
  `parking_interfaces`, AMR 메시지 5종 보유
- 미션 소비 코드: `patrol_interfaces/msg/MissionCommand` 사용

변경 후 제안:

- 하나의 `patrol_interfaces` 패키지에 `CameraState.msg`와 최신 공용 계약의
  MissionCommand·CommandCheck·DriveToken·EStop·RobotStatus·PatrolReport를
  함께 등록한다.
- `package.xml`의 `<name>`과 `CMakeLists.txt`의 `project()`를 모두
  `patrol_interfaces`로 통일한다.
- 메시지 소비 코드는 `patrol_interfaces`만 참조한다.

위 반영안은 현재 작업 브랜치에 구현했으며 공용 패키지 담당자의 검토와
병합이 필요하다.

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| AMR | main 최신 내용을 반영해 메시지 7종을 하나의 `patrol_interfaces`로 등록하고 패키지 메타데이터 통일 | `src/patrol_interfaces/package.xml`, `CMakeLists.txt`, `msg/` | 공용 인터페이스 담당 |
| 관제 | `patrol_interfaces` 패키지명과 MissionCommand 소비 경로 확인 | MissionCommand 송신 코드 | 관제 담당 |
| System monitor | 변경 불필요 여부 확인 | 공용 상태 메시지 소비 경로 | System monitor 담당 |
| 비전 | `CameraState.msg`가 병합 후에도 등록되는지 확인 | `src/patrol_interfaces/msg/CameraState.msg` | 비전 담당 |

## 영향과 적용 순서

공용 인터페이스 담당자가 main을 기준으로 메시지 파일과 빌드 등록을 먼저
통합한다. 각 소비 패키지는 새 공용 패키지를 빌드·source한 뒤 함께
재빌드한다. 혼합 상태에서는 동일 경로가 서로 다른 ROS 패키지명으로
인식되어 의존성 탐색과 메시지 import가 실패할 수 있다. 실패 시 공용
패키지 병합 전 브랜치로 되돌리고 미션 주행 게이트를 비활성 상태로
유지한다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | 반영 중 | 공용 메시지 7종 생성·빌드 PASS | 새 계약의 미션·안전·상태 송수신 코드 반영 |
| AMR / robot6 | 반영 중 | 공용 메시지 7종 생성·빌드 PASS | 새 계약의 미션·안전·상태 송수신 코드 반영·실환경 재시험 |
| 관제 | 미확인 | | 송신 코드의 패키지명 확인 |
| System monitor | 미확인 | | 메시지 소비 영향 확인 |
| 비전 | 일부 반영 | CameraState 새 식별 필드 생성과 비전 패키지 동시 빌드·import PASS | 비전 발행 노드의 source_session_id·source_sequence 값 생성 반영 |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: IT-02
- 추가 시험·기대 결과: 단일 `patrol_interfaces` 패키지에서 메시지 7종이
  생성되고 모든 소비 패키지가 빌드되며 robot1·robot6의
  `mission_command` 구독 타입이 동일해야 한다.
- 실제 실행 결과와 증거: 최신 공용 메시지 7종을 격리 작업공간에서 빌드하고
  `ros2 interface show`로 생성 결과를 확인했다. `patrol_interfaces`,
  `patrol_vision`, `final_turtlebot_pkg` 동시 빌드 PASS. 공용 패키지 lint 5건과
  최신 AMR 미션 단위시험 51건 PASS. 격리 ROS domain에서 구조화 command ID와 mission ID를
  포함한 MissionCommand pub/sub PASS
- 미실행 또는 BLOCKED 항목: 새 구조화 ID·mission_id·CommandCheck를 사용하는
  관제↔AMR 종단 시험, robot1·robot6 실환경 시험

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-07 | 박성현·AMR | 미션 소비 코드는 `patrol_interfaces`로 통일하고 공용 패키지 변경은 요청서로 분리 | 사용자 요청과 격리 ROS 토픽 시험 |
| 2026-09-07 | 박성현·AMR | 사용자 승인에 따라 최신 interfaces.md 필드로 공용 메시지 7종을 반영하고 격리 빌드·생성 검증 | 공용 패키지 테스트 5건과 의존 패키지 동시 빌드 |
