# [관제] System monitor v1.0 E-stop 대표 원인 우선순위 확인 요청

- 상태: 검토 요청
- 최초 작성 시각: 2026-09-08 18:24 KST
- 요청자: 관제 팀
- 요청 단위: 관제
- 대상 단위 및 로봇: System monitor / robot1·robot6·all 표시
- 관련 TBD ID: TBD-IF-004·011, TBD-CTRL-004
- 기준: [관제 인터페이스 v1.0](../decisions/2026-09-08-control-interface-baseline.md), [interfaces.md](../interfaces.md)
- 코드 변경 승인 근거·범위: 문서 검토 요청이며 System monitor 코드 변경을 요청하지 않음

## 확정 내용

`/control/estop`의 대표 reason은 다음 우선순위에서 가장 먼저 활성인 값이다.

`SYSTEM_FAULT → UNKNOWN → OPERATOR → KEEPOUT_FAILURE → COMMUNICATION → OBSTACLE → TOKEN`

System monitor는 수신한 대표 reason을 표시하며 자체 우선순위를 계산하지 않는다. 물리 E-stop, `latched`, manual reset은 v1.0 범위에 없다. 전체 활성 원인 집합 전달, UI 요청 API와 원인별 상세 조건은 차기 버전 TBD다.

## 요청 사항

현재 표시·저장 구조가 위 v1.0 값을 그대로 소비하는지 확인해 달라. 코드 변경이 불필요하면 그 근거와 함께 `변경 불필요`로 회신한다. 삭제된 System monitor 측 설계 문서는 재생성하지 않으며 실제 구현·시험 완료는 별도로 기록한다.


## System monitor 회신

- 회신 일자: 2026-09-08
- 결론: **변경 불필요**
- 근거:
  - `/control/estop` 수신부(`src/patrol_sysmon/app/ros/payloads.py` `estop_payload`)는 `target_robot_id`·`active`·`reason`·`sequence`만 읽고 reason 값을 그대로 저장한다. 원인 집합을 조합하거나 자체 우선순위를 계산하는 코드가 없다.
  - 저장(`estop_latest`·`estop_history`)은 대상별 최신 행과 대표 원인이 바뀐 시점만 남기며, 화면은 수신한 reason 하나를 0~6 라벨로 표시한다. 우선순위 순서가 바뀌어도 System monitor 코드는 영향이 없다.
  - `latched`·manual reset 의존은 이미 제거했다(PR #16, `EStop.msg`에서 `latched` 삭제). 물리 E-stop UI·필드는 없다.
  - 전체 활성 원인 집합(`active_reasons`)과 UI 요청 API는 차기 버전 TBD-IF-011·TBD-CTRL-004 확정 후 별도 반영한다.
- 검증: ROS를 source한 sysmon 전체 시험 통과. 별도 프로세스 DDS 시험에서 새 `EStop`으로 `/control/estop` 매칭과 대상별 저장을 확인했다.
