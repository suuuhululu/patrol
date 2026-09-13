# 시스템 통합과 시험

> 기준일: 2026-09-13 · 계약: `patrol_interfaces 2.0.0`

이 문서는 최종 공용 인터페이스의 통합 순서와 합격 조건을 정의한다. 개별 팀의
단위시험 통과만으로 종단 통합이 완료됐다고 판단하지 않는다.

## 1. 통합 기준

- 모든 PC는 같은 Git commit의 `patrol_interfaces`를 빌드한다.
- `robot_id`와 namespace는 `robot1`, `robot6`을 사용한다.
- 외부 순찰은 `Patrol` Action만 사용한다.
- AMR 제어와 로컬 감지 사이에 별도 공용 감지 Action을 요구하지 않는다.
- 최종 속도는 각 AMR의 `local_safety_supervisor`만 발행한다.
- EStop은 예약 인터페이스이며 현재 시험 범위에서 제외한다.

## 2. 기동 순서

1. PC 3 Offboard Discovery Server와 기존 TB4 Onboard Discovery를 확인한다.
2. `robot1`, `robot6`의 AMR 노드와 Patrol Action Server를 기동한다.
3. 시스템 모니터의 `/system_monitor/report_detection` Service Server를 기동한다.
4. CCTV `gate_cam`, `center_cam`, `cam_master`를 기동한다.
5. Control Server를 기동한다.
6. 토픽·Action·Service 타입과 송수신 주체를 확인한다.

## 3. 필수 종단 흐름

### IT-01 순찰 시작

```text
patrol_allowed=true
→ Patrol Goal
→ Goal accepted
→ WAITING_FOR_TOKEN
→ DriveToken
→ token_valid=true
→ UNDOCKING
→ PATROLLING
```

합격 조건은 `WAITING_FOR_TOKEN` 전에 AMR이 이동하지 않고, 동시에 두 로봇에
유효한 Token이 발급되지 않는 것이다.

### IT-02 waypoint와 완료

```text
PATROLLING
→ WAYPOINT_REACHED 반복
→ DOCKING
→ Patrol Result
→ 빈 DriveToken
```

Result의 outcome과 reason이 Action 정의와 일치하고 완료 뒤 Token이 회수돼야 한다.

### IT-03 차량 대피와 재개

```text
patrol_allowed=false
→ MOVE_TO_SAFE_ZONE
→ MOVING_TO_SAFE_ZONE
→ patrol_allowed=true
→ RESUME_PATROL
→ RESUMING
→ PATROLLING
```

동일 permit 반복에는 명령이 중복되지 않아야 한다. 안전구역 이동 중에는 기존
Token을 유지하고, 별도 Patrol Goal을 만들지 않는다.

### IT-04 감지와 저장

```text
AMR 내부 감지
→ DETECTION_PROCESSING
→ DETECTION_CONFIRMED + event_id + event_type
→ ReportDetection
→ STORED 또는 DUPLICATE
```

관제는 Patrol Feedback으로 사건을 식별하고, 시스템 모니터는 같은 event_id의
동일 요청을 중복 저장하지 않는다. `REJECTED` 사유도 확인한다.

### IT-05 화재 hold

`DETECTION_CONFIRMED + FIRE` 후 현재 Action의 Token 갱신은 허용하되, Action 종료
뒤 다른 로봇의 새 Goal과 Token을 차단한다. 운영자가 hold를 명시적으로 해제한
뒤에만 다음 순찰을 허용한다.

### IT-06 취소와 오류

- Cancel 요청 시 빈 Token이 Action 종료보다 먼저 발행되는지 확인한다.
- Goal 거절, Action 실패, Result 오류 뒤 활성 슬롯이 해제되는지 확인한다.
- Token 발행 중단과 lease 만료 뒤 최종 속도가 차단되는지 확인한다.
- 통신 복구만으로 자동 출발하지 않는지 확인한다.

### IT-07 CCTV

- gate 토픽은 `ENTERING`, `EXITED`만 수락한다.
- center 토픽은 `PARKED`, `EXITING`만 수락한다.
- `cam_master`가 상태에 맞는 `patrol_allowed`를 5 Hz로 제공하는지 확인한다.
- CCTV가 AMR 제어 토픽을 직접 발행하지 않는지 확인한다.

## 4. 계약 검증

```bash
python3 scripts/verify_interface_v1.py
colcon build --packages-select patrol_interfaces patrol_control
colcon test --packages-select patrol_interfaces patrol_control
colcon test-result --verbose
```

검증 항목:

- 소스 트리와 CMake 등록 목록 일치
- 설치된 필드·상수와 원본 IDL 일치
- manifest SHA-256 일치
- 삭제된 타입 import 불가
- 관제 상태 머신·콜백 테스트 통과
- 문서 링크와 인터페이스 이름 일치

## 5. 완료 판정

다음 결과를 구분해 기록한다.

- 단위시험 완료
- 같은 PC의 ROS smoke test 완료
- 여러 PC의 DDS 송수신 완료
- 실제 AMR 주행 완료
- 실제 CCTV와 감지 저장까지 포함한 종단시험 완료

문서 작성, 테스트 절차 작성 또는 mock 시험만으로 실제 장비 통합 완료를 선언하지
않는다. 실패 시 생산자·소비자·QoS·namespace·시간 순서를 함께 기록한다.

## 6. 범위 밖

- EStop 실행과 해제
- 자동 역할 교대와 배터리 정책
- `DetectionEvidence` 전용 토픽
- 시스템 모니터의 상세 Dashboard·DB 보존 정책
