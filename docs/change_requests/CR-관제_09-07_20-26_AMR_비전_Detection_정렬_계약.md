# [관제] AMR 비전 Detection과 yaw 정렬 계약

- 상태: 초안
- 최초 작성 시각: 2026-09-07 20:26 KST
- 요청자: 관제
- 요청 단위: 관제
- 대상 단위 및 로봇: 비전 detecting node, AMR / robot1·robot6
- 관련 TBD ID: TBD-AMR-001, TBD-AMR-006, TBD-IF-006, TBD-IF-007, TBD-IF-009
- 기준 문서·절: [integration.md W-06·IT-14·16](../integration.md), [amr.md 3·6절](../amr.md), [interfaces.md 1·9절](../interfaces.md)
- 결정 일자·근거: 2026-09-07, 프로젝트 담당자 결정. 영상 판단과 로봇 구동의 책임을 분리하고 정렬된 정지 상태에서 탐지를 확정한다.
- 코드 변경 승인 근거·범위: 본 문서는 비전·AMR 팀에 대한 수정 요청이다. 관제는 `src/patrol_vision/**`, AMR 코드, `docs/vision.md`, `docs/amr.md`, `docs/interfaces.md`와 공용 메시지 파일을 직접 수정하지 않는다. 실제 코드·인터페이스 변경은 각 담당 단위 검토와 별도 승인 후 수행한다.

## 변경 이유

기존 문서에는 AMR 영상 후보, yaw 정렬, 정렬 상태 1초 탐지라는 흐름만 있고 detecting node 개발 담당, 정렬 완료 통지 방향, 중단 정책과 감지 확정 조건이 정해지지 않았다. 비전 detecting node가 직접 회전을 수행하면 AMR의 local_safety_supervisor와 최종 속도 발행 경계를 우회할 가능성도 있다.

개발 책임과 실행 위치를 분리하고, 비전은 수동 탐지, AMR은 회전·정렬, 비전은 정렬 완료 통지를 받은 뒤 1초 연속 탐지로 DetectionEvent를 확정하도록 계약한다.

## 확정된 변경 계약

### 1. 개발·실행 책임

| 항목 | 확정 책임 |
|---|---|
| AMR 탑재 카메라 detecting node 개발·유지보수 | 비전팀 |
| detecting node 실제 실행 | robot1·robot6의 각 AMR PC |
| 영상 추론·DetectionCandidate 생성 | 비전 detecting node |
| yaw 회전·정렬·정지 확인 | AMR |
| 최종 속도 출력과 안전 차단 | AMR local_safety_supervisor |
| DetectionEvent 생성·발행 로직 개발 | 비전팀 |
| DetectionEvent 실제 발행 프로세스 | 각 AMR PC에서 실행되는 detecting node |

detecting node는 수동적인 영상 탐지만 수행한다. `cmd_vel`, Nav2 goal 또는 로봇 회전 명령을 직접 발행하지 않는다. AMR은 후보 정보를 받아 yaw 후보 속도를 계산하고 local_safety_supervisor를 통해서만 구동한다.

### 2. 정렬·확정 흐름

1. detecting node가 영상에서 대상을 탐지하고 candidate 식별자, event type 후보, confidence와 수평 정렬 오차를 AMR에 제공한다.
2. AMR은 하나의 candidate를 현재 정렬 대상으로 고정하고 yaw 정렬을 시작한다.
3. 정렬 중 detecting node는 후보 정보를 갱신하지만 직접 회전하거나 정렬 완료를 판정하지 않는다.
4. AMR은 목표 정렬 오차를 충족한 상태에서 실제 정지를 확인한다.
5. AMR이 같은 candidate 식별자를 포함한 정렬 완료 상태를 detecting node에 전달한다.
6. AMR은 정렬 완료 통지 후 탐지 확인 동안 정지 상태를 유지한다.
7. detecting node는 정렬 완료된 같은 candidate가 1.0초 연속 유효하게 탐지되면 DetectionEvent를 한 번 확정한다.
8. detecting node가 확정 또는 확인 실패 결과를 반환하면 AMR이 정렬 작업을 종료한다. 이후 주행 재개 여부는 AMR mission·안전 상태에 따른다.

AMR의 정지 확인 기준은 기존 실제 정지 기준을 재사용한다.

- odometry 선속도 절댓값 ≤ 0.05 m/s
- odometry 각속도 절댓값 ≤ 0.1 rad/s
- 두 조건을 0.5초 연속 유지
- odometry 측정 age ≤ 0.5초

정렬 완료는 목표 정렬 오차와 위 정지 조건을 모두 만족해야 한다. 목표 정렬 오차, yaw 속도·가속도와 최대 정렬 시간은 AMR팀이 제시하고 비전팀의 영상 오차 단위와 함께 검토한다.

### 3. 1초 감지 확정 조건

- 시간은 detecting node의 `time.monotonic()` 또는 이에 준하는 monotonic clock으로 측정한다.
- 시작점은 같은 candidate에 대한 AMR 정렬 완료 메시지를 유효하게 수신한 시점이다.
- 정렬 완료 상태, 동일 대상 조건, event type별 confidence 임계값을 모두 1.0초 연속 만족해야 한다.
- 1.0초 확인 중 한 프레임이라도 대상 미검출, 동일 대상 조건 불충족, confidence 임계값 미달 또는 정렬 완료 상태 해제가 발생하면 확인 시간을 0으로 초기화하고 DetectionEvent를 발행하지 않는다.
- 재확인은 AMR이 동일 또는 새 candidate에 대해 유효한 정렬 완료 상태를 다시 제공한 뒤 시작한다.
- confidence 필드는 확정에 사용한 유효 1.0초 구간의 평균으로 한다.
- 같은 확정 건은 DetectionEvent를 한 번만 생성한다. 재전송 시 기존 event_id와 payload를 유지한다.
- event type별 confidence 임계값, 동일 대상 판정, bbox/ROI 조건과 재발행 cooldown은 비전팀이 수치와 근거를 제시하고 합의 후 적용한다.

### 4. 정렬 중 중단 정책

정렬을 시작하면 다음 일반 입력만으로 현재 정렬 대상을 취소하거나 다른 candidate로 교체하지 않는다.

- 일반 MissionCommand 변경
- CCTV permit 반전
- 우선순위가 같거나 낮은 새 DetectionCandidate
- 동일 후보의 일시적인 confidence 변동

다만 아래 독립 안전 계층은 정렬 중단 금지보다 항상 우선한다.

- E-stop 활성
- Drive Token 만료 또는 회수
- local_safety_supervisor의 장애물 차단
- odometry·카메라·센서 또는 구동계 장애로 안전한 회전·정지 확인이 불가능한 경우

안전 원인이 발생하면 AMR은 yaw 정렬을 즉시 중단하고 안전 정지한 뒤 중단 상태를 detecting node에 전달한다. detecting node는 진행 중인 1초 확인을 폐기한다. 안전 원인이 사라져도 정렬이나 확인을 자동 재개하지 않으며 새 유효 절차를 시작해야 한다.

후보가 장시간 사라지는 경우의 정렬 실패 timeout은 무한 회전을 막기 위한 안전 관련 값이므로 AMR팀이 최대 정렬 시간과 함께 제시한다. 이는 일반 입력에 의한 임의 중단과 구분한다.

### 5. DetectionEvent 계약 요청

기존에 확정한 ID 규칙은 유지한다.

~~~text
det-<robot_session>-<event_type>-<sequence>
~~~

- 동일 이벤트 재전송은 같은 event_id와 payload를 사용한다.
- 새 확정 이벤트에는 증가한 sequence와 새 event_id를 사용한다.
- 발행자 재시작 시 robot/source session을 변경한다.
- event_id는 추적·중복 제거용이며 수신자가 문자열을 파싱해 제어하지 않는다.

DetectionEvent에는 severity enum과 severity 필드를 만들지 않는다. 화재의 `FIRE_DETECTED=702`는 관제 reason code이며 DetectionEvent event_type 값으로 재사용하지 않는다.

비전팀은 실제 모델 클래스와 운영 대상에 맞는 `event_type` 이름·정수값·confidence 임계값을 제시해야 한다. 구현하지 않는 클래스를 미리 enum에 포함하지 않고, `UNKNOWN=0` 포함 여부와 미지원 클래스 처리도 함께 제시한다. 관제·AMR·시스템 모니터가 검토하기 전에는 enum 수치를 구현 계약으로 확정하지 않는다.

비전팀이 제시할 DetectionEvent 필드 초안에는 최소한 다음 의미가 포함되어야 한다.

~~~text
std_msgs/Header header
string event_id
string source_session_id
uint64 source_sequence
string robot_id
string mission_id
string command_id
uint8 event_type
float32 confidence
string evidence_id
~~~

추가로 다음을 함께 제시한다.

- `header.stamp`의 의미: 최초 후보 시각과 최종 확정 시각 중 무엇인지
- mission·command가 없을 때 빈 문자열 허용 여부
- evidence가 여러 개인 경우 필드 또는 연결 방식
- topic 이름과 namespace
- QoS, 중복 ID 보관 기간, ACK·재전송 여부
- 노드 재시작 후 중복·이전 session 처리

### 6. Candidate·정렬 상태 내부 계약 요청

DetectionCandidate와 AMR→detecting node 정렬 상태는 AMR 내부 연계이지만 서로 다른 개발팀이 구현하므로 메시지 또는 service/action 계약이 필요하다. 최초 초안의 작성 책임은 다음과 같이 나눈다.

- 비전팀은 DetectionCandidate와 DetectionEvent 초안을 작성한다.
- AMR팀은 AMR→detecting node 정렬 상태·완료·중단 통지 초안을 작성한다.
- 비전팀은 정렬 완료 후 1초 확인의 성공·실패 결과 초안을 작성하고 발행한다.
- 양 팀은 각 초안을 함께 검토해 아래 상관관계와 QoS·timeout·상태 전이를 최종 합의한다.

candidate_id는 비전 detecting node가 후보를 처음 생성할 때 발급하고 후보 추적·yaw 정렬·1초 확인이 끝날 때까지 유지한다. AMR은 candidate_id를 변경하거나 새로 만들지 않고 정렬 상태와 완료·중단 통지에 받은 값을 그대로 돌려준다. 정확한 candidate_id 문자열 형식과 후보 종료·재생성 조건은 비전팀이 제시한다. 수신자는 candidate_id 문자열을 파싱해 제어하지 않는다.

최소 계약은 다음 상관관계를 만족해야 한다.

- robot_id와 candidate_id
- event type 후보와 confidence
- bbox 중심 또는 정규화된 수평 오차 및 오차 단위
- 측정 시각과 데이터 age
- 정렬 상태: 정렬 중, 정렬 완료, 확인 완료, 실패·안전 중단을 구분할 수 있는 의미
- 정렬 완료·실패가 어느 candidate에 대한 결과인지 확인할 필드
- 갱신 주기, timeout, QoS 또는 action feedback/cancel 의미

비전팀의 1초 확인 결과에는 최소한 candidate_id와 성공·실패 상태를 포함하고, 성공이면 생성한 event_id를 함께 제공한다. 실패이면 탐지 단절, confidence 미달, 정렬 상태 해제 등 원인을 구분할 수 있어야 한다. AMR은 이 결과를 받아 정렬 정지 유지 상태를 종료하되, 주행 재개 여부를 직접 추정하지 않고 현재 mission·안전 상태를 다시 확인한다.

증적 원본·bbox 표시 이미지와 evidence_id는 비전 detecting node가 생성한다. 비전팀은 DetectionEvent와 증적의 연결 메타데이터 및 전송 요청을 생산하고, System monitor는 합의된 전송 계약에 따라 수신·저장·조회한다. 증적 생성·전송 실패가 DetectionEvent 자체의 발행을 막지 않도록 하고 실패 상태를 별도로 전달한다. 저장 경로·전송 ACK·재전송은 TBD-IF-007에서 확정한다.

메시지명·토픽명·enum 정수값은 본 요청서에서 임의로 확정하지 않는다. 비전·AMR 공동 제시 후 TBD-IF-006·009에 반영한다.

## 팀별 요청 작업

### 비전팀 요청

- `src/patrol_vision/` 아래에 robot1·robot6이 공통으로 사용할 detecting node 신규 모듈, 실행 entry point, launch/config 경로를 제시하고 구현한다.
- detecting node는 영상 추론과 수동 탐지만 수행하며 속도·Nav2·회전 명령을 발행하지 않는다.
- DetectionCandidate의 최초 계약을 작성하고 candidate_id를 생성·유지·종료한다.
- AMR의 정렬 상태를 수신해 같은 candidate인지 검증하고, 정렬 완료 후 1초 연속 탐지를 수행한다.
- 1초 확인 성공·실패 결과를 AMR에 발행하고 성공 시 DetectionEvent의 event_id를 연결한다.
- DetectionEvent 계약과 발행을 구현하되 severity enum·필드를 만들지 않는다.
- 실제 모델을 기준으로 event_type enum, 종류별 confidence, 동일 대상, ROI, 후보 종료·재생성, 이벤트 cooldown을 제시한다.
- 증적 이미지·evidence_id·DetectionEvent 연결 메타데이터를 생성하고 전송 실패 상태를 제공한다.
- 입력 → Candidate → 정렬 상태 수신 → 1초 확인 → Event·증적 또는 실패 흐름의 코드별 flowchart를 `docs/vision.md` 또는 비전팀 합의 문서에 작성한다.

### AMR팀 요청

- 비전팀 DetectionCandidate를 구독하고 받은 candidate_id를 현재 정렬 대상으로 고정한다.
- yaw 속도·가속도, 정렬 오차, 최대 정렬 시간, 후보 소실 실패 기준을 제시한다.
- yaw 후보 속도를 local_safety_supervisor에 연결하고 detecting node나 정렬 모듈이 최종 속도를 직접 발행하지 않도록 한다.
- 목표 정렬 오차와 실제 정지 조건을 모두 만족한 뒤 같은 candidate_id로 정렬 완료를 통지한다.
- AMR→detecting node 정렬 중·완료·실패·안전 중단 상태 계약의 최초 초안을 작성한다.
- 정렬 완료 뒤 비전의 1초 확인 결과가 올 때까지 정지 상태를 유지하고, 결과 수신 후 mission·안전 조건에 따라 다음 동작을 결정한다.
- 일반 MissionCommand·permit 반전·새 후보는 진행 중 정렬을 취소·교체하지 않도록 보류하고, 독립 안전 원인은 즉시 정렬 중단·정지 후 통지한다.
- candidate 수신 → yaw → 정렬·정지 확인 → 완료 통지 → 비전 결과 대기 → 종료·안전 중단 흐름의 코드별 flowchart를 `docs/amr.md`에 작성한다.

### 비전·AMR 공동 합의

- DetectionCandidate, Alignment 상태, 1초 확인 결과의 필드·topic·방식(message/service/action)·QoS·갱신 주기·timeout을 합의한다.
- candidate_id가 후보 생성부터 DetectionEvent 또는 실패까지 양방향 메시지에서 동일하게 유지되는지 확인한다.
- 영상 수평 오차의 단위·부호·허용 범위와 AMR yaw 제어 입력의 변환 기준을 합의한다.
- 노드 재시작, 메시지 역순·중복·누락, 후보 소실, timeout과 안전 중단 상태 전이를 합의한다.
- 공용 메시지가 필요하면 `patrol_interfaces` 변경안을 작성하고 별도 승인을 받은 뒤 양 팀이 동일 버전으로 적용한다.

### 관제·System monitor 영향

- 관제는 확정 DetectionEvent의 event_type을 소비하고 기존 화재 mission·token·도킹 정책에 연결한다. 이는 본 요청서의 비전·AMR 코드 구현 범위가 아니다.
- System monitor는 DetectionEvent와 증적 전송 계약이 확정되면 수신·저장·표시한다. event_type을 다시 판정하거나 yaw 정렬을 제어하지 않는다.
- 두 단위는 비전팀 event_type·DetectionEvent 초안과 증적 계약을 검토하되 비전·AMR 내부 정렬 상태를 재구현하지 않는다.

## 영향과 적용 순서

1. 비전팀이 event_type과 detecting node·DetectionEvent 초안을 제시한다.
2. AMR팀이 yaw 제어 수치와 Candidate·정렬 상태 연계안을 제시한다.
3. 비전·AMR이 candidate 상관관계, 단위, 주기, timeout과 실패 상태를 맞춘다.
4. 공용 메시지 변경이 필요한 경우 별도 승인을 받고 동일 버전의 `patrol_interfaces`를 양쪽에 배포한다.
5. detecting node 단위시험과 AMR yaw 모의시험을 각각 통과한 뒤 robot1·robot6에 배포한다.
6. integration.md IT-14·16을 안전한 시험 환경에서 수행한다.

혼합 버전에서는 candidate와 정렬 완료가 잘못 연결될 수 있으므로 실제 yaw 시험을 진행하지 않는다. 인터페이스 불일치나 상태 상관관계 오류가 발생하면 AMR을 정지시키고 해당 정렬을 실패 처리하며 자동 재개하지 않는다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | 미반영 | 본 요청서 | yaw·정지·통지·안전 중재안 제시 및 구현 |
| AMR / robot6 | 미반영 | 본 요청서 | yaw·정지·통지·안전 중재안 제시 및 구현 |
| 관제 | 검토 대기 | DetectionEvent 소비자 | event_type 확정 후 수신 처리 검토 |
| System monitor | 검토 대기 | DetectionEvent·증적 소비자 | 필드·전송 계약 검토 |
| 비전 | 미반영 | 본 요청서 | detecting node·event_type·1초 확정 구현안 제시 |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: IT-14, IT-16
- 비전팀이 event_type enum과 종류별 confidence·동일 대상·cooldown을 제시하고 영향 단위가 합의한다.
- detecting node가 AMR PC에서 실행되며 속도·Nav2 명령을 발행하지 않는다.
- AMR만 yaw를 수행하고 최종 출력이 local_safety_supervisor를 통과한다.
- 정렬 오차와 실제 정지를 모두 만족한 뒤에만 같은 candidate의 정렬 완료를 알린다.
- 정렬 완료 후 같은 대상이 1.0초 연속 유효할 때 DetectionEvent가 한 번 발행된다.
- 1초 중 탐지 단절·정렬 해제 시 확인이 초기화된다.
- 일반 입력으로 진행 중 정렬을 교체하지 않고, 독립 안전 원인은 즉시 중단·정지시키며 자동 재개하지 않는다.
- DetectionEvent에 severity enum·필드가 존재하지 않는다.
- robot1·robot6 각각 IT-14·16 결과와 로그·버전을 기록한다.
- 실제 실행 결과와 증거: NOT_RUN
- 미실행 또는 BLOCKED 항목: event_type, Candidate·정렬 상태 인터페이스, yaw 수치·timeout 합의 전 실제 회전 시험 BLOCKED

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-07 | 프로젝트 담당자 | AMR detecting node는 비전팀이 개발하고 AMR PC에서 실행; 비전은 수동 탐지, AMR은 yaw·정렬·정지 완료 통지, 이후 1초 연속 탐지로 확정 | 사용자 결정 |
| 2026-09-07 | 프로젝트 담당자 | 정렬은 일반 입력으로 중단하지 않으며 event_type은 비전팀 제시, severity enum은 만들지 않음 | 사용자 결정 |
| 2026-09-07 | 관제 | 기존 E-stop·token·로컬 안전은 독립 안전 계층이므로 정렬 중단 금지보다 우선 | 기존 확정 안전 계약과 최종 속도 단일 발행 원칙 |
