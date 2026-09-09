# [관제] System monitor patrol_interfaces v1.0.0 통일

- 상태: 로컬 반영·검증 완료 · 실제 상대 PC 시험 미실시
- 최초 작성 시각: 2026-09-08 21:04 KST
- 요청자: 관제 개발
- 요청 단위: 관제
- 대상 단위 및 로봇: System monitor / 전체 공용 메시지 소비
- 관련 TBD ID: TBD-IF-003·004·005·006·007·008·010·011
- 기준 문서·절: [interfaces.md](../interfaces.md), [monitoring_and_data.md](../monitoring_and_data.md)
- 결정 일자·근거: 2026-09-08 사용자 결정 — 현재 wire schema를 v1.0으로 고정하고 잔여 TBD는 차기 버전 이관
- 코드 변경 승인 근거·범위: 2026-09-08 사용자 승인 — 모든 팀을 공용 인터페이스 v1.0으로 일괄 통일

## 변경 이유

시스템 모니터가 폐기 타입·호환 필드를 계속 허용하면 다른 PC의 구형 설치를 숨길 수 있다. 정확한 v1.0 필드만 소비하고 토픽 도착 순서가 달라도 저장돼야 한다.

## 변경 전 → 변경 후

- 변경 전: 시험 fixture와 가상 publisher에 `latched` 호환 분기 잔존, 설치 타입 전체 대조 없음.
- 변경 후: EStop v1.0 필드만 사용, 25개 입력 의존성 검사, 설치 필드·상수 manifest 검사, KeepoutStatus 선행 수신 저장 보장.

## 요청·반영 범위

현재 활성 구독 25개가 `patrol_interfaces 1.0.0`의 타입을 사용하도록 고정한다. E-stop은 EStop만 구독하고 `EStopState`·`MissionCommandAck`·`latched` 호환 경로를 제거한다. DB의 과거 구조 migration 이력은 보존하며 UI·저장 기능은 호환에 필요한 범위 밖에서 바꾸지 않는다.

## 검증·완료 조건

의존성 검사, Sysmon 단위시험, 격리 DDS 종단시험, 설치 인터페이스 manifest 일치를 완료 조건으로 한다. 실제 상대 PC publisher 시험은 별도다.

## 2026-09-08 반영 결과

- ROS adapter 의존성 검사 PASS: 활성 입력 25개, 대기 0개.
- ROS 환경 전체 120개 시험과 86개 subtest 통과, 별도 프로세스 DDS 시험 6개 통과.
- 검사 중 발견한 첫 KeepoutStatus 선행 수신의 외래 키 실패를 도착 순서 독립 저장으로 수정하고 회귀시험을 추가했다.
- 설치 manifest: `5db7945d3495d954c195935e96a499535f052578d6755be622cd3a223b6816d6`.
- 실제 AMR·비전 publisher, 운영 domain 6, PC 간 네트워크 시험은 **NOT_RUN**이다.

## 요청 작업과 영향

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| System monitor | 같은 commit 빌드·manifest 비교, 실제 publisher 25개 수신 확인 | `src/patrol_sysmon` | System monitor |
| 관제 | 판단 결과의 공용 전달은 TBD-IF-011에서 후속 합의 | 관제 운영 상태·로그 | 관제 |
| AMR·비전 | v1.0 생산부 실제 PC 발행 | 각 생산부 | 각 팀 |

DB legacy migration 자료는 삭제하지 않는다. 실행 경로에서는 구형 필드를 허용하지 않으며, 실제 상대 PC 시험 전에는 통합 검증 완료로 표시하지 않는다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| System monitor | 로컬 반영·검증 완료 | 120개 시험·86개 subtest·manifest PASS | 운영 domain·상대 PC 시험 |
| 관제 | 공용 타입만 반영 | 기준선·manifest PASS | 판단/발행 노드 구현 |
| AMR / robot1·robot6 | 별도 요청서 | AMR 통일 요청서 | 실제 PC 발행 |
| 비전 | 별도 요청서 | 비전 통일 요청서 | 실제 PC 발행 |

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-08 21:04 KST | 관제 | v1.0 일괄 통일 요청 작성 | 사용자 승인 |
| 2026-09-08 22:09 KST | 관제 | 로컬 전체 시험 완료, 실제 상대 PC 시험은 미완료 | 실행 결과 |
