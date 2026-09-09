# [관제] AMR patrol_interfaces v1.0.0 통일

- 상태: v1.0 wire 로컬 반영·검증 완료 · AMR 통합 launch 연결 보완 필요 · 실제 장비 주행 미실시
- 최초 작성 시각: 2026-09-08 21:04 KST
- 요청자: 관제 개발
- 요청 단위: 관제
- 대상 단위 및 로봇: AMR / robot1·robot6
- 관련 TBD ID: TBD-IF-001·002·003·004·006·007·008·009
- 기준 문서·절: [interfaces.md](../interfaces.md), [v1.0 기준선](../decisions/2026-09-08-control-interface-baseline.md)
- 결정 일자·근거: 2026-09-08 사용자 결정 — 현재 wire schema를 v1.0으로 고정하고 잔여 TBD는 차기 버전 이관
- 코드 변경 승인 근거·범위: 2026-09-08 사용자 승인 — 모든 팀을 공용 인터페이스 v1.0으로 일괄 통일

## 변경 이유

공용 패키지 버전과 메시지 집합을 각 PC가 임의로 해석하면 DDS 타입 불일치가 빌드 후에야 드러난다. AMR의 v1.0 소비 규칙과 설치 타입을 하나의 manifest로 확인할 수 있게 한다.

## 변경 전 → 변경 후

- 변경 전: 패키지 버전 0.1.0, 확정 메시지 수와 설치 결과를 기계적으로 비교하는 기준 없음.
- 변경 후: `patrol_interfaces 1.0.0`, 메시지 15개, 설치 Python 타입의 필드·상수와 정규화 manifest 검사.

## 요청·반영 범위

`patrol_interfaces 1.0.0`의 15개 wire schema를 같은 Git commit에서 빌드한다. AMR 소비부는 `latched`·`parameters_json`을 wire 필드로 사용하지 않고 EStop `all`, CommandCheck 0~3, RobotStatus safety 0~5를 사용한다. 임무·Nav2 알고리즘은 변경하지 않는다.

## 검증·완료 조건

공용 단독 빌드, AMR 패키지 빌드·시험, `scripts/verify_interface_v1.py --installed` PASS와 manifest SHA-256 기록을 완료 조건으로 한다. 실제 장비 주행은 별도다.

## 2026-09-08 반영 결과

- `patrol_interfaces`, `patrol_amr`, `patrol_amr_safety` 로컬 빌드 성공.
- AMR 전체 로컬 회귀시험 343개 통과. 앞선 v1.0 관련 시험 144개와 99개 subtest 결과도 유지했다.
- RobotStatus safety enum은 0~5 정수만 수락하도록 확인했다.
- CommandCheck mapping은 ACCEPTED=1·EXECUTING=2·REJECTED=3 외 값을 생성하지 못하게 고정했고, MissionIngress의 무효 payload·ID 충돌은 각각 205·203을 호출자 주입 없이 사용한다.
- RobotStatus `safety_state`를 직접 주입하던 구형 launch parameter를 제거하고 내부 안전 상태 토픽만 사용하도록 정리했으며, 두 AMR launch의 `--show-args`를 확인했다.
- 설치 manifest: `5db7945d3495d954c195935e96a499535f052578d6755be622cd3a223b6816d6`.
- PC 1·2 설치 결과 비교와 실제 주행은 **NOT_RUN**이다.
- 잔여 통합 불일치: `hardware_patrol.launch.py`는 `local_safety_supervisor`·`status_reporter`를 `patrol_amr` 실행 파일로 참조하지만 실제 설치 위치는 `patrol_amr_safety`다. 또한 `command_gateway`의 `command_dispatch` 구독자가 없고 통합 launch에도 gateway가 포함되지 않아, CommandCheck와 실제 mission 실행의 단일 종단 경로가 아직 연결되지 않았다. 이는 15개 wire schema 불일치는 아니지만 AMR 통합 실행 전 보완해야 한다.

## 요청 작업과 영향

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| AMR | robot1·robot6에서 같은 commit 빌드·manifest 비교, 통합 launch의 실제 패키지 참조와 command gateway→mission 실행 경로 연결, 실제 송수신 확인 | `patrol_amr`, `patrol_amr_safety`, 통합 bringup | AMR |
| 관제 | 같은 v1.0 타입으로 송수신 노드 구현 | `src/patrol_control` | 관제 |
| System monitor·비전 | 별도 요청서에서 추적 | 각 소비·생산부 | 각 팀 |

혼합 버전은 허용하지 않는다. 각 PC에서 같은 commit을 받은 뒤 공용 패키지부터 빌드하고 소비 패키지, manifest 검사, 로컬 시험, 실제 PC 간 시험 순으로 적용한다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | wire 로컬 소스 검증 완료 | 전체 343개 시험·manifest PASS | 통합 launch·command 실행 연결, PC 1 설치·실기 |
| AMR / robot6 | wire 로컬 소스 검증 완료 | 같은 공용 소스·시험 | 통합 launch·command 실행 연결, PC 2 설치·실기 |
| 관제 | 공용 타입만 반영 | 기준선·manifest PASS | 관제 노드 구현 |
| System monitor | 별도 요청서 | System monitor 통일 요청서 | 실제 PC 시험 |
| 비전 | 별도 요청서 | 비전 통일 요청서 | 실제 PC 시험 |

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-08 21:04 KST | 관제 | v1.0 일괄 통일 요청 작성 | 사용자 승인 |
| 2026-09-08 22:09 KST | 관제 | 로컬 빌드·시험 완료, 다중 PC 검증은 미완료로 분리 | 실행 결과 |
| 2026-09-08 22:33 KST | 관제 | 잔여 비계약 check_state·reason code 주입 및 safety_state launch 입력 제거, 전체 AMR 회귀·launch 인자 확인 | 불일치 감사·343개 시험 PASS |
| 2026-09-08 22:41 KST | 관제 | wire 외 AMR 통합 launch 패키지 참조와 command dispatch 미연결을 잔여 작업으로 기록 | 설치 실행 파일·구독자 정적 대조 |
