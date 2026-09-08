# [AMR] DriveToken sequence epoch와 holder 교체 무효화

- 상태: 초안
- 최초 작성 시각: 2026-09-07 15:12 KST
- 요청자: 조정묵 (AMR)
- 요청 단위: AMR
- 대상 단위 및 로봇: 관제(계약 소유·발행) / robot1·robot6
- 관련 TBD ID: TBD-IF-002. 이 요청으로 해결하지 않으며 관제 합의 전까지 OPEN을 유지한다.
- 기준 문서·절: [interfaces.md 3절](../interfaces.md#3-drivetoken), [9절 Q-01](../interfaces.md#9-qos와-공통-시간거리-기준), [amr.md 3절·3.1절](../amr.md)
- 결정 일자·근거: 2026-09-07 사용자가 AMR 권장안으로 진행하도록 지시. AMR 구현에 잠정 적용하고 관제 합의를 요청한다.
- 코드 변경 승인 근거·범위: 2026-09-07 사용자 승인. 범위는 `src/patrol_amr/patrol_amr/drive_token_guard.py`와 그 단위시험이다. 공용 메시지 필드·enum·토픽·QoS는 변경하지 않았다.

## 변경 이유

3단계 `drive_token_guard.py` 구현 중 TBD-IF-002의 미정 사항이 코드 동작을 좌우한다는 것이 드러났다. 미정이라는 이유로 비워 두면 두 가지 실제 문제가 남는다.

첫째, sequence 하한을 영구 고정하면 관제 재시작으로 sequence가 되돌아갔을 때 AMR이 모든 토큰을 폐기하여 주행 권한을 영영 되찾지 못한다. 복구 경로가 없다.

둘째, 공통 토픽에서 관제가 다른 로봇을 holder로 지명해도 이전 holder가 Q-01 lease 1.0초 동안 주행 권한을 유지한다. 교대 순간에 두 로봇이 동시에 권한을 가진 것으로 보이는 구간이 생긴다. [integration.md의 TBD-INT-001](../integration.md#tbd)이 교대 순서를 미정으로 두고 있어 이 구간의 안전 판단이 필요하다.

## 변경 전 → 변경 후

메시지 계약은 그대로다. AMR 로컬 판정 규칙만 정한다.

| 항목 | 변경 전(미정 상태의 보수적 동작) | 변경 후(AMR 잠정 적용) |
|---|---|---|
| sequence 하한 범위 | 로봇 수명 전체에 걸쳐 단조 증가 | token 문자열 epoch 단위. token이 바뀌면 하한을 새로 잡는다 |
| 관제 재시작(sequence 역행) | 모든 토큰 폐기, 복구 불가 | 새 token 문자열이면 낮은 sequence도 수락 |
| 같은 token의 역행·중복 | 폐기 | 폐기(동일) |
| uint32 wraparound | 미구현 | 미구현(동일). 5 Hz 발행에서 소진에 약 27년이므로 역행은 재시작으로 해석한다 |
| 다른 holder 지명 관측 | 폐기만 하고 자기 권한은 lease 만료까지 유지 | 앞선 sequence면 자기 권한을 즉시 무효화(`HOLDER_CHANGED`) |
| 같은 epoch의 다른 holder 중복 메시지 | 폐기 | 폐기(동일, `OTHER_HOLDER`) |
| `header.stamp` 기반 message age | 미구현 | 미구현(동일). 아래 근거 참조 |

재생(replay) 위험은 이 규칙이 아니라 전송 계약이 제한한다. 9절이 drive_token에 lifespan 500 ms를 두었으므로 그보다 오래된 표본은 전달되지 않는다. 5 Hz 발행에서 500 ms는 2~3개 메시지에 해당한다.

`header.stamp`를 이용한 age 검증은 구현하지 않았다. 3절이 보장되지 않은 시간 동기화의 직접 비교를 금지하고 결합 방식을 TBD-IF-002로 두었기 때문이다. amr.md 3절이 message age 확인을 요구하는 것과 상충하므로, 신선도를 9절의 deadline 200 ms·lifespan 500 ms QoS가 담당하는 것으로 해석했다. 관제 확인이 필요하다.

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| AMR | 잠정 적용 완료. 관제 합의 후 재확인 | `src/patrol_amr/patrol_amr/drive_token_guard.py` | 조정묵 |
| 관제 | 아래 4개 질의 회신. sequence 발행 규칙과 교대 순서 확정 | drive_token 발행부 | 박성현 |
| System monitor | 해당 없음. drive_token을 구독하지 않는다 | | |
| 비전 | 해당 없음. drive_token을 구독하지 않는다 | | |

관제에 확인이 필요한 항목이다.

1. `sequence`는 공통 토픽 하나의 전역 단조 값인가, holder별 값인가. AMR은 전역 단조로 구현했다.
2. 관제 재시작 시 `token` 문자열을 반드시 새로 발급하는가. AMR의 복구는 이 전제에 의존한다.
3. 권한 교대 시 새 holder의 token을 이전 holder의 sequence보다 큰 값으로 발행하는가.
4. `header.stamp`를 age 검증에 사용해야 하는가. 사용한다면 시계 기준과 허용 age를 정해야 한다. 사용하지 않는다면 신선도를 QoS로 보장한다는 해석을 확정한다.

## 영향과 적용 순서

- 메시지 필드·enum·토픽·QoS를 바꾸지 않으므로 관제 코드 변경 없이도 현재 계약대로 동작한다. 관제가 위 전제와 다르게 발행하면 AMR이 토큰을 폐기해 주행하지 않는다. 실패 방향은 정지이며 의도치 않은 주행은 발생하지 않는다.
- 교대 즉시 무효화는 이전 holder의 주행 권한을 최대 1.0초 앞당겨 끊는다. 정지 요청이 늘어나는 방향이며 새로운 주행을 만들지 않는다.
- 혼합 버전에서도 메시지 호환성 문제는 없다. 차이는 AMR의 수락 판정에만 나타난다.
- 되돌리려면 `drive_token_guard.py`의 해당 분기를 이전 동작으로 바꾸고 단위시험을 함께 되돌린다. 데이터·저장 스키마 영향은 없다.
- 이 요청은 TBD-IF-002를 해결하지 않는다. 관제 합의 전까지 AMR 잠정 적용으로 표시한다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | 잠정 적용, 실기 미확인 | `feat/amr-safety-status`, 단위시험 25건 | 관제 합의 후 재확인, robot1 실기 |
| AMR / robot6 | 잠정 적용, 실기 미확인 | 위와 같음 | 관제 합의 후 재확인, robot6 실기 |
| 관제 | 미반영 | | 위 4개 질의 회신 |
| System monitor | 변경 불필요 | drive_token 비구독 | |
| 비전 | 변경 불필요 | drive_token 비구독 | |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: [IT-03 토큰 검증, IT-04 토큰 만료·회수](../integration.md#4-통합시험-명세). 교대 순서는 TBD-INT-001과 함께 확인한다.
- 추가 시험·기대 결과: 같은 token의 역행·중복은 폐기, 새 token epoch의 낮은 sequence는 수락, 앞선 sequence의 다른 holder 관측 시 즉시 권한 상실, 폐기 메시지는 lease 미연장.
- 실제 실행 결과와 증거: 2026-09-07 `python3 -m unittest discover -s tests -p test_drive_token_guard.py` 25건 OK. 관제 발행부와의 연동은 미실행이다.
- 미실행 또는 BLOCKED 항목: IT-03·IT-04 통합시험, robot1·robot6 실기, 교대 시나리오. 관제 구현이 없어 현재 수행할 수 없다.

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-07 | AMR | 권장안을 잠정 적용하고 관제 합의를 요청 | 사용자 지시, 복구 경로 부재와 교대 중복 권한 구간 |
| | 관제 | 회신 대기 | |
