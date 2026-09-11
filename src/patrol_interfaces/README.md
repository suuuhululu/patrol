# patrol_interfaces

기본 순찰 시나리오에서 AMR, 관제, CCTV 비전, 시스템 모니터가 공유하는 ROS 2 인터페이스 패키지다.

현재 인터페이스 버전은 `2.0.0`이다. 호환 기준과 필드 의미는 [공용 인터페이스 문서](../../docs/interfaces.md)를 따른다.

```text
patrol_interfaces/
├── action/
│   ├── Patrol.action
│   └── DetectEvent.action
├── msg/
│   ├── PatrolCommand.msg
│   ├── DriveToken.msg
│   ├── EStop.msg
│   ├── CameraState.msg
│   ├── DetectionEvidence.msg
│   └── MissionExecutionEvent.msg
└── srv/
    └── ReportDetection.srv
```

`EStop`은 타입과 토픽 이름만 예약하며 현재 기본 구현 범위에는 포함하지 않는다.

`MissionExecutionEvent`의 `RESULT_STORED` payload는 제거된 `PatrolReport`를
참조하지 않는다. 대신 `Patrol.action` Result의 `outcome`, `reason_code`,
`reason`을 `result_*` 필드에 평탄화해 전달한다.

각 PC는 같은 Git commit의 패키지를 빌드해야 한다. `2.0.0`은 이전 wire schema와 호환되지 않으므로 소비 노드를 함께 갱신하기 전에는 실제 통합 실행이나 주행시험을 하지 않는다.

소스와 설치 타입은 `python3 scripts/verify_interface_v1.py --installed`로 확인한다. 스크립트 파일명은 기존 실행 경로와의 호환을 위해 유지하며 검증 대상은 v2.0 계약이다.
