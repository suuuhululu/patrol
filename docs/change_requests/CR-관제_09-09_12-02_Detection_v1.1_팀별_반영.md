# [관제] Detection v1.1 팀별 반영

- 상태: 요청
- 최초 작성 시각: 2026-09-09 12:02 KST
- 요청자: 관제
- 요청 단위: 관제
- 대상 단위 및 로봇: 비전·AMR·시스템 모니터·관제, robot1·robot6
- 관련 TBD ID: TBD-IF-006, TBD-IF-007, TBD-AMR-001, TBD-AMR-004
- 기준 문서·절: [interfaces.md 1·6.1·9절](../interfaces.md), [integration.md W-06·IT-14·15](../integration.md), [v1.1 기준선](../decisions/2026-09-09-detection-interface-v1.1.md)
- 회신 대상: [AMR 요청서](CR-AMR_09-09_10-52_Detection_재개신호및_v1_잔여확정.md)
- 결정 일자·근거: 2026-09-09 사용자 확정
- 코드 변경 승인 근거·범위: 공용 `patrol_interfaces`와 공용 문서만 관제 측에서 반영 승인. 비전·AMR·시스템 모니터 소유 코드와 세부 문서는 각 팀이 본 요청서에 따라 변경한다.

## 변경 이유

Detection 확정 후 AMR 내부 hold를 끝내는 종결 결과가 없고 Candidate와 Event의 event_type 숫자가 달랐다. `risk_level`은 실제 모델과 운영 분기에 맞지 않았으며, Event·Evidence·Alignment 토픽 namespace와 robot6 하드코딩도 통합 배포를 막는다. 증적 저장 ACK를 AMR 재개의 선행 조건으로 만들면 시스템 모니터나 DB 장애가 주행을 불필요하게 묶으므로 로컬 큐 등록 결과와 저장 ACK를 분리한다.

## 공용 계약 변경 전 → 변경 후

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| event_type | Candidate FIRE=0·LEAK=1·OBSTACLE=2, Event UNKNOWN=0·FIRE=1·LEAK=2·OBSTACLE=3 및 추가 타입 | Candidate·Event 모두 UNKNOWN=0·FIRE=1·LEAK=2·OBSTACLE=3 |
| 위험도 | `DetectionEvent.risk_level`, `RISK_*` | 전부 제거, event_type으로만 판단 |
| 확정 종결 | 별도 메시지 없음 | `DetectionResult`: CONFIRMED=0, VERIFY_FAILED=1, INTERNAL_ERROR=2 |
| 증적 | 구현별 통짜 또는 불명확 | `EvidenceChunk`와 비전 로컬 재전송 큐 |
| 저장 ACK | 발행 주체·재개 연계 불명확 | System monitor가 `/{robot}/ingestion_ack` 발행, AMR 재개와 비동기 |
| namespace | `/robot6/vision/*` 등 혼재·하드코딩 | `/{robot}/detection/{candidate,alignment_status,result,event,evidence}`, 공용 ACK는 `/{robot}/ingestion_ack` |

`DetectionResult`는 `header`, `robot_id`, `candidate_id`, `event_id`, `result`, `detail` 필드를 사용한다. CONFIRMED는 Event와 EvidenceChunk가 로컬 재전송 큐에 등록된 상태이며 `event_id`가 필수다. VERIFY_FAILED는 1초 연속 검증 실패, INTERNAL_ERROR는 비전 처리·인코딩·로컬 큐 등록 오류이며 두 상태의 `event_id`는 빈 문자열이다. `detail`은 사람용 진단이고 제어 분기는 `result`로만 한다.

## 동작 흐름

~~~mermaid
flowchart TD
    V[비전: DetectionCandidate] --> A[AMR: yaw 정렬 및 정지 확인]
    A --> S[AMR: AlignmentStatus]
    S --> Q{비전: 같은 대상 1초 연속 검증}
    Q -->|성공| O[Event와 EvidenceChunk 로컬 큐 등록]
    O --> C[DetectionResult CONFIRMED]
    Q -->|조건 실패| F[DetectionResult VERIFY_FAILED]
    Q -->|처리 또는 큐 오류| E[DetectionResult INTERNAL_ERROR]
    C --> R[AMR 내부 hold 종결 판단]
    F --> R
    E --> R
    O --> M[System monitor: EvidenceChunk 저장]
    M --> K[IngestionAck]
    K -->|INCOMPLETE| O
    K -->|STORED 또는 DUPLICATE| D[비전 로컬 큐 종료]
~~~

위 흐름에서 AMR의 실제 이동은 E-stop·Drive Token·local safety 게이트를 다시 통과해야 한다. System monitor ACK 경로는 증적 보존용이며 `R`의 선행 조건이 아니다.

## 팀별 요청 작업

### 비전 팀

- 비전팀이 개발하는 AMR detecting node를 robot1·robot6 AMR PC에서 실행한다. 속도·회전 명령은 발행하지 않는다.
- `ROBOT_ID=robot6`과 `/robot6/...` 하드코딩을 제거한다. launch에서 `robot_id`와 `/robot1` 또는 `/robot6` namespace를 주입하고 코드에서는 `detection/candidate`, `detection/alignment_status`, `detection/result`, `detection/event`, `detection/evidence`, `ingestion_ack` 상대 이름을 사용한다.
- `DetectionCandidate.event_type`을 UNKNOWN=0·FIRE=1·LEAK=2·OBSTACLE=3으로 변경하고 UNKNOWN은 정상 후보·확정 이벤트로 발행하지 않는다.
- 같은 candidate의 `AlignmentStatus.ALIGNED_COMPLETE`를 받은 뒤 정지 상태가 유지되는 동안 같은 대상을 1초 연속 검증한다. 조건 단절·정렬 상태 해제 시 확인 시간을 초기화한다.
- 성공 시 Event와 EvidenceChunk를 로컬 재전송 큐에 원자적으로 등록한 후 CONFIRMED를 발행한다. 검증 실패는 VERIFY_FAILED, 처리·인코딩·큐 등록 오류는 INTERNAL_ERROR로 종결한다.
- `DetectionEvent`에서 risk_level·RISK_*·LIGHTING·FACILITY_DAMAGE 사용을 제거한다.
- 증적은 `EvidenceChunk`로 분할하고 `IngestionAck`을 구독한다. INCOMPLETE이면 `missing_chunks`만 재전송하고 STORED·DUPLICATE이면 큐 항목을 종료하며 REJECTED는 오류 기록·정책상 재시도 대상으로 처리한다.

### AMR 팀

- `detection/candidate`를 구독하고 같은 candidate ID로 `detection/alignment_status`를 발행하며, `detection/result`를 구독한다. launch namespace와 상대 토픽을 사용한다.
- yaw 회전·정렬·최종 정지는 AMR이 담당한다. 정지 확인 뒤 ALIGNED_COMPLETE를 발행하고 1초 비전 검증 동안 정지를 유지한다.
- 현재 작업의 robot_id·candidate_id와 일치하는 DetectionResult만 수락한다. CONFIRMED는 비어 있지 않은 event_id, VERIFY_FAILED·INTERNAL_ERROR는 빈 event_id만 허용하고 위반 시 폐기·경고한다.
- 유효한 종결 결과로 정렬 hold를 끝내는 것은 AMR 내부 전이다. 새 관제 RESUME_PATROL이나 IngestionAck을 기다리지 않는다. 다만 E-stop·Drive Token 만료/회수·장애물 차단·센서/구동 장애는 즉시 중단하며 자동 재개하지 않는다.
- event_type 숫자 변경을 모든 후보 처리·로그·테스트에 반영하고 risk_level 기반 분기를 추가하지 않는다.
- FIRE 확정 후 기존 합의대로 현재 mission의 순찰·복귀·도킹까지 완료한 뒤 token을 회수하며 다른 로봇에 새 token을 요구하지 않는다. 부저·도킹 종단은 TBD-AMR-004의 기존 정책을 유지한다.

### 시스템 모니터 팀

- `DetectionEvent` 소비부·서비스·DB 매핑·UI·테스트에서 필수 `risk_level`과 `RISK_*` 분기를 제거하고 event_type만으로 저장·표시한다. 기존 DB 컬럼 보존이 필요하면 nullable legacy 컬럼으로 두되 공용 메시지 입력에 요구하지 않는다.
- `/{robot}/detection/event`와 `/{robot}/detection/evidence`를 구독하고 `/{robot}/ingestion_ack`을 System monitor가 발행한다. 현재 맞는 경로도 launch/설정에서 계약값을 재확인한다.
- EvidenceChunk를 evidence_id와 chunk index/count로 중복 제거·조립하고 SHA·크기를 검증한다. 누락은 INCOMPLETE와 missing_chunks, 저장 성공은 STORED, 이미 저장된 동일 엔티티는 DUPLICATE, 검증 불가 데이터는 REJECTED로 응답한다.
- ACK 지연·DB 실패가 DetectionResult나 AMR 재개를 제어하지 않도록 한다.

### 관제 팀

- `/{robot}/detection/event`만 제어 판단 입력으로 소비하고 event_type으로 분기한다. risk_level을 요구하거나 산정하지 않는다.
- AlignmentStatus·DetectionResult·EvidenceChunk·IngestionAck을 중계하거나 AMR 재개 명령으로 변환하지 않는다.
- FIRE=1 확정 시 기존 화재 정책을 적용하고 UNKNOWN=0 또는 미정의 값은 정상 이벤트로 실행하지 않고 경고한다.

## 요청 코드 범위

| 팀 | 필수 검토·수정 경로 | 범위 |
|---|---|---|
| 비전 | `src/patrol_vision/patrol_vision/vision_node.py`, `src/patrol_vision/setup.py`, 신규 `src/patrol_vision/launch/` 및 Detection 테스트 | robot 파라미터·상대 토픽, Alignment 구독, 1초 검증, Result·Event·Evidence 발행, outbox·ACK |
| AMR | `src/patrol_amr/patrol_amr/mission_supervisor.py`, Detection 중재용 신규 모듈·테스트, `src/patrol_amr/launch/patrol.launch.py`, `src/patrol_amr/launch/hardware_patrol.launch.py` | Candidate/Alignment/Result 연결, yaw·정지·hold 종결, launch namespace |
| 시스템 모니터 | `src/patrol_sysmon/app/ros/{registry.py,qos.py,payloads.py,node.py}`, `app/services/{detection_service.py,event_service.py,history_service.py}`, `app/models/{detection.py,event.py,history.py}`, `app/schema.sql`, 관련 templates·JS·testkit·tests | risk 의존 제거, event_type 매핑, EvidenceChunk 조립, ACK 및 화면·DB·시험 갱신 |
| 관제 | `src/patrol_control/`의 향후 DetectionEvent 소비부·테스트 | Event만 소비, event_type 분기, FIRE 정책 연결; Alignment·Result·Evidence·ACK 경로는 구현하지 않음 |

경로 표는 직접 수정 권한을 부여하지 않는다. 공용 `patrol_interfaces` 외에는 각 소유 팀이 수정하고, 소유 문서도 해당 팀이 구현 결과에 맞춰 갱신한다.

## 적용 순서와 호환성

`patrol_interfaces 1.1.0`은 v1.0과 wire 호환되지 않는다. 공용 package 반영 → 네 팀 소비 코드 수정 → 같은 Git commit 빌드 → manifest 일치 확인 → IT-14·15 순서로 적용한다. 일부 팀만 v1.1로 올린 혼합 실행은 금지한다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| 공용 interface | 로컬 빌드·설치 타입 검증 PASS | `patrol_interfaces 1.1.0`, manifest `ed46754623f43db928cb331a61ed4b918989e1bcb979e6cdc5348741837aa617` | 네 팀 동시 배포 |
| 관제 / PC 3 | 문서 반영·코드 대기 | interfaces.md, integration.md | Event 소비부 구현·시험 |
| 비전 / robot1·robot6 | 요청 | 본 요청서 비전 절 | detecting node·launch·outbox·ACK 처리 |
| AMR / robot1·robot6 | 요청 | 본 요청서 AMR 절 | 정렬·Result 소비·내부 hold 종결 |
| 시스템 모니터 / PC 3 | 요청 | 본 요청서 시스템 모니터 절 | risk 제거·Evidence/ACK 종단 반영 |

## 완료 조건과 검증

- 모든 PC에서 `patrol_interfaces 1.1.0`, 메시지 16개, manifest가 기준선과 일치한다.
- `ros2 topic list`에 robot1·robot6별 계약 경로만 있고 `/robot6/vision/*` 또는 중복 절대 경로가 없다.
- IT-14에서 세 DetectionResult 상태, ID·event_id 검증, 1초 판정, 안전 중단, FIRE 종단이 통과한다.
- IT-15에서 청크 누락·중복·순서 변경·DB 실패·복구와 ACK 지연 중 AMR 비차단이 통과한다.
- 실제 실행 결과와 증거: NOT_RUN

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-09 | 사용자·관제 | 3개 DetectionResult, 통일 event_type, risk 제거, EvidenceChunk, System monitor ACK, detection namespace 확정 | 대화 확정 |
