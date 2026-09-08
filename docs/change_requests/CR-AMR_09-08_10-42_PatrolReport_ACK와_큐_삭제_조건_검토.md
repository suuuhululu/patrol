# [AMR] PatrolReport ACK와 영속 큐 삭제 조건 검토

- 상태: 검토 중
- 최초 작성 시각: 2026-09-08 10:42 KST
- 요청자: 박성현
- 요청 단위: AMR
- 대상 단위 및 로봇: 관제·System monitor / robot1·robot6
- 관련 TBD ID: TBD-IF-003
- 기준 문서·절: [interfaces.md 1.2·5·9절](../interfaces.md), [amr.md](../amr.md), [integration.md](../integration.md)
- 결정 일자·근거: PatrolReport 필드·result·reason code·QoS와 미전송 report 영속 보관·동일 report ID 재전송은 2026-09-07 기준 문서에서 결정됐다. 애플리케이션 수신 ACK와 큐 삭제 조건은 아직 없다.
- 코드 변경 승인 근거·범위: 사용자가 AMR-07 `status_reporter` 구현을 지시했다. AMR 내부 outbox와 ROS publisher만 구현하며 관제·System monitor 코드는 변경하지 않는다.

후속 권장 계약은 [E-stop reset과 PatrolReport 저장 ACK 인터페이스 명세](CR-AMR_09-08_13-54_E-stop_reset과_PatrolReport_ACK_인터페이스_명세.md)에 정리했다. 이 문서의 결정 요청을 구체화한 초안이며 영향 팀 합의 전에는 확정 계약이 아니다.

## 변경 이유

AMR은 임무 종료 결과를 로컬 영속 큐에 먼저 기록한 뒤 `status_reporter`가
`/{robot}/patrol_report`로 발행해야 한다. 현재 공용 계약에는 별도 ACK
메시지나 토픽이 없어 수신 애플리케이션이 저장을 완료했는지 AMR이 확인할
방법이 없다. 따라서 이번 단일 기능 구현은 subscriber가 한 명 이상 연결된
상태에서 RELIABLE publisher 호출이 성공하면 로컬 pending 항목을 지우는
기준까지 적용했다. 이는 DDS 발행 성공 기준이며 관제 또는 System monitor의
DB 저장 완료를 보장하는 애플리케이션 ACK가 아니다.

## 변경 전 → 변경 후

이번 AMR 구현:

```text
mission_worker
  → PatrolReport outbox 원자 저장
status_reporter
  → subscriber 연결 확인
  → /robotN/patrol_report RELIABLE·VOLATILE·KEEP_LAST(20) 발행
  → publish 호출 성공 후 pending 삭제
```

- subscriber가 0이면 report를 지우지 않고 같은 report ID로 보존한다.
- publisher 호출에서 예외가 발생하면 report를 지우지 않는다.
- 프로세스 재시작 뒤에도 pending report와 report ID를 복구한다.
- 수신자의 DB 저장 실패·프로세스 종료 이후까지 보장하는 ACK 재전송은 아직
  구현하지 않는다.

결정 요청:

1. PatrolReport 수신 완료 ACK가 필요한지, 필요하다면 발행 주체가 관제인지
   System monitor인지 확정한다.
2. ACK 토픽명·메시지 타입과 최소 필드(`report_id`, 수신자 session,
   저장 결과, reason)를 확정한다.
3. 두 수신자가 모두 구독할 때 큐 삭제 조건이 한 곳의 ACK인지 양쪽 ACK인지
   확정한다.
4. 재전송 간격·최대 횟수 또는 보관 기간, 수신 측 중복 제거 보관 기간을
   확정한다.
5. ACK가 영구히 오지 않을 때 RobotStatus 또는 운영 경고로 표시할 기준을
   확정한다.

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| AMR | 결정 전 현재 provisional 삭제 기준 유지, 결정 후 outbox drain에 ACK 상태 반영 | `patrol_report_outbox.py`, `patrol_report_adapter.py`, `status_reporter.py` | 박성현 |
| 관제 | PatrolReport 중복 제거 위치와 ACK 필요 여부·계약 결정 | PatrolReport 수신·UNREPORTED 해제 | 관제 담당 |
| System monitor | DB 저장 완료 ACK 필요 여부와 중복 저장 방지 기준 결정 | PatrolReport 저장 처리 | System monitor 담당 |
| 비전 | 해당 없음. PatrolReport 생산·수신 경로에 참여하지 않음 | 해당 없음 | 해당 없음 |

## 영향과 적용 순서

현재 AMR 버전은 수신자가 연결되기 전의 결과 손실을 막지만 수신 애플리케이션
처리 완료까지 확인하지 않는다. 관제와 System monitor는 `report_id`로 중복을
제거해야 한다. ACK를 도입하기로 합의하면 공용 메시지·토픽을 먼저
`interfaces.md`에 확정하고 수신자 구현, AMR outbox 삭제 조건 순으로 적용한다.
혼합 버전에서는 ACK 기능을 활성화하지 않아 기존 수신자가 없는 상태에서 큐가
무한히 쌓이는 일을 막는다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | provisional 구현 완료 | 영속 outbox·ROS 스모크 시험 | ACK 결정 후 보완 |
| AMR / robot6 | provisional 구현 완료 | 영속 outbox·ROS 스모크 시험 | ACK 결정 후 보완 |
| 관제 | 검토 요청 | 기존 PatrolReport 수신 계약 | ACK·중복 제거 확인 |
| System monitor | 검토 요청 | 기존 저장 책임 | ACK·DB 저장 기준 확인 |
| 비전 | 변경 불필요 | 경로 비참여 | 없음 |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: IT-03, IT-12
- 추가 시험·기대 결과: subscriber 미연결 중 큐 보존, 재시작 복구, 같은
  report ID 발행, 수신 중복 제거, DB 실패 후 재전송을 확인한다.
- 실제 실행 결과와 증거: AMR 단위시험 207건 PASS, 격리 ROS domain에서
  `RobotStatus`와 `PatrolReport` 수신 및 pending 큐 삭제 PASS.
- 미실행 또는 BLOCKED 항목: 관제·System monitor 실수신, DB 실패 주입,
  애플리케이션 ACK는 본 결정 전까지 BLOCKED.

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-08 10:42 | 박성현·AMR | subscriber 연결+publish 성공을 임시 삭제 기준으로 구현하고 ACK 계약을 요청 | AMR-07 단일 기능 구현 및 기존 TBD-IF-003 대조 |
| 2026-09-08 13:54 | 박성현·AMR | System monitor의 기존 IngestionAck 구현을 대조해 상세 권장 계약 초안을 별도 명세로 연결 | 사용자 인터페이스 명세서 작성 요청 |
