# AMR 순찰 시스템 개발 문서

> 기준일: 2026-09-13
>
> 공용 계약: `patrol_interfaces 2.0.0`
>
> 상태: 최종 인터페이스 확정 · 소비 코드 전환과 장비 통합시험 별도

두 AMR과 CCTV를 사용하는 ROS 2 순찰 시스템의 공용 설계 문서다. 통신 계약은
[interfaces.md](interfaces.md)가 유일한 기준이며, 실제 구현 상태와 시험 결과는
각 개발 단위 문서에서 구분해 기록한다.

## 문서 지도

| 문서 | 역할 |
|---|---|
| [AGENTS.md](../AGENTS.md) | 공용 개발 규칙과 책임 경계 |
| [architecture.md](architecture.md) | 시스템 구성, 로봇 식별, Discovery와 실행 환경 |
| [interfaces.md](interfaces.md) | 최종 Action·메시지·서비스·토픽 계약 |
| [scenarios.md](scenarios.md) | 공용 시나리오와 팀별 책임 |
| [integration.md](integration.md) | 통합 순서와 종단시험 |
| [amr.md](amr.md) | AMR 임무·Nav2·로컬 안전·감지 구현 상태 |
| [control_server.md](control_server.md) | 관제 판단과 코드 흐름 |
| [vision.md](vision.md) | CCTV 차량 상태와 `patrol_allowed` |
| [monitoring_and_data.md](monitoring_and_data.md) | 감지 보고 저장과 읽기 전용 모니터링 |
| [change_requests/README.md](change_requests/README.md) | 개발 단위 간 변경 요청 규칙 |

## 최종 공용 인터페이스

```text
action/Patrol.action
msg/CameraState.msg
msg/DetectionEvidence.msg
msg/DriveToken.msg
msg/EStop.msg
msg/MissionExecutionEvent.msg
msg/PatrolCommand.msg
srv/ReportDetection.srv
```

- 외부 순찰은 `Patrol` Action을 사용한다.
- 실행 중 안전구역 이동과 재개는 `PatrolCommand`를 사용한다.
- 주행 권한은 로봇별 `DriveToken`으로 관리한다.
- CCTV는 `CameraState`와 `std_msgs/Bool patrol_allowed`를 제공한다.
- 감지 진행·확정은 `Patrol` Feedback으로 관제에 전달한다.
- 확정 사건과 사진 저장은 `ReportDetection` Service를 사용한다.
- `EStop`은 타입과 토픽만 예약하며 현재 구현하지 않는다.
- AMR 제어와 로컬 감지 사이에 별도 공용 감지 Action은 없다.

## 책임 경계

- AMR: Patrol Action Server, Nav2 연결, 로컬 안전, 배터리·도킹, 로컬 감지
- 관제: Patrol Action Client, `PatrolCommand`, `DriveToken`, permit 기반 중재
- 비전: CCTV 차량 상태와 `patrol_allowed`
- 시스템 모니터: `ReportDetection` 저장과 읽기 전용 표시

관제와 시스템 모니터는 PC 3에서 함께 실행할 수 있지만 서로 다른 개발 단위다.
시스템 모니터는 운영 판단이나 주행 명령을 생성하지 않는다. 최종 속도 출력은
AMR의 `local_safety_supervisor`만 발행한다.

## 문서 적용 원칙

- 새 개발과 통합은 현재 `patrol_interfaces` 소스와 `interfaces.md`를 따른다.
- 과거 결정 문서, 변경 요청서, 개발 기록은 당시 상태를 설명하는 이력이다.
- 과거 문서와 현재 계약이 충돌하면 2026-09-13 최종 계약을 우선한다.
- 기존 소비 코드가 삭제된 타입을 사용하면 문서를 억지로 맞추지 않고 전환 필요로 기록한다.
- 네 팀은 같은 Git commit의 인터페이스 패키지를 빌드하고 manifest SHA-256을 비교한다.

## 환경 기준

- Ubuntu 24.04
- ROS 2 Jazzy
- Python 3.12
- Fast DDS
- `ROS_DOMAIN_ID=6`
- 로봇: `robot1`, `robot6`
- 기준 좌표계: `map`

실제 장비 주소, TB4 프로세스 배치와 다중 PC 통합 결과는
[architecture.md](architecture.md)와 [integration.md](integration.md)에서 관리한다.
