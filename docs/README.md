# AMR 순찰 시스템 개발 문서

작성일: 2026-09-06 · 상태: v1.0 공용 계약 확정 · 차기 버전 TBD·장비 통합 별도 · 대상: AMR·관제·시스템 모니터·비전 전체 개발자

두 AMR이 CCTV 차량 상태와 관제의 주행 권한에 따라 순찰·대피·도킹·역할 교대를 수행하는 시스템이다. 이 문서는 설계 기준과 미정 계약을 관리한다. 구현 진행 상태는 각 개발 단위의 변경 기록과 시험 결과로 확인한다. 기존 결정은 유지하고 상세 계약이 부족한 부분은 각 문서의 TBD에 표시했다. 실제 시스템의 구현·배포·통합시험 완료를 의미하지 않는다.

## 문서 지도

~~~text
AGENTS.md
docs/
├── README.md
├── architecture.md
├── interfaces.md
├── scenarios.md
├── amr.md
├── control_server.md
├── vision.md
├── monitoring_and_data.md
├── integration.md
└── change_requests/
    └── README.md
~~~

| 문서 | 역할 |
|---|---|
| [AGENTS.md](../AGENTS.md) | 공용 개발 규칙·승인·개발 단위 경계 |
| [architecture.md](architecture.md) | 시스템 구성·PC 역할·로봇 식별·Discovery·실행 환경 |
| [interfaces.md](interfaces.md) | 메시지·토픽·enum·QoS·시간 정책·공용 계약 TBD |
| [scenarios.md](scenarios.md) | UC-01~08 액터·시나리오·팀별 책임·설계 flowchart |
| [amr.md](amr.md) | PC 1·2 임무·주행·안전·배터리·도킹·Detection |
| [control_server.md](control_server.md) | 관제 팀: 명령·권한·Keepout·교대·복구 판단 |
| [vision.md](vision.md) | PC 4 CCTV·차량 이벤트·patrol_allowed |
| [monitoring_and_data.md](monitoring_and_data.md) | 시스템 모니터 팀: 모니터링·이력·증적·읽기 전용 대시보드 |
| [integration.md](integration.md) | 기동·연결·정상 및 장애 흐름·통합시험 |
| [amr_patrol_safety_flowchart.md](amr_patrol_safety_flowchart.md) | `amr_patrol_safety` 담당 노드·내부 모듈·메시지 연결의 구현 전 설계 읽기본 |
| [change_requests/README.md](change_requests/README.md) | 개발 단위 간 수정 요청 양식·처리 상태 |
| [관제 인터페이스 v1.0](decisions/2026-09-08-control-interface-baseline.md) | 현재 단계 확정 계약과 차기 버전 이관 TBD |

## 설계 기준

[2026-09-07 PM 설계 결정](decisions/2026-09-07-design-baseline.md)에 따라 관제는 별도 노드, 시스템 모니터는 UI 전용으로 사용한다. 공용 메시지 패키지는 `patrol_interfaces 1.0.0`이다. 관제의 명령·Heartbeat·DriveToken·E-stop·RobotStatus·이중 Keepout 구현 입력은 [v1.0 (`CTRL-IF-2026-09-08`)](decisions/2026-09-08-control-interface-baseline.md)으로 고정한다. 남은 TBD는 v1.0 완료 조건에서 제외하고 차기 버전으로 이관한다. 네 팀은 같은 Git commit을 각 PC에서 로컬 빌드하고 공용 검증 스크립트의 manifest SHA-256을 비교한다. 최신 PM 결정과 System design의 확정 내용을 우선하며, 과거 문서의 TBD가 확정 사항을 대체하지 않는다. 진행표와 통합 일정은 PM이 별도로 수동 관리한다.

## 읽기 순서와 작성 원칙

모든 개발자는 AGENTS → architecture → interfaces를 먼저 읽는다. 이후 scenarios의 UC 흐름, 담당 기능 문서와 integration을 읽는다. AMR1·AMR2는 amr.md를 공유하며 식별자·설정 차이만 구분한다. 관제 팀은 control_server.md, 시스템 모니터 팀은 monitoring_and_data.md를 담당한다. 두 팀의 기능은 통합 실행 시 PC 3에서 함께 실행하지만 개발 책임은 독립적이다.

통신 이름·필드·enum·공통 시간값과 팀 간 공용 로그 전달 계약은 interfaces.md가 기준이다. 내부 DB·저장 스키마·인덱스·보존 정책은 monitoring_and_data.md에서 관리한다. 시스템 모니터는 토픽을 받아 표시하며, 관제와 모니터 사이의 운영 판단은 관제가 수행한다. 기능 문서는 처리 규칙을, integration.md는 여러 단위를 통과하는 순서와 시험을 설명한다. 값을 변경할 때 기준 문서와 참조 문서의 일관성을 함께 확인한다.

- **기준:** 제공 자료 또는 사용자가 명시한 결정. 구현 검증 완료라는 뜻은 아니다.
- **제안:** 문서에 제시된 구현·운영 초안. 기존 결정으로 승격하지 않는다.
- **TBD:** System design에서 확정되었는지 먼저 확인할 항목. 확정 내용이 있으면 낮은 버전의 미정 표기를 갱신하고, 원본도 미정인 경우에만 추가 정보를 확인한다. 본문 근처의 ID와 문서 끝 표를 참조한다.
- 미결 목록을 따로 복제하는 TBD 파일은 만들지 않는다. 요청서는 실제 공용 변경 결정 또는 타 단위 수정 필요가 있을 때 생성한다.

## 코드와 Flowchart 관리

네 팀 모두 동작 코드 파일·모듈별 Mermaid flowchart를 담당 기능 문서에 작성하고 코드 변경과 함께 갱신한다. 실제 코드 경로·진입 함수·분기·실패·취소·복구 경로와 구현 대조 버전을 기록한다. AMR은 [시나리오별 코드 분리 및 flowchart 규칙](amr.md#11-시나리오별-코드-분리와-개발-단위)을 따른다. Git에서 요청서 폴더를 공동 관리할 때의 충돌 처리는 [수정 요청서 규칙](change_requests/README.md#5-git-공동-관리와-충돌-처리)을 따른다.

## 참고 자료와 결정 기록

- 초기 작성 자료: interface_tree.md 1~17절. 해당 파일은 이 저장소에 포함되어 있지 않으므로 개발 기준은 이 문서 묶음에 기록된 내용과 TBD를 따른다.
- 노션 회의록(https://app.notion.com/p/FINAL_PROJECT-3d1cde0003cd801abc76ebcb31b15718)을 참고했다.
- 공용 개발 규칙은 AGENTS.md, Onboard/Offboard Discovery와 robot1·robot6 식별 체계는 architecture.md, 문서 구성은 위 문서 지도를 기준으로 한다.
- 기존 문서의 /amr1·/amr2 예시는 /robot1·/robot6으로 대체했다. 화면 표시는 AMR1·AMR2다.
- system_document_tree.md는 과거 구조 제안으로 이 저장소에 포함되어 있지 않다. 문서 구조의 기준으로 사용하지 않는다.
- 2026-09-07 결정: 관제와 시스템 모니터를 별도 개발 단위로 구분하고, 통합 실행 시 관제 PC(PC 3)에서 두 기능을 함께 실행한다. 근거: 프로젝트 담당자의 팀 구분·실행 방식 명시. 영향: 공용 규칙, 기능 담당, 인터페이스 검토자, 통합 및 수정 요청 양식. 통신 값·제어 정책 변경은 없다.

- 2026-09-07 결정: 시스템 모니터는 토픽 수신·표시를 담당하고 관제가 운영 상태·경고를 판단한다. 공용 로그 전달 계약은 interfaces.md, 내부 저장 설계는 monitoring_and_data.md로 구분한다. 근거: 프로젝트 담당자의 역할·문서 구분 명시. 표시용 토픽·공용 로그 상세 계약은 TBD-IF-011로 관리하며 구현·통합 검증은 별도로 수행한다.

- 2026-09-07 결정: command·mission·token·report·CCTV/Detection/증적·관제 운영 event ID는 사람이 식별 가능한 발행자 session·sequence 기반 문자열을 사용한다. MissionCommand 확인은 CommandCheck의 ACCEPTED·EXECUTING·REJECTED로 구분하고 최종 결과는 PatrolReport로 전달한다. 상세 형식과 필드는 interfaces.md를 기준으로 한다. 근거: 개발 프로세스 학습 범위에서 로그 추적성과 팀 간 계약 이해를 우선한다. AMR 반영은 [관제 수정 요청서](change_requests/CR-관제_09-07_15-55_AMR_명령_토큰_상태_안전_계약_변경.md)로 추적한다.

- 2026-09-07 결정, 2026-09-08 용어 명확화: LOW는 새 mission을 시작하지 않고 현재 mission의 순찰·복귀·도킹까지 완료하며 CRITICAL은 즉시 복귀 또는 도킹 판단으로 전환한다. 화재 확정 후에도 현재 mission의 순찰·복귀·도킹까지 기존 token을 유지하고 종료 시 회수하며, 이후 다른 로봇에 새 token을 발급하지 않는다. 도킹 성공과 화재 부저 OFF는 DOCKED 완료 센서·별도 충전 감지 신호 활성 2초 연속이며, 이 신호는 SOC 기반 `BatteryState` enum과 독립적이다. 도킹 실패 시 다른 활성 화재가 없으면 부저를 끄고 관제 경고를 발생시킨다. 근거: 프로젝트 담당자 명시. 영향: 관제·AMR 공용 계약과 IT-13·14 시험 기준.

## 초안의 한계

Detection·증적 전송 계약, PatrolReport 저장 ACK와 큐 삭제, E-stop 원인별 상세 clear 조건, System monitor 요청 API와 관제 운영 상태 토픽, Keepout 상태·탈출 경로 검증 등은 차기 버전 TBD다. E-stop 대표 reason 우선순위와 RobotStatus safety enum, MissionCommand·CommandCheck·Heartbeat·EStop의 기준선 범위는 v1.0에 확정했지만 코드 반영과 장비 통신 검증은 별도다. 소프트웨어 버전·주소의 실제 적용 상태 및 장비 통신은 배포 시 검증한다. 설계 문서의 예시를 실제 적용된 설정이나 구현 완료의 근거로 사용하지 않는다.

## ROS 2 워크스페이스

워크스페이스 이름은 `patrol`이며, 저장소 루트 자체를 워크스페이스로 사용한다. 패키지 작업 폴더는 루트의 `src/` 아래에 둔다.

```text
patrol/                 # 저장소 루트 = 워크스페이스 루트
├── .github/
├── docs/
├── src/
│   ├── patrol_interfaces/
│   ├── patrol_amr/
│   ├── patrol_control/
│   ├── patrol_vision/
│   ├── patrol_sysmon/
│   └── patrol_bringup/
│       ├── launch/
│       ├── config/
│       └── maps/
├── scripts/
└── tests/
    ├── integration/
    └── fixtures/
```

Ubuntu 24.04 / ROS 2 Jazzy 환경에서는 `patrol` 루트에서 `colcon build`를 실행하며 생성되는 `build/`, `install/`, `log/`는 Git에서 제외한다. 2026-09-08 기준 `patrol_interfaces 1.0.0`과 AMR·AMR 안전·비전 패키지는 이 작업공간에서 로컬 빌드를 확인했고, 시스템 모니터는 로컬 소비부·별도 프로세스 DDS 시험을 확인했다. `src/patrol_control`의 관제 동작 코드는 아직 미구현이며, 상대 PC 배포와 여러 PC·장비 통합시험은 완료되지 않았다.

## Git 협업 가이드

- [버전 관리](development/version-control.md)
- [PR 작성과 승인](development/pull-request-guide.md)
- [브랜치 네이밍 규칙](development/branch-naming.md)
- [브랜치 사용 가이드](development/branch-guide.md)
- [GitHub PAT 인증 저장 가이드 — 처음 시작하기](development/git-authentication.md)
