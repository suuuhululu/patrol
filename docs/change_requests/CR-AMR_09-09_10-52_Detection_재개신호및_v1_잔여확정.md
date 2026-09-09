# CR-AMR: Detection 확정 후 재개 신호 및 v1 확정 인터페이스 잔여 결정 사항

- 상태: 초안
- 최초 작성 시각: 2026-09-09 10:52 KST
- 요청자: AMR(Detection/비전 노드 담당)
- 요청 단위: AMR
- 대상 단위 및 로봇: 관제(PC 3), AMR 내부(robot1·robot6) — 항목별로 구분함
- 관련 TBD ID: TBD-AMR-001, TBD-AMR-004, TBD-IF-006, TBD-IF-007
- 기준 문서·절: [amr.md 6절](../amr.md), [interfaces.md 1·TBD절](../interfaces.md), [integration.md W-06·IT-14·15](../integration.md)
- 결정 일자·근거: 미정 — 이 요청서로 결정을 요청하는 단계이며, 아직 합의된 결정 없음.
- 코드 변경 승인 근거·범위: 미승인. 이 요청서는 결정 요청용이며, 코드(`vision_node.py` 등) 변경은 각 항목 결정 후 별도 승인을 받는다.

## 변경 이유

v1 확정 인터페이스(16개 `.msg`)와 `vision_node.py`(robot6 OAK-D Detection 노드) 코드를 대조한 결과, `AlignmentStatus`의 토픽명·QoS는 AMR 측에서 별도로 확정해 전달하기로 했으나, 그 외에 아직 결정되지 않은 항목이 다수 남아 있다. 특히 "이벤트 확정 후 발행을 모두 마쳤을 때 로봇이 순찰(또는 정렬 회전)을 재개하는 신호"는 v1 `.msg` 어디에도, `interfaces.md`·`amr.md`·`integration.md` 어디에도 정의돼 있지 않다. `amr.md` 6절의 설계 의도(`mission_supervisor`가 yaw 정렬을 수행)로 미루어 볼 때 이건 AMR 내부(노드 분할 여부에 따른) 문제로 보이지만, 실제 노드 분할이 확정되지 않아(`amr.md` 1절 "기능 구분은 실제 ROS 노드 분할을 확정하지 않는다") 명확한 결정이 필요하다. 이와 함께 정리된 나머지 잔여 항목도 함께 결정을 요청한다.

## 변경 전 → 변경 후

아직 "변경"이 합의된 상태가 아니므로, 항목별 현재 상태와 결정이 필요한 선택지를 정리한다. 최종 결정은 검토·결정 이력에 기록한다.

### 1. Detection 확정 후 재개 신호

- 현재 상태: `vision_node.py`는 이벤트 확정·발행 후 `reset_candidate()`로 `SEARCHING` 상태로 돌아가고 `DetectionCandidate` 발행을 멈출 뿐, 회전/순찰을 재개시키는 명시적 신호를 보내지 않는다.
- 결정 필요 사항: (a) 정렬 제어와 Detection이 같은 프로세스(`mission_supervisor` 내부 함수 호출)인지, (b) 서로 다른 프로세스라면 어떤 토픽/신호로 "재개해도 된다"를 전달할지, (c) 그 신호가 `DetectionEvent`+증적 로컬 발행 완료 시점 기준인지, 관제로부터의 `IngestionAck`(저장 확인) 수신 후인지.

### 2. `DetectionCandidate`/`DetectionEvent`/`DetectionEvidence` 공식 토픽명·QoS

- 현재 상태: `/robot6/vision/detection_candidate` 등은 코드에 임의로 정한 값이며 `interfaces.md` 1절엔 TBD로만 표시.
- 결정 필요 사항: 공식 토픽명, QoS(현재 코드는 candidate BEST_EFFORT depth1 / event·evidence RELIABLE depth10 사용 중)를 AMR·관제 합의로 확정.

### 3. 증적 전송 방식: `DetectionEvidence` 통짜 vs `EvidenceChunk` 분할

- 현재 상태: `vision_node.py`는 이미지 전체를 `DetectionEvidence` 하나에 담아 발행. `EvidenceChunk`(`chunk_index`/`chunk_count`/`sha256`)와 `IngestionAck`(`missing_chunks`)가 별도로 확정 인터페이스에 존재.
- 결정 필요 사항: 관제가 실제로 청크 방식 수신·재전송 확인을 요구하는지, 아니면 통짜 발행이 v1 최종 방식인지.

### 4. `IngestionAck` 처리 여부

- 현재 상태: `vision_node.py`는 `IngestionAck`를 구독하지 않음.
- 결정 필요 사항: 3번이 청크 방식으로 정해질 경우, 관제의 `STORED`/`DUPLICATE`/`INCOMPLETE`/`REJECTED` 및 `missing_chunks` 응답을 받아 재전송하는 로직을 AMR이 구현할지.

### 5. `DetectionEvent.risk_level` 채움 주체

- 현재 상태: 항상 `RISK_UNKNOWN` 고정 발행.
- 결정 필요 사항: AMR이 event_type·confidence 기반으로 자체 산정할지, 관제가 별도로 판정할지, v1에서는 UNKNOWN 고정을 유지할지.

### 6. `LIGHTING`·`FACILITY_DAMAGE` 이벤트 담당

- 현재 상태: 현재 YOLO 모델은 fire/leak/obstacle 3종만 학습, 나머지 2종은 이 노드가 생성 불가.
- 결정 필요 사항: 다른 노드/모델이 담당하는지, v1 범위에서 제외하는지.

### 7. robot1용 배포 사본

- 현재 상태: `ROBOT_ID`와 토픽 문자열 4곳(`CAMERA_TOPIC`/`CANDIDATE_TOPIC`/`EVENT_TOPIC`/`EVIDENCE_TOPIC`)이 robot6으로 하드코딩.
- 결정 필요 사항: 2번 항목(토픽명 확정) 이후 robot1용 사본을 만드는 절차와 승인 범위.

### 8. 정렬·탐지 임계값 공식 합의

- 현재 상태: `ALIGNMENT_TOLERANCE`(0.05), `ALIGNMENT_STABLE_SEC`(0.5초), `VERIFY_DURATION_SEC`(1초), `VERIFY_MAX_FRAME_GAP_SEC`(0.3초), `CANDIDATE_WINDOW_SEC`(0.3초)/`CANDIDATE_MIN_HITS`(2), `DEDUP_HASH_DISTANCE`(10) 등이 코드에 로컬 상수로만 존재.
- 결정 필요 사항: TBD-AMR-001 해결 시 이 값들을 기준으로 채택할지, 로봇별로 다르게 둘지(설치 위치·카메라 화각 차이 고려).

### 9. 화재 부저 노드의 `DetectionEvent` 구독 여부

- 현재 상태: 부저 제어 노드·구독 구조 불명.
- 결정 필요 사항: 부저 노드가 `DetectionEvent`(`event_type=FIRE`)를 직접 구독하는 구조로 할지, 별도 신호가 필요한지(TBD-AMR-004).

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| AMR | 1·7·8·9번 항목의 내부 설계 결정(노드 분할 여부, 임계값 확정, 부저 구독 구조) | `vision_node.py`, mission_supervisor(별도 파일 미제공) | AMR |
| 관제 | 2·3·4·5번 항목의 토픽명·QoS·증적 전송 방식·risk_level 처리 확정, `interfaces.md` TBD-IF-006·007 갱신 | `docs/interfaces.md`, 관제 수신부 설계 | 관제 |
| 비전 | 해당 없음. CCTV 차량 이벤트와 별개 파이프라인 | 해당 없음 | 비전 |

## 영향과 적용 순서

1. 1번(재개 신호)과 7번(robot1 배포)은 AMR 내부 결정이라 관제 승인 없이도 진행 가능하지만, 2번(토픽명) 확정 전에 7번을 먼저 진행하면 이중 작업이 발생하므로 2번을 먼저 정하는 순서를 권장한다.
2. 2·3·4번은 서로 연결돼 있다 — 3번(전송 방식)이 청크로 정해지면 2번 QoS와 4번(IngestionAck 처리) 구현 범위가 같이 바뀐다.
3. 아직 어떤 항목도 코드에 반영되지 않았으므로 현재 혼합 버전 문제는 없다. 결정 후 코드 반영 시 관련 노드(비전 Detection, 관제 수신부)를 함께 갱신해야 한다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | 미반영 | | 2번 확정 후 배포 사본 생성(7번) |
| AMR / robot6 | 미반영 | | 1·8·9번 내부 결정 필요 |
| 관제 | 미반영 | | 2·3·4·5번 결정 및 `interfaces.md` 갱신 |
| 비전 | 해당 없음 | CCTV 파이프라인과 무관 | 없음 |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: IT-14(Detection·화재), IT-15(증적·DB)
- 추가 시험·기대 결과: 결정 완료 후 별도 정의
- 실제 실행 결과와 증거: NOT_RUN
- 미실행 또는 BLOCKED 항목: 9개 항목 전부 결정 전이라 IT-14·15는 BLOCKED

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-09 | AMR | 요청서 초안 작성, 9개 항목 결정 요청 | v1 `.msg`·코드 대조 결과 |
