# AMR 상태 연결 임시 결정과 합병 교체 지점

- 상태: **임시 결정·사용자 승인 구현 / 팀 간 확정 계약 아님**
- 결정일: 2026-09-08 KST
- 근거: 사용자가 사전 합의 자료는 없다고 확인한 뒤, “코드합병할때 수정하기 편하게 임의로 정하고 임의로 정한 내용에 대해서는 따로 명시”, “일단은 코드를 먼저 완성”하도록 지시했다.
- 범위: `patrol_amr_safety`의 운영·도킹·scan **보고 필드** 연결. mission 담당 코드·공용 메시지·Nav2·주행 허가·실제 정지 기준은 변경하지 않는다.
- 정책 ID: `TEMP-AMR-STATUS-20260908-v1`
- 단일 교체 모듈: [provisional_status_policy.py](../../src/patrol_amr_safety/patrol_amr_safety/provisional_status_policy.py)
- 관련 미정 계약: TBD-AMR-005, TBD-IF-003. 임시 구현으로 공용 TBD를 해결 처리하지 않는다.

## 1. 임의로 정한 운영 상태 우선순위

위에서 처음 만족하는 행을 사용한다. 기존 enum 숫자는 바꾸지 않았다.

| 우선순위 | 입력 | 임시 operational_state |
|---|---|---|
| 1 | safety ERROR 또는 mission FAILED | OP_ERROR |
| 2 | safety STOPPING·STOPPED·ESTOPPED | OP_STOPPED_SAFETY |
| 3 | 신선한 유효 odom의 속도가 기존 실제 정지 경계를 벗어남 | OP_MOVING |
| 4 | battery CHARGING·PATROL_READY·FULL | OP_CHARGING |
| 5 | mission snapshot 미수신 또는 motion_stopped가 false | OP_INITIALIZING |
| 6 | 나머지 | OP_READY |

예: 충전과 안전 차단이 동시에 보이면 OP_STOPPED_SAFETY가 우선한다. OP_STOPPED_SAFETY는 안전 차단을 보고하는 축이며, 실제 바퀴 정지 완료는 기존 motion_stopped와 safety_state로 구분한다. 수신 snapshot이 없거나 odom이 stale이면 READY를 추정하지 않는다.

## 2. 임의로 정한 도킹 상태 전이

입력은 최신 mission, 직전 보고 docking_state, battery enum이다. 직전 보고값은 메모리에만 보존한다.

| 입력·조건 (위 행 우선) | 임시 docking_state |
|---|---|
| mission UNDOCKING | DOCK_UNDOCKING |
| mission DOCKING | DOCK_DOCKING |
| mission PATROLLING·MOVING_TO_SAFE_ZONE·WAITING_SAFE_ZONE·RETURNING_TO_DOCK | DOCK_UNDOCKED |
| mission FAILED이고 직전 도킹값이 UNDOCKING·DOCKING·FAILED | DOCK_FAILED 유지 |
| mission COMPLETED·outcome SUCCEEDED, 직전 DOCKING | DOCK_DOCKED |
| mission COMPLETED·outcome SUCCEEDED, 직전 UNDOCKING | DOCK_UNDOCKED |
| mission CANCELED, 직전 UNDOCKING·DOCKING | DOCK_UNKNOWN |
| 위 조건에 해당하지 않고 battery가 충전 방향 enum | DOCK_DOCKED |
| 나머지 | 직전 docking_state 유지, 최초는 DOCK_UNKNOWN |

**추정 한계:** 충전 enum을 도크 접점 확인의 대용으로 쓰는 행은 임시 가정이다. reporter 재시작 뒤에는 이전 전이를 모르므로 충전 관측 또는 새 도킹 단계가 없으면 UNKNOWN이 남을 수 있다. mission의 실패 이유만으로 도킹 실패를 추정하지 않는다. 실제 도킹 Action 성공 조건이나 센서 판정을 이 모듈이 대신하지 않는다.

## 3. 임의로 정한 scan 문자열

문자열은 모두 합병 시 교체 가능한 **임시 보고용 값**이다. Detection·카메라 scan 시작/종료 이벤트를 받은 것이 아니다.

| 입력 | 임시 scan_state |
|---|---|
| mission snapshot 없음 | UNKNOWN |
| PATROLLING이며 safety NORMAL 아님 | PAUSED |
| PATROLLING·safety NORMAL·motion_stopped=true | SCANNING |
| PATROLLING·safety NORMAL·odom 무효/미수신/stale | UNKNOWN |
| 그 밖의 PATROLLING | MOVING_TO_WAYPOINT |
| mission PAUSED / FAILED / CANCELED / COMPLETED | PAUSED / FAILED / CANCELED / COMPLETED |
| 나머지 | IDLE |

**추정 한계:** 순찰 중 정지를 SCANNING으로 부르는 것은 사용자 요청에 따른 임시 규칙이다. 실제 탐지 수행·완료·증적 확보를 보증하지 않는다. 관제·모니터는 이 임시 문자열을 확정된 scan 완료 신호로 취급하지 않아야 한다.

## 4. 코드 연결과 합병 방법

1. `status_mission_bridge.py`가 기존 schema_version=1 mission snapshot을 읽는다. `has_snapshot`은 수신 여부를 제공한다. 생산자 schema를 임의 확장하지 않았다.
2. `StatusReporter._tick()`이 현재 모델·mission snapshot을 `project_axes()`에 전달한다.
3. 반환된 운영·도킹 enum만 모델에 반영하고, 값이 바뀌면 기존 PublicationGate에 알린다. scan 문자열은 다음 정기 발행에 반영한다. 기존 Q-02 2 Hz·최대 10 Hz gate는 유지한다.
4. `_publish()`가 scan 값을 빈 문자열로 덮어쓰지 않고 모델값을 전송한다. 실제 safety_state·motion_stopped·battery_state·속도·임무 ID·결과는 기존 입력을 유지한다.

합병 시 mission 담당과 세 필드의 입력·전이·재시작 의미를 합의한 뒤 **`project_axes()` 구현을 명시적 입력 매핑으로 교체**한다. 함수의 `StatusAxes` 반환 형식을 유지하면 reporter의 발행 코드·공용 메시지를 함께 고칠 필요가 없다. 입력 schema가 바뀌면 MissionStatusBridge/reader도 그 계약에 맞춰 수정한다. 임시 scan 문자열은 송신자와 수신자의 적용 시점을 맞춰 교체한다.

시작 로그에 정책 ID와 provisional 사용 사실을 경고로 남긴다. 합병 뒤 임시 정책을 제거할 때 로그와 이 문서 상태도 갱신한다. 문서만 삭제하고 임시 추론을 남기지 않는다.

## 5. 검증과 남은 실기

단위시험은 초기·이동·정지·stale·안전 우선순위·도킹 성공/실패 유지·전체 mission enum 처리를 확인한다. ROS 시험은 기존 mission JSON·odom·safety 입력을 production reporter에 공급해 세 필드의 전달과 기존 결과 복구 경로를 확인한다. 실제 결과는 [flowchart 진행 기록](../amr_patrol_safety_flowchart.md)에 기록한다.

TurtleBot 4 robot1·robot6 실기, 실제 mission·관제 PC 통합 및 임시 규칙 대체는 별도 작업이다. 임시 규칙을 포함한 코드 연결 완료와 실기·공용 계약 확정을 구분한다.
