# CCTV 비전 기능 설계

상태: 설계 초안 · 담당: 비전 팀 · 통합 실행 위치: PC 4 · 공통 계약: [interfaces.md](interfaces.md)

시스템 시나리오는 [scenarios.md](scenarios.md)를 따른다. 이 팀은 UC-04의 차량 상태·permit 생성과 UC-01·03·05·08의 permit 연계 범위를 담당하며, UC 전체를 단독 구현하는 것으로 해석하지 않는다.

## 1. 책임

PC 4는 Gate/Center CCTV를 처리해 차량 상태 이벤트를 생성하고 cam_master가 patrol_allowed를 계산한다. 차량은 한 대만 존재한다. AMR OAK-D 기반 Detection·yaw 정렬·증적 생성은 [amr.md](amr.md)의 책임이다.

| 기능 | 발행 또는 수신 | 허용 상태 |
|---|---|---|
| gate_cam | /vision/cctv/gate_event 발행 | ENTERING, EXITED |
| center_cam | /vision/cctv/center_event 발행 | PARKED, EXITING |
| cam_master | 두 이벤트 구독, /vision/cctv/patrol_allowed 발행 | Bool |

PC 4 ROS 참여자는 PC 3 Offboard Discovery Server의 Client다. 구체적 CCTV 장치·모델·배포는 TBD-VIS-001이다.

## 2. 이벤트 처리

CameraState 필드는 interfaces.md 6절을 따른다. vehicle_track_id는 제거된 항목이다. topic별로 허용되지 않은 enum은 폐기하고 진단 로그를 남긴다.

cam_master는 event_id를 Q-13 동안 보관해 같은 이벤트를 한 번만 처리한다. CCTV 이벤트는 RELIABLE/VOLATILE이며 과거 이벤트 재생을 위해 TRANSIENT_LOCAL을 사용하지 않는다. ID 생성·state 정수값은 TBD-IF-005다.

confidence 필드는 존재하지만 차량 상태 확정 confidence나 연속 프레임 기준은 아직 정해지지 않았다(TBD-VIS-001). AMR Detection의 1초 의도를 CCTV에 적용하지 않는다.

## 3. 순찰 허용 조건

| 수신 상태 | patrol_allowed |
|---|---|
| 초기값 | true |
| ENTERING | false |
| PARKED | true |
| EXITING | false |
| EXITED | true |

ENTERING → PARKED는 진입 이벤트 쌍이다. EXITING → EXITED는 독립적인 출차 이벤트 쌍이다. PARKED → EXITING을 필수 연결 전이로 정의하지 않는다. 독립 출차 이벤트를 처리할 수 있어야 한다.

통신 timeout 시 마지막 patrol_allowed 값을 유지한다. 관제가 timeout을 판단하여 경고·로그를 토픽으로 제공하고 시스템 모니터는 이를 표시·기록한다. 임의로 false로 변경하지 않는다. 단, 이 정책이 token·E-stop 등 별도 안전 게이트를 무효화하지 않는다.

patrol_allowed는 관제 판단 조건이며 AMR에 직접 주행·정지 명령을 발행하지 않는다. 차량 진입을 사람이 직접 제어하므로 vehicle_entry_block 토픽은 만들지 않는다. 관제의 대피·재개 순서는 [integration.md](integration.md)를 따른다.

## 4. 오류와 진단

잘못된 enum, 중복 event_id, 이벤트 미수신, 카메라 입력 상태를 진단할 수 있어야 한다. 팀 간 로그 필드·전달 경로는 [interfaces.md의 TBD-IF-011](interfaces.md#tbd), 내부 저장 설계는 [monitoring_and_data.md의 TBD-MON-001](monitoring_and_data.md#tbd)을 따른다.

늦게 도착한 서로 다른 ID의 이벤트, 순서 역전, cam_master 재시작 후 보존 값·중복 캐시 정책은 TBD-VIS-002다. VOLATILE 설정만으로 모든 과거 이벤트 문제를 해결했다고 간주하지 않는다.

## 5. 검증

정상 진입 쌍과 독립 출차 쌍, topic별 enum 검증, 중복 제거, timeout 시 마지막 값 유지, 관제 대피·재개 연계를 확인한다. [통합시험 IT-05·06](integration.md#4-통합시험-명세)을 참조한다.

## TBD

| ID | 미정 사항 | 영향 단위 | 상태 |
|---|---|---|---|
| TBD-VIS-001 | CCTV 입력·모델·ROI, 차량 상태 확정 confidence·시간 기준, 장애 판단 | 비전·관제 | OPEN |
| TBD-VIS-002 | 순서 역전·누락·늦은 이벤트, cam_master 재시작 시 상태·캐시 처리 | 비전·관제 | OPEN |

발행 주기와 경고 timeout은 TBD-IF-010, CameraState 계약은 TBD-IF-005에만 정의한다.
