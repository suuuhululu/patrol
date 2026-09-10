# AMR mission 노드 Detection 수신·yaw 정렬 흐름

- 작성 시각: 2026-09-09
- 범위: 비전 `DetectionCandidate` 수신부터 `AlignmentStatus` terminal 발행까지, mission 노드가 담당하는 구간
- 근거: [DetectionCandidate 토픽·QoS 확정](change_requests/CR-AMR_09-09_10-49_DetectionCandidate_토픽_QoS_확정_요청.md), [AlignmentStatus 토픽·QoS 확정](change_requests/CR-AMR_09-09_10-45_AlignmentStatus_토픽_QoS_확정_요청.md), [yaw 정렬 수치와 Nav2 후보 중재 확정](change_requests/CR-AMR_09-09_10-53_yaw_정렬_Nav2_중재_확정.md)
- 구현 상태: **미구현.** 공용 메시지 세 종만 존재하고 AMR 수신·정렬·발행 코드는 없다.

## 1. 책임 경계

| 책임 | 담당 | 상태 |
|---|---|---|
| 후보 생산, `AlignmentStatus` 소비, 정렬 완료 후 1초 최종 검증 | 비전 `detecting_node` | robot6 후보 발행 단위 시험 완료 |
| 후보 선택, Nav2 goal 취소, yaw 후보 생산, `AlignmentStatus` 생산 | mission 정렬부 (박성현) | 미구현 |
| 두 속도 후보 신선도·동시성 판정, 안전 게이트, 유일한 최종 `cmd_vel` | local safety (조정묵) | `cmd_vel_yaw` 구독 미구현 |

비전 노드는 `cmd_vel`, `cmd_vel_yaw`, Nav2 goal 중 어느 것도 발행하지 않는다. 회전과 정지 확인은 전부 AMR이 한다.

## 2. 인터페이스 계약

| 방향 | 토픽 | 타입 | QoS |
|---|---|---|---|
| 비전 → mission | `/{robot}/vision/detection_candidate` | `patrol_interfaces/DetectionCandidate` | RELIABLE / VOLATILE / KEEP_LAST(10) |
| mission → 비전 | `/{robot}/vision/alignment_status` | `patrol_interfaces/AlignmentStatus` | RELIABLE / VOLATILE / KEEP_LAST(10) |
| mission → local safety | `/{robot}/cmd_vel_yaw` | `geometry_msgs/TwistStamped` | Nav2 후보와 동일 velocity QoS |

양쪽 모두 `TRANSIENT_LOCAL`을 쓰지 않는다. 노드 재시작 뒤 과거 후보나 과거 terminal 상태가 새 것처럼 재전달되는 것을 막기 위해서다.

`candidate_id`는 비전이 만들고 AMR은 파싱하거나 바꾸지 않는다. `AlignmentStatus.candidate_id`에 받은 값을 그대로 되돌려준다.

## 3. 확정 수치

| 항목 | 값 |
|---|---|
| 후보 수락 confidence | 0.70 이상 |
| 정렬 완료 오차 | `abs(horizontal_error) <= 0.05` |
| 오차 유지시간 | 0.5초 연속 |
| yaw 각속도 | 절댓값 0.08 ~ 0.25 rad/s |
| yaw timeout | 정렬 시작 후 10초 |
| 후보 단절 | 마지막 유효 후보 이후 0.6초 초과 |
| 후보 신선도 (Q-17) | 각 TwistStamped age 0.5초 이하 |
| 실제 정지 확인 | 선속도 0.05 m/s 이하, 각속도 0.1 rad/s 이하, 0.5초 연속, odom age 0.5초 이하 |

## 4. 수신부터 terminal 까지

```mermaid
flowchart TD
    V[비전 detecting_node] -.->|"/{r}/vision/detection_candidate<br/>robot_id·candidate_id:string, event_type:uint8<br/>confidence·horizontal_error:float32, stamp:Time"| RX{수신 검증}

    RX -->|"robot_id != namespace"| DROP[후보 폐기·상태 미발행]
    RX -->|"confidence < 0.70"| DROP
    RX -->|"terminal 처리된 candidate_id"| DROP
    RX -->|"정렬 진행 중이며 다른 candidate_id"| DROP
    RX -->|"유효한 신규 후보"| GATE{정렬을 시작해도 되는가}

    GATE -->|"motion_allowed:bool=false"| DROP
    GATE -->|"임무 상태가 정렬 불가"| DROP
    GATE -->|"bool=true"| BEGIN[정렬 시작]

    BEGIN -.->|"/{r}/vision/alignment_status<br/>state:uint8=0 ALIGNING · 1회"| V
    BEGIN --> CANCEL[활성 Nav2 goal 취소]
    CANCEL --> STOP1{odometry 실제 정지 확인}
    STOP1 -->|"미확인"| CANCEL
    STOP1 -->|"확인"| LOOP[yaw 회전 루프]

    LOOP -.->|"/{r}/cmd_vel_yaw · TwistStamped<br/>linear.x=0.0, angular.z:부호는 horizontal_error 계약<br/>절댓값 0.08~0.25 rad/s, stamp:Time"| S[local safety 후보 중재]
    LOOP --> CHK{매 주기 판정}

    CHK -->|"안전 조건 상실<br/>token·E-stop·heartbeat·센서"| AB[yaw 후보 0 출력]
    CHK -->|"마지막 유효 후보 이후 0.6초 초과"| FAILOUT[yaw 후보 0 출력]
    CHK -->|"정렬 시작 후 10초 경과"| FAILOUT
    CHK -->|"abs(horizontal_error) <= 0.05 가 0.5초 미만"| LOOP
    CHK -->|"abs(horizontal_error) <= 0.05 가 0.5초 연속"| ZERO[yaw 출력 0]

    ZERO --> STOP2{odometry 실제 정지 재확인}
    STOP2 -->|"미확인·timeout"| FAILOUT
    STOP2 -->|"확인"| DONE

    DONE[정렬 완료] -.->|"/{r}/vision/alignment_status<br/>state:uint8=1 ALIGNED_COMPLETE · 1회"| V
    FAILOUT -.->|"/{r}/vision/alignment_status<br/>state:uint8=2 FAILED · 1회"| V
    AB -.->|"/{r}/vision/alignment_status<br/>state:uint8=3 SAFETY_ABORTED · 1회"| V

    DONE --> HOLD[정지 유지 · Nav2 자동 재개 없음]
    FAILOUT --> HOLD
    AB --> HOLD
    HOLD --> RESUME{mission 상태·실행 조건 재확인}
    RESUME -->|"조건 충족"| NAV[Nav2 재개는 별도 판단]
    RESUME -->|"미충족"| WAIT[대기]

    V2[비전: ALIGNED_COMPLETE 수신] -.->|"동일 candidate_id · 1초 최종 검증"| EV[DetectionEvent·증적 생성]
```

## 5. local safety 쪽 중재

mission 정렬부가 `cmd_vel_yaw`를 내는 동안 Nav2도 `cmd_vel_safe`를 낼 수 있다. 최종 판정은 local safety가 한다.

```mermaid
flowchart TD
    N[Nav2 cmd_vel_safe] --> A{신선한 후보가 몇 개인가}
    Y[정렬부 cmd_vel_yaw] --> A
    A -->|"0개"| Z["최종 0 · CANDIDATE_MISSING 또는 CANDIDATE_STALE"]
    A -->|"1개"| G{token·E-stop·heartbeat 게이트}
    A -->|"2개 동시"| Z2["최종 0 · 선택을 추측하지 않는다"]
    G -->|"통과"| OUT["/{r}/cmd_vel 로 후보 그대로"]
    G -->|"차단"| Z3["최종 0 · 차단 사유 전부 보고"]
```

두 후보가 동시에 신선하면 어느 쪽을 믿을지 정할 근거가 없으므로 0을 낸다. 정렬부가 Nav2 취소와 실제 정지 확인을 먼저 하는 이유가 이것이다. 그 순서를 지키면 두 후보가 동시에 신선한 구간이 생기지 않는다.

## 6. 상태 전이 규칙

- 한 `candidate_id`에 `ALIGNING`은 최대 1회, terminal 상태도 최대 1회다.
- terminal 발행 후 같은 ID를 `ALIGNING`으로 되돌리지 않는다. 새 정렬은 새 ID로 시작한다.
- 안전 원인 중단은 `FAILED`가 아니라 `SAFETY_ABORTED`로 구분한다. 비전이 재시도 여부를 다르게 판단해야 하기 때문이다.
- `ALIGNED_COMPLETE`는 odometry 실제 정지 확인 전에 발행하지 않는다. 회전 중에 비전이 최종 검증을 시작하면 흔들린 영상으로 판정하게 된다.
- terminal 뒤 Nav2를 자동 재개하지 않는다.

## 7. 미구현·미합의

| 항목 | 상태 |
|---|---|
| mission 정렬부 전체 (수신·중재·yaw 생산·상태 발행) | 미구현 |
| local safety `cmd_vel_yaw` 구독과 두 후보 동시 신선 시 0 출력 | 미구현 |
| 정렬 완료 뒤 동일 대상 1초 최종 확인과 이벤트 중복 판정 | TBD-IF-006 |
| `DetectionEvent`·`EvidenceChunk` 발행과 수신 저장 ACK | TBD-IF-006·007 |
| 비전팀의 토픽·QoS 회신 | 대기 |
