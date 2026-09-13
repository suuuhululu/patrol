# patrol_amr

AMR 임무·Nav2 시나리오 패키지다. 최종 공용 계약은
[docs/interfaces.md](../../docs/interfaces.md)의 `patrol_interfaces 2.0.0`을 따른다.

## 최종 공용 연결

```text
Control Server
├── /{robot}/patrol_action       → AMR Action Server
├── /{robot}/patrol_command      → AMR Subscriber
└── /{robot}/drive_token         → local_safety_supervisor

AMR 감지 확정 측
└── /system_monitor/report_detection → System monitor Service Server
```

- Patrol Goal 수락 후 `WAITING_FOR_TOKEN`을 먼저 반환한다.
- 유효한 DriveToken 전에는 Nav2와 최종 속도 출력을 시작하지 않는다.
- 안전구역 이동과 재개는 실행 중인 Patrol Action 안에서 처리한다.
- 로컬 감지 상태는 Patrol Feedback으로 관제에 전달한다.
- AMR 제어와 감지 코드 사이에 별도 공용 감지 Action을 사용하지 않는다.
- EStop은 현재 구현하지 않는 예약 인터페이스다.

## 현재 상태

현재 소스 트리의 시나리오·launch·시험용 노드는 최종 Patrol Action Server와
DriveToken 소비 경로로 전환 중이다. `vision_node_v2.py`의 ReportDetection Client는
존재하지만 실제 시스템 모니터와 종단 검증이 필요하다. 자세한 전환 상태는
[AMR 기능 설계](../../docs/amr.md)를 따른다.

## 검증

```bash
colcon build --packages-select patrol_interfaces patrol_amr patrol_amr_safety
colcon test --packages-select patrol_amr patrol_amr_safety
colcon test-result --verbose
```

빌드와 단위시험만으로 실제 AMR 주행 완료를 선언하지 않는다.
