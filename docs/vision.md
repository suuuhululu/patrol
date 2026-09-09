# CCTV 비전 기능 설계

상태: patrol_interfaces v1.0 적용 · 실제 PC 간 통합시험 미실시 · 담당: 비전(PC 4) · 공통 계약: [interfaces.md](interfaces.md)

## 1. 책임

PC 4는 Gate/Center CCTV를 처리해 차량 상태 이벤트를 생성하고 cam_master가 patrol_allowed를 계산한다. 차량은 한 대만 존재한다. AMR OAK-D 기반 Detection·yaw 정렬·증적 생성은 [amr.md](amr.md)의 책임이다.

| 기능 | 발행 또는 수신 | 허용 상태 |
|---|---|---|
| gate_cam | /vision/cctv/gate_event 발행 | ENTERING, EXITED |
| center_cam | /vision/cctv/center_event 발행 | PARKED, EXITING |
| cam_master | 두 이벤트 구독, /vision/cctv/patrol_allowed 발행 | Bool |

PC 4 ROS 참여자는 PC 3 Offboard Discovery Server의 Client다. 구체적 CCTV 장치·모델·배포·확정 기준은 2-1절에서 확정했다.

## 2. 이벤트 처리

CameraState 필드는 interfaces.md 6절을 따른다. vehicle_track_id는 제거된 항목이다. topic별로 허용되지 않은 enum 또는 camera_id는 폐기하고 진단 로그를 남긴다(문서 하단 CR 반영 내역, cam_master가 topic-camera_id 일치도 함께 검증한다).

cam_master는 event_id를 Q-13 동안 보관해 같은 이벤트를 한 번만 처리한다. CCTV 이벤트는 RELIABLE/VOLATILE이며 과거 이벤트 재생을 위해 TRANSIENT_LOCAL을 사용하지 않는다. v1.0의 CameraState는 UNKNOWN=0, ENTERING=1, EXITED=2, PARKED=3, EXITING=4이며 ID 생성·camera_id 규칙은 문서 하단 CR 반영 내역을 따른다.

confidence 필드는 존재하며, 차량 상태 확정에 쓰인 유효 구간(문서 하단 CR 반영 내역 참조)의 평균 conf를 담는다. AMR Detection의 1초 의도를 CCTV에 적용하지 않는다.

### 2-1. 카메라 입력·확정 기준 (확정, 2026-09-07)

프로젝트 담당자 확정. gate_cam.py/center_cam.py에 반영돼 있다.

- 카메라 입력: imgsz=512, YOLO 탐지 confidence 임계값=0.7
- gate 라인 위치: 좌측 라인 비율 0.32, 우측 라인 비율 0.70, ROI 상단 비율 0.45, ROI 하단 비율 0.95 (화면 가로/세로 비율 기준)
- center ROI 좌표: TOP=(0.2, 0.15, 0.62, 0.32), BOTTOM=(0.05, 0.76, 0.7, 1.00) (비율 좌표, x1·y1·x2·y2)
- PARKED 확정 체류시간: 5.0초
- 이벤트 쿨다운: 2.0초 (같은 차량이 이 시간 안에 재발행하지 않도록 방지)
- 연속 상태 확정 기준: 0.2초(monotonic 연속 유지, 문서 하단 CR 반영 내역)
- CameraState.confidence 필드의 의미: 위 확정 절차에 쓰인 유효 구간 프레임들의 평균 conf 값(문서 하단 CR 반영 내역 참조)
- 장애 판단 기준: 프레임 읽기가 3초 연속 실패하면 카메라 장애로 로그(ERROR)를 남긴다. 이를 관제·시스템 모니터에 실제로 알리는 공용 전달 경로는 차기 버전 TBD-IF-010에서 정한다.
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

cam_master는 patrol_allowed가 바뀌면 즉시 발행하고, 바뀌지 않아도 5Hz로 현재 값을 반복 발행한다(문서 하단 CR 반영 내역, CR-관제_09-07_17-53_비전_CameraState와_permit_반영 4절). 통신 timeout 시 관제가 5초 기준으로 경고를 판단하고 마지막 patrol_allowed 값을 유지하며, 시스템 모니터는 관제가 제공한 판단 결과만 표시·기록한다. 임의로 false로 변경하지 않는다. 단, 이 정책이 token·E-stop 등 별도 안전 게이트를 무효화하지 않는다.

patrol_allowed는 관제 판단 조건이며 AMR에 직접 주행·정지 명령을 발행하지 않는다. 차량 진입을 사람이 직접 제어하므로 vehicle_entry_block 토픽은 만들지 않는다. 관제의 대피·재개 순서는 [integration.md](integration.md)를 따른다.

## 4. 오류와 진단

잘못된 enum, 잘못된 camera_id(topic 불일치), 중복 event_id, 이벤트 미수신, 카메라 입력 상태를 진단할 수 있어야 한다. cam_master는 gate_event 토픽에서는 `camera_id == 'gate_cam'`, center_event 토픽에서는 `camera_id == 'center_cam'`만 수락하고 그 외는 폐기·경고 로그를 남긴다(문서 하단 CR 반영 내역). 로그 항목의 구체적인 필드·전달 경로는 모니터링 및 인터페이스 TBD를 따른다.

늦게 도착한 서로 다른 ID의 이벤트, 순서 역전, cam_master 재시작 후 보존 값·중복 캐시 정책은 4-1절에서 확정했다. VOLATILE 설정만으로 모든 과거 이벤트 문제를 해결했다고 간주하지 않는다.

### 4-1. 순서 역전·재시작 정책 (확정, 2026-09-07)

- 순서 역전: cam_master는 CameraState.header.stamp(실제 감지 시각)를 확인해, 이미 반영한 이벤트 중 가장 최신 시각보다 과거인 이벤트가 나중에 도착하면 폐기한다("과거 사건이 이미 확정된 최신 상태를 뒤집지 못한다"). event_id가 다른 정상 이벤트라도 이 검증을 통과하지 못하면 permit에 반영하지 않는다.
- 늦게 도착한 이벤트: 별도의 지연 임계값(예: N초 이상이면 무조건 폐기)은 두지 않는다. 위 순서 역전 검증 하나로 처리한다.
- cam_master 재시작 시 patrol_allowed: 이전 상태를 복구하지 않고 초기값 True로 초기화한다(3절 초기값 정책과 동일). 영속 저장은 하지 않는다.
- cam_master 재시작 시 event_id 캐시: 영속 저장하지 않고 메모리 상태를 그대로 초기화한다(재시작 직후 과거 event_id 재수신에 대한 별도 방어는 없음).
- gate_cam/center_cam의 `restart_sequence`는 이 원칙과 별개다(문서 하단 CR 반영 내역 참조) — patrol_allowed 판단에 관여하지 않는 진단용 값이라 가벼운 로컬 파일 카운터로 영속화한다.

## 5. 검증

정상 진입 쌍과 독립 출차 쌍, topic별 enum·camera_id 검증, 중복 제거, timeout 시 마지막 값 유지, 관제 대피·재개 연계를 확인한다. [통합시험 IT-05·06](integration.md#4-통합시험-명세)을 참조한다.

v1.0 호환 자동 시험은 `src/patrol_vision/test/test_p0_camerastate.py`에 있다. 현재 2개 시험은 CameraState enum 0~4, camera ID, topic별 허용 상태, patrol_allowed 매핑과 5 Hz 상수를 확인한다. event_id·source_session_id 생성, restart_sequence, 0.2초 실측 경계, topic-camera_id 거부, 순서 역전과 실제 프레임 처리는 이 시험 범위 밖이며 IT-05·06·07에서 확인한다.

## TBD

TBD-VIS-001(카메라 입력·확정 기준·장애 판단)과 TBD-VIS-002(순서 역전·재시작 정책)는 2026-09-07 확정되어 각각 2-1절·4-1절 본문에 반영됐다. 비전 내부 TBD는 없지만 카메라 장애의 공용 전달은 차기 버전 TBD-IF-010이다.

CameraState 패키지·필드·enum·event_id·camera_id·QoS는 v1.0으로 확정됐다. permit 5 Hz와 관제 5초 timeout도 CR-관제_09-07_17-53_비전_CameraState와_permit_반영에 따라 v1.0에 포함한다. 카메라 장애 공용 전달 경로와 TBD-IF-010의 다른 단위 세부 항목은 차기 버전이다.

## CR 반영 내역: CR-관제_09-07_17-53_비전_CameraState와_permit_반영 (2026-09-07)

| 항목 | 코드 위치 | 반영 값 |
|---|---|---|
| camera_id | gate_cam.py / center_cam.py `_publish_state` | `gate_cam` / `center_cam` (과거 `GATE`/`CENTER` 폐기) |
| event_id | 위 파일 `build_event_id()` | `cam-<source_session_id>-<state소문자>-<source_sequence 4자리>` |
| source_session_id | 위 파일 `build_source_session_id()` | `<camera_id>-<YYYYMMDDTHHMMSS>-<restart_sequence 2자리>` |
| restart_sequence | 위 파일 `load_and_bump_restart_sequence()` | 노드별 로컬 카운터 파일에서 +1, 없거나 손상 시 1 |
| 확정 기준 | 위 파일 `_on_detection`/`_on_no_detection` | `CONFIRM_SECONDS=0.2`, `time.monotonic()` 연속 유지. 미검출·조건 이탈 시 즉시 초기화(PARKED 5초 dwell 제외) |
| confidence | 위 파일 `_publish_state` | ENTERING/EXITED/EXITING: 0.2초 구간 평균, PARKED: 마지막 0.2초 구간 평균 |
| topic-camera_id 검증 | cam_master.py `_handle_event` | 불일치 시 폐기 |
| patrol_allowed 발행 | cam_master.py `_republish_patrol_allowed` | 변경 즉시 발행 + 5Hz(`PATROL_ALLOWED_PUBLISH_HZ=5.0`) 반복 발행 |
| CameraState 필드 | `patrol_interfaces/msg/CameraState.msg` | `source_session_id`(string), `source_sequence`(uint64) 추가 |

관제 수신부(5초 timeout, Bool 3회 연속 수신 기반 복구)는 이번 반영에 포함하지 않음(관제 담당).
