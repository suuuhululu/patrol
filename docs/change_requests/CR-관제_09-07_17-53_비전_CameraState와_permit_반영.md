# [관제] 비전 CameraState와 permit P0 계약 반영

- 상태: 초안
- 최초 작성 시각: 2026-09-07 17:53 KST
- 요청자: 관제
- 요청 단위: 관제
- 대상 단위 및 로봇: 비전(PC 4, gate_cam·center_cam·cam_master)
- 관련 TBD ID: TBD-IF-005, TBD-IF-010, TBD-VIS-001
- 기준 문서·절: [interfaces.md 1.2·6·9절](../interfaces.md), [vision.md 1~5절](../vision.md), [integration.md W-02·IT-05·06](../integration.md)
- 결정 일자·근거: 2026-09-07, 프로젝트 담당자 확정. 개발 과정의 로그 식별성, FPS 변동과 순간 오탐에 무관한 시간 판정, permit 통신 상태 확인을 우선한다.
- 코드 변경 승인 근거·범위: 본 요청서는 비전팀 구현 요청이며 비전 소유 코드의 직접 변경 승인이 아니다. 관제는 `src/patrol_vision/**`와 `docs/vision.md`를 수정하지 않는다. `interfaces.md`와 `src/patrol_interfaces/**`도 이번 작업에서 직접 수정하지 않으며 공용 인터페이스 반영은 별도 승인·합의 후 수행한다.

## 변경 이유

현재 비전 코드는 CameraState event_id에 UUID v4를 사용하고 camera_id를 `GATE`·`CENTER`로 발행하며 source session·sequence 필드를 채우지 않는다. 일반 상태는 실측 FPS를 전제로 3프레임을 확인하고, gate 미검출 프레임은 진행 중 확인을 끊지 않는다. cam_master는 permit을 값 변경 시에만 발행한다.

확정된 P0 계약은 사람이 식별할 수 있는 이벤트 ID, camera_id `gate_cam`·`center_cam`, FPS와 무관한 0.2초 연속 판정, 확정 구간 confidence 평균, permit 5 Hz 반복과 관제 5초 timeout이다. 비전팀 소유 문서와 코드에 이를 반영하고 통합시험으로 확인해야 한다.

## 변경 전 → 변경 후

### 1. 패키지와 CameraState 계약

- 변경 전: 패키지·일부 필드·ID·camera_id·enum 계약이 문서상 TBD이고 구현은 일부 필드만 사용한다.
- 변경 후: 공용 패키지는 `patrol_interfaces` 하나만 사용하고 `parking_interfaces`는 폐기한다. 비전 저장소·설정·문서·package 의존성에 과거 이름이 남아 있으면 모두 `patrol_interfaces`로 바꾼다.

요청하는 CameraState 계약은 다음과 같다. 이는 요청서에 기록한 합의 내용이며 이번 관제 작업에서 `interfaces.md`나 `.msg`를 직접 변경하지 않는다.

~~~text
std_msgs/Header header
string event_id
string camera_id
string source_session_id
uint64 source_sequence
uint8 state
float32 confidence

uint8 STATE_UNKNOWN=0
uint8 STATE_ENTERING=1
uint8 STATE_EXITED=2
uint8 STATE_PARKED=3
uint8 STATE_EXITING=4
~~~

- gate topic의 camera_id는 `gate_cam`, center topic은 `center_cam`이다.
- gate topic 허용 상태는 ENTERING·EXITED, center topic은 PARKED·EXITING이다.
- 다른 상태나 camera_id가 topic과 맞지 않으면 cam_master가 폐기하고 진단 로그를 남긴다.
- `header.stamp`는 이벤트 상태가 확정된 시각이다.

### 2. 이벤트 ID

~~~text
source_session_id = <camera_id>-<YYYYMMDDTHHMMSS>-<restart_sequence>
event_id = cam-<source_session_id>-<state>-<source_sequence>
~~~

예:

~~~text
source_session_id: gate_cam-20260907T175300-01
event_id: cam-gate_cam-20260907T175300-01-entering-0001

source_session_id: center_cam-20260907T175301-01
event_id: cam-center_cam-20260907T175301-01-parked-0001
~~~

- source_sequence는 각 source session에서 1부터 시작해 새 이벤트마다 증가하며 상태가 바뀌어도 초기화하지 않는다.
- 순번 표기는 event_id 안에서 최소 네 자리 0 채움을 사용한다.
- 같은 이벤트를 재전송하면 event_id, source session·sequence, header.stamp와 payload를 유지한다.
- 새 이벤트는 새 source_sequence와 event_id를 사용한다.
- 수신 로직은 event_id 문자열을 파싱하지 않고 별도 필드와 enum을 사용한다.

### 3. 상태 확정과 confidence

- YOLO confidence 임계값 0.7, 기존 ROI·라인·PARKED 5초·이벤트 cooldown 2초·최고 confidence 박스 1개 정책은 유지한다.
- ENTERING·EXITED·EXITING은 프레임 수 대신 `time.monotonic()` 기준으로 유효 조건이 0.2초 연속 유지된 경우 확정한다.
- ROI, 방향, confidence 조건이 깨지거나 미검출 프레임이 발생하면 진행 중인 0.2초 확인을 즉시 초기화한다.
- ENTERING·EXITED·EXITING confidence는 확정에 사용한 유효 0.2초 구간의 평균이다.
- PARKED는 5초 체류를 만족할 때 발행하고 confidence는 확정 직전 마지막 유효 0.2초 구간의 평균이다.

### 4. patrol_allowed

- 메시지 타입과 토픽은 현재처럼 `std_msgs/msg/Bool`, `/vision/cctv/patrol_allowed`를 유지한다.
- 초기 true 및 ENTERING·EXITING=false, PARKED·EXITED=true 매핑을 유지한다.
- 상태가 바뀌면 즉시 발행하고, 바뀌지 않아도 현재 값을 5 Hz로 반복 발행한다.
- QoS는 RELIABLE, VOLATILE, KEEP_LAST(1), deadline 500 ms를 유지한다.
- 관제의 수신 계약은 5초 미수신 시 timeout 경고를 발생시키고 마지막 permit 값을 유지하는 것이다. permit timeout은 비전 event 미발행 timeout과 구분하며, 관제 수신부 구현은 이 비전팀 요청의 코드 변경 범위가 아니다.
- Bool 기반 정상 복구는 동일 값 3회 연속 수신, 각 간격 0.5초 이하, 첫 번째부터 세 번째까지 로컬 monotonic 경과 0.3초 이상을 모두 만족할 때다. 조건이 깨지면 다시 첫 수신부터 센다.
- Bool에는 source session·publish sequence가 없으므로 동일 cam_master 세션과 증가 sequence까지 검증하는 강화안은 P0에 포함하지 않는다. 해당 내용은 [vision_P1.md](../vision_P1.md)의 권장안이다.

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| 비전 | UUID 제거, source session·sequence와 구조화 event ID 생성, camera_id 변경 | `src/patrol_vision/patrol_vision/gate_cam.py`, `_publish_state` 및 초기화 | 비전 |
| 비전 | 3프레임 확인을 monotonic 0.2초로 변경, 미검출·조건 이탈 시 초기화, 유효 구간 confidence 평균 | `gate_cam.py`, `_on_no_detection`, `_on_detection` | 비전 |
| 비전 | 구조화 ID·camera_id, EXITING 0.2초, PARKED 5초와 마지막 0.2초 confidence 평균 | `src/patrol_vision/patrol_vision/center_cam.py`, 초기화·`_on_no_detection`·상태 판정·`_publish_state` | 비전 |
| 비전 | topic-camera_id·enum 검증, 상태 변경 즉시 및 5 Hz permit 반복 발행 | `src/patrol_vision/patrol_vision/cam_master.py`, 이벤트 검증·publisher timer | 비전 |
| 비전 | P0 계약과 기존 확정 설명을 일치시키고 코드별 flowchart 갱신 | `docs/vision.md` 2·3·4·5절 및 gate_cam·center_cam·cam_master flowchart | 비전 |
| 비전 | P0 시간 경계·초기화·ID·confidence·5 Hz 자동 시험 추가 | 기존 비전 테스트 또는 `src/patrol_vision/test/` 신규 테스트 | 비전 |
| 관제 | 해당 없음. 수신 측 5초 timeout·복구는 통합시험의 사전 조건이며 이 요청서의 구현 대상이 아님 | 해당 없음 | 관제 |
| System monitor | 해당 없음. 관제 판단 결과 표시 계약은 TBD-IF-011에서 별도 관리 | 해당 없음 | System monitor |
| AMR | 해당 없음. CameraState를 직접 소비하지 않음 | 해당 없음 | AMR |

## 영향과 적용 순서

1. 비전팀이 공용 CameraState `.msg`의 필드 추가 필요성과 적용 시점을 확인한다.
2. 공용 메시지 변경을 별도 승인해 빌드한 뒤 비전 송신·수신 코드를 같은 버전으로 갱신한다.
3. gate_cam·center_cam 단위시험 후 cam_master의 5 Hz 발행을 확인한다.
4. 별도 범위에서 관제 수신부의 5초 timeout·복구 적용 상태를 확인한다.
5. IT-05·06을 실행해 비전 발행 결과와 관제 수신 결과를 확인한다.

CameraState 필드가 추가되면 구버전 `patrol_interfaces`로 빌드한 노드와 새 노드는 타입 해시가 달라 통신하지 못할 수 있으므로 관련 노드를 함께 재빌드·배포한다. 혼합 버전에서는 주행 재개 시험을 진행하지 않는다. 실패 시 배포 버전을 맞추고 permit 마지막 값을 유지한 상태에서 통합시험을 중단한다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | 검토 대기 | CameraState 직접 소비 없음 | 변경 불필요 확인 |
| AMR / robot6 | 검토 대기 | CameraState 직접 소비 없음 | 변경 불필요 확인 |
| 관제 | 미반영 | P0 계약 확정 | permit 수신 timeout·복구 구현 |
| System monitor | 검토 대기 | 관제 판단 결과 소비 예정 | 표시·기록 경로 확인 |
| 비전 | 미반영 | 본 요청서 | 문서·코드·시험 반영 |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: IT-05, IT-06, IT-07
- CameraState 실제 타입에 요청 필드와 enum이 존재하고 모든 비전 노드가 `patrol_interfaces`로 빌드된다.
- gate_cam·center_cam이 정해진 camera_id, source session·sequence, 구조화 event ID를 발행한다.
- 0.2초 미만·조건 이탈·미검출에서는 일반 상태 이벤트가 발행되지 않고, 0.2초 연속 조건에서 한 번만 발행된다.
- confidence 평균 구간과 PARKED 5초 조건이 경계 시험에서 일치한다.
- permit 상태 변경 즉시 발행과 5 Hz 반복, 5초 timeout, 마지막 값 유지, Bool 기반 정상 복구가 IT-06을 통과한다.
- 실제 실행 결과와 로그: NOT_RUN
- 미실행 또는 BLOCKED 항목: 공용 CameraState 수정 승인·비전 반영·관제 수신부 반영 전 통합시험 BLOCKED

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-07 | 프로젝트 담당자 | 패키지 `patrol_interfaces`, CameraState 필드·camera_id·enum·ID, 0.2초 판정·confidence, permit 5 Hz·5초 timeout 확정 | 사용자 결정 |
| 2026-09-07 | 관제 | 기존 인터페이스·비전 문서와 코드는 직접 수정하지 않고 요청서 및 통합시험 기준으로 전달 | 개발 단위 변경 경계 |
