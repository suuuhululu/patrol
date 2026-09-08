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

