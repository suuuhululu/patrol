# Control Server 기능 설계

> 기준: [2026-09-07 PM 설계 결정](decisions/2026-09-07-design-baseline.md). 관제는 별도 노드, 시스템 모니터는 UI 전용, 공용 패키지는 `patrol_interfaces`이며 상세 계약은 System design의 확정 내용을 우선한다.

상태: 설계 초안 · 담당: 관제 팀 · 통합 실행 위치: PC 3 · 참조: [interfaces.md](interfaces.md), [integration.md](integration.md)

시스템 시나리오는 [scenarios.md](scenarios.md)를 따른다. 이 팀은 UC-01·02·03·04·05·06·07·08의 관제 판단·제어·로그 제공 범위를 담당하며, UC 전체를 단독 구현하는 것으로 해석하지 않는다.

## 1. 책임

관제는 robot1·robot6을 관리하고 명령, Drive Token, Keepout, 복구 게이트, 역할 교대를 결정한다. E-stop은 Safety Arbiter가 단일 발행한다. 별도 개발 단위인 시스템 모니터 팀의 모니터링·DB·Dashboard는 [monitoring_and_data.md](monitoring_and_data.md)에 둔다.

PC 3에서 함께 실행해도 시스템 모니터 팀의 코드 소유권과 수정 범위는 분리한다. 관제는 제어 판단과 화면에 제공할 운영 상태·통신 이상·경고·보고 누락 판단을 수행한다. 시스템 모니터는 관제가 토픽으로 제공한 판단 결과를 표시하고 이력을 저장·조회한다.

아래는 논리 기능 분할이며 독립 ROS 노드 수를 의미하지 않는다.

| 기능 | 책임 |
|---|---|
| Robot Command Manager | 명령 검증·중재·재전송·취소·대체 |
| Drive Token Manager | holder 선정, 발급·갱신·회수 |
| Robot State / Recovery Gate | 유효 상태·STALE·위치·재개 조건 관리 |
| Handover Manager | 배터리·거리 기반 가용 AMR 선정과 교대 |
| Emergency Controller / Safety Arbiter | 정지 원인 통합, 단일 E-stop, 해제 결정 |
| Traffic / Keepout Coordinator | permit 대응, Keepout transaction, 대피 조정 |
| ROS 2 Command Gateway | 결정된 명령·권한 발행, parameter API 호출 및 결과 전달 |

## 2. 명령과 권한

로봇 표시명은 AMR1/AMR2, 계약 식별자는 robot1/robot6이다. 명령별로 UUID v4 command_id를 사용하고 동일 재전송에서 유지한다. 대체·새 목적에는 새 ID를 부여한다. 관제는 외부 Nav2 Action을 호출하지 않는다.

Drive Token 발급·갱신·회수는 관제가 결정한다. AMR은 별도의 로컬 검증·만료 책임을 가진다. 발행·lease는 Q-01을 따른다. token을 받은 사실과 임무를 실행하라는 명령을 분리한다.

한 holder를 지정하는 공통 토큰 모델을 유지한다. 다른 로봇으로 교대할 때 기존 token을 먼저 회수한다. 실제 정지 확인과 신규 발급 사이의 조건은 TBD-INT-001이며 회수 메시지 발행만으로 상대의 정지 완료를 단정하지 않는다.

명령 우선순위·동시 명령 중재, START/RESUME 차이, 재전송 timeout은 TBD-CTRL-001이다.

## 3. RobotStatus와 통신 복구

수신 로봇 ID와 namespace를 확인하고 마지막 수신 시각·유효 pose를 추적한다. Q-03을 초과하면 관제의 상태를 STALE로 전환하고 신규 mission과 token 갱신을 중단한다. 결과 미수신 임무는 UNREPORTED로 유지하며 PatrolReport를 대필하지 않는다.

복구 시 다음을 모두 확인한다.

1. Q-04 동안 RobotStatus를 정상 연속 수신한다.
2. Q-05의 pose_valid·pose age 기준을 충족한다.
3. E-stop이 해제되어 있다.
4. 필요한 Keepout 적용 상태와 배터리 조건이 충족된다.
5. 유효 Drive Token을 확보하고 재개 명령을 발행할 수 있다.

하나라도 실패하면 자동 순찰을 시작하지 않는다. Q-06의 오래된 pose는 복구 참고용이며 주행 재개 위치로 대체하지 않는다. 재개 가능 배터리 상태와 연속 정상 수신의 세부 정의는 TBD-CTRL-003이다.

## 4. 차량 상태와 Keepout

patrol_allowed=false는 정지 명령 그 자체가 아니다. 기존 순찰 취소 → Keepout ON → MOVE_TO_SAFE_ZONE → 도착 확인 → token 회수 순서로 조정한다. 대피 주행 중 필요한 token은 유지하되 E-stop·통신 등 독립 안전 조건은 계속 적용한다.

patrol_allowed=true는 E-stop·RobotStatus·Keepout 등 재개 조건 확인 → Keepout OFF → token 발급 → RESUME_PATROL 순서다. 빠른 permit 반전·중복 값에 따른 재진입 정책은 TBD-INT-002다.

Keepout transaction의 대상은 해당 로봇의 global/local costmap이다.

1. 전체 대상 parameter snapshot을 읽는다.
2. 목표값을 적용한다.
3. 전체 대상 read-back 및 lifecycle 확인이 성공하면 commit한다.
4. 일부 실패하면 전체 snapshot으로 rollback한다.
5. rollback 실패 시 Safety Arbiter에 정지를 요청하고 Keepout을 UNKNOWN으로 보고한다.

재시도 시간·횟수는 Q-07이다. rollback의 timeout·확인 절차와 재시도 중 상태 보장은 TBD-CTRL-002다. 서로 다른 노드 parameter 변경을 기본적으로 원자적이라고 취급하지 않는다.

안전구역 후보는 Q-08을 충족해야 한다. 후보가 없으면 현재 위치 정지와 SAFE_ZONE_NOT_FOUND 보고를 처리한다. mask·차량 동선 제공, 후보 계산 위치, Keepout ON 이전에 탈출 가능성을 어떻게 검증할지는 TBD-CTRL-002 및 TBD-INT-003이다.

## 5. 도킹과 역할 교대

AMR은 도킹 실행·센서 성공 판정을 담당하고 관제는 실패를 받아 가용 AMR을 선정한다. 배터리와 거리를 판단 근거로 사용한다. 정확한 적격 상태·우선순위·동점 처리는 TBD-CTRL-003이다.

기존 AMR token 회수 후 새 command_id로 인계한다. 기존 임무 종료/대체와 새 임무의 연결 관계를 기록한다. 이전 로봇이 도킹하기 위한 주행과 새 로봇 순찰의 시간 관계는 TBD-INT-001에서 결정한다.

## 6. E-stop과 화재 경계

Safety Arbiter만 /control/estop을 발행한다. AMR 로컬 안전이 최종 속도를 통제하며 물리 E-stop은 수동 reset까지 latch한다. token·heartbeat·장애물 원인은 제거 후 관제가 해제 여부를 결정한다. 활성화 즉시, 자동 해제 조건은 Q-10을 따른다.

E-stop 해제 부저는 사용하지 않는다. 화재 확정 부저의 ON/OFF는 별도 정책이다. 화재가 곧바로 어떤 mission 결과·정지·도킹 명령을 유발하는지는 TBD-INT-004다. reason code 702를 임무 결과 enum이나 Detection event_type 수치로 혼용하지 않는다.

## 7. 기록과 검증

관제는 STALE·UNREPORTED, CCTV timeout 경고, 순찰·교대 진행 상태와 운영상 증적 누락·지연 경고를 판단하고 시스템 모니터에 토픽으로 제공한다. 판단 결과와 로그의 토픽명·필드·발행 정책·초기 상태·재연결 계약은 [TBD-IF-011](interfaces.md#tbd)에서 정의한다. 기존 판단 기준은 유지하고 미정 기준은 관련 TBD에서 합의한다. 모니터가 자체 판단을 대신 수행한다고 가정하지 않는다.

명령 ID, holder 변화, Keepout 적용·rollback, STALE·복구, E-stop 원인·해제, 교대 결과를 모니터링과 연결한다. 저장 실패 시 제어 동작 영향은 TBD-MON-002에서 결정한다.

검증은 [integration.md](integration.md)의 token·상태·Keepout·교대·E-stop 시험을 따른다. Dashboard는 읽기 전용이므로 명령 입력 UI가 있다고 가정하지 않는다. 운영자 명령 입력 경로는 TBD-CTRL-004다.

## TBD

| ID | 미정 사항 | 영향 단위 | 상태 |
|---|---|---|---|
| TBD-CTRL-001 | 명령 우선순위·동시 처리·STOP/CANCEL/RESUME 정책·재전송 | 관제·AMR | OPEN |
| TBD-CTRL-002 | 안전구역 계산자·지도/동선 공급, rollback 확인·timeout·재시도 | 관제·AMR | OPEN |
| TBD-CTRL-003 | 재개/교대 배터리 적격 조건·거리 점수·동점, 정상 연속 수신 정의 | 관제·AMR | OPEN |
| TBD-CTRL-004 | 운영자 명령 입력·수동 reset/해제 요청 경로 | 관제·AMR | OPEN |

공용 계약 TBD는 interfaces.md를 참조한다. 결정 시 요청서와 상대 단위 반영 상태를 연결한다.
