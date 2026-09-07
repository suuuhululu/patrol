# [System monitor] 시스템 모니터 코드 반영과 공용 패키지 명칭 정리

- 상태: 요청 · 합의 대기
- 최초 작성 시각: 2026-09-07 18:45 KST
- 작성 팀: System monitor
- 요청 단위: 관제, AMR, 비전 (공용 `patrol_interfaces` 사용 팀)
- 기준 문서: [설계 기준 결정](../decisions/2026-09-07-design-baseline.md), [interfaces.md](../interfaces.md), [AGENTS.md](../../AGENTS.md)

## 요청 이유

시스템 모니터 구현을 `src/patrol_sysmon/`에 반영했다. 개발 중 사용한 공용 메시지 패키지 이름이 확정 명칭과 다르고, 공용 패키지에 없는 메시지를 사용하고 있어 합의가 필요하다. 상세는 [설계기준 차이 정리](../../src/patrol_sysmon/docs/설계기준-차이-정리.md)에 있다.

## 변경 전 → 변경 후

### 1. 패키지 명칭

- 변경 전: 시스템 모니터 코드가 `parking_interfaces`를 import한다. 메시지 정의는 임시로 `src/patrol_sysmon/parking_interfaces/`에 두었다.
- 변경 후 제안: 확정 명칭 `patrol_interfaces`로 통일하고 임시 폴더를 제거한다. 시스템 모니터 코드의 문자열 19곳을 교체한다. 동작 변경은 없다.
- 공용 `src/patrol_interfaces/`는 이번 반영에서 **변경하지 않았다.**

### 2. 공용 패키지에 추가가 필요한 메시지

| 메시지 | 사용처 | 비고 |
|---|---|---|
| `DetectionEvent`, `EvidenceChunk` | AMR → 관제·모니터 | 감지 사건과 증적 |
| `IngestionAck` | 관제 저장 계층 → AMR | 재전송 종료 조건 |
| `KeepoutStatus` | AMR → 관제·모니터 | 적용·롤백 상태 |
| `PatrolVisit` | AMR → 관제·모니터 | 관측점 방문 |
| `EStopState` | Safety Arbiter → 전체 | 공용에는 `EStop`으로 이름이 다르다 |

`EStop`과 `EStopState`의 명칭·필드 일치 여부를 먼저 확정해야 한다.

### 3. 판단 주체

관제가 `/control/operational_state`·`/control/operational_event`를 발행하면 STALE·UNREPORTED·CCTV timeout·증적 지연 판단을 그 토픽에서 받는다. 현재 자체 계산은 토픽 미수신 시 대체 표시로 남긴다. 두 경로가 함께 동작하는 기간의 표시 기준과 전환 시점 합의가 필요하다.

## 상대 팀에 필요한 조치

- 관제: 판단 토픽 2종의 메시지 정의와 발행 시점 확정
- 공용 패키지 관리 주체: 위 메시지 추가 여부와 `EStop`/`EStopState` 명칭 확정
- 확정 후 시스템 모니터가 코드의 패키지 이름을 교체하고 재빌드 결과를 보고한다

## 검증

시스템 모니터 단위 시험 115개는 현재 명칭(`parking_interfaces`) 기준으로 통과한 상태다. 명칭 교체 후 같은 시험과 격리 DDS 종단시험을 다시 실행해 결과를 이 요청서에 추가한다.
