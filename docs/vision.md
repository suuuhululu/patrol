# CCTV 비전 기능 설계

상태: 설계 초안 · 담당: 비전(PC 4) · 공통 계약: [interfaces.md](interfaces.md)

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

### 2-1. TBD-VIS-001 비전팀 확정안 (2026-09-07)

아래 값은 비전팀 내부(gate_cam.py/center_cam.py)에서 확정해 코드에 반영한 제안이다. 관제팀 확인 전까지는 잠정치다.

- 카메라 입력: imgsz=512, YOLO 탐지 confidence 임계값=0.7
- gate 라인 위치: 좌측 라인 비율 0.32, 우측 라인 비율 0.70, ROI 상단 비율 0.45, ROI 하단 비율 0.95 (화면 가로/세로 비율 기준)
- center ROI 좌표: TOP=(0.2, 0.15, 0.62, 0.32), BOTTOM=(0.05, 0.76, 0.7, 1.00) (비율 좌표, x1·y1·x2·y2)
- PARKED 확정 체류시간: 5.0초
- 이벤트 쿨다운: 2.0초 (같은 차량이 이 시간 안에 재발행하지 않도록 방지)
- 연속 프레임 확정 기준: 3프레임 (현재 실측 FPS 약 15 기준 약 0.2초). gate는 라인 통과가 감지된 뒤 반대편에 3프레임 연속 머무는지 재확인한 후 발행하고, center는 PARKED(5초 dwell)에 더해 EXITING도 ROI 이탈이 3프레임 연속 확인돼야 발행한다. 순간적인 좌표 흔들림·오탐으로 인한 오발행을 줄이기 위함이다.
- CameraState.confidence 필드의 의미: 위 확정 절차에 쓰인 프레임들의 평균 conf 값
- 장애 판단 기준: 프레임 읽기가 3초 연속 실패하면 카메라 장애로 로그(ERROR)를 남긴다. 이를 관제·모니터링에 실제로 알리는 전달 경로(별도 토픽 등)는 TBD-IF-008에서 별도로 정한다.
- 트랙 처리 정책: YOLO track_id 기반 다중 트랙 관리를 사용하지 않는다. 차량이 한 대라는 전제(1절)에 따라 매 프레임 confidence가 가장 높은 박스 1개만 차량으로 인정하고 나머지는 무시한다.

## 3. 순찰 허용 조건

| 수신 상태 | patrol_allowed |
|---|---|
| 초기값 | true |
| ENTERING | false |
| PARKED | true |
| EXITING | false |
| EXITED | true |

ENTERING → PARKED는 진입 이벤트 쌍이다. EXITING → EXITED는 독립적인 출차 이벤트 쌍이다. PARKED → EXITING을 필수 연결 전이로 정의하지 않는다. 독립 출차 이벤트를 처리할 수 있어야 한다.

통신 timeout 시 마지막 patrol_allowed 값을 유지하고 시스템 모니터가 경고·로그를 남긴다. 임의로 false로 변경하지 않는다. 단, 이 정책이 token·E-stop 등 별도 안전 게이트를 무효화하지 않는다.

patrol_allowed는 관제 판단 조건이며 AMR에 직접 주행·정지 명령을 발행하지 않는다. 차량 진입을 사람이 직접 제어하므로 vehicle_entry_block 토픽은 만들지 않는다. 관제의 대피·재개 순서는 [integration.md](integration.md)를 따른다.

## 4. 오류와 진단

잘못된 enum, 중복 event_id, 이벤트 미수신, 카메라 입력 상태를 진단할 수 있어야 한다. 로그 항목의 구체적인 필드·전달 경로는 모니터링 및 인터페이스 TBD를 따른다.

늦게 도착한 서로 다른 ID의 이벤트, 순서 역전, cam_master 재시작 후 보존 값·중복 캐시 정책은 TBD-VIS-002다. VOLATILE 설정만으로 모든 과거 이벤트 문제를 해결했다고 간주하지 않는다.

### 4-1. TBD-VIS-002 비전팀 확정안 (2026-09-07)

- 순서 역전: cam_master는 CameraState.header.stamp(실제 감지 시각)를 확인해, 이미 반영한 이벤트 중 가장 최신 시각보다 과거인 이벤트가 나중에 도착하면 폐기한다("과거 사건이 이미 확정된 최신 상태를 뒤집지 못한다"). event_id가 다른 정상 이벤트라도 이 검증을 통과하지 못하면 permit에 반영하지 않는다.
- 늦게 도착한 이벤트: 별도의 지연 임계값(예: N초 이상이면 무조건 폐기)은 두지 않는다. 위 순서 역전 검증 하나로 처리한다.
- cam_master 재시작 시 patrol_allowed: 이전 상태를 복구하지 않고 초기값 True로 초기화한다(3절 초기값 정책과 동일). 영속 저장은 하지 않는다.
- cam_master 재시작 시 event_id 캐시: 영속 저장하지 않고 메모리 상태를 그대로 초기화한다(재시작 직후 과거 event_id 재수신에 대한 별도 방어는 없음).

## 5. 검증

정상 진입 쌍과 독립 출차 쌍, topic별 enum 검증, 중복 제거, timeout 시 마지막 값 유지, 관제 대피·재개 연계를 확인한다. [통합시험 IT-05·06](integration.md#4-통합시험-명세)을 참조한다.

## TBD

| ID | 미정 사항 | 영향 단위 | 상태 |
|---|---|---|---|
| TBD-VIS-001 | CCTV 입력·모델·ROI, 차량 상태 확정 confidence·시간 기준, 장애 판단 | 비전·관제 | OPEN |
| TBD-VIS-002 | 순서 역전·누락·늦은 이벤트, cam_master 재시작 시 상태·캐시 처리 | 비전·관제 | OPEN |

발행 주기와 경고 timeout은 TBD-IF-010, CameraState 계약은 TBD-IF-005에만 정의한다.
