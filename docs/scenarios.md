# 유즈케이스 기반 시스템 시나리오

상태: 설계 시나리오 · 기준일: 2026-09-07 · 대상: AMR·비전·관제·System monitor

UC-01~08은 전체 순찰 시스템 관점이다. 외부 액터는 관제 운영자·시설 관리자·시험 담당자이며 AMR·CCTV·관제·Monitor는 시스템 내부 구성요소다. 운영자 제어 요청은 관제 입력 경로(TBD-CTRL-004), 읽기 전용 조회는 System monitor로 분리한다. 시험 담당자는 시험 입력·장애 주입·판정 기록을 담당하며 운영 제어권을 추가하는 액터로 해석하지 않는다.

사용자가 제공한 UC-01~08을 공유 저장소에서 독립적으로 읽을 수 있도록 정리했다. 아래 flowchart는 **설계 흐름**이며 실제 코드별 flowchart·구현 대조·시험 결과를 대신하지 않는다. 미정 분기는 해당 TBD 합의 전 구현 기준으로 확정하지 않는다.

## 시나리오와 팀별 구현 연결

| UC | 시스템 시나리오 | 관제 | AMR | 비전 | System monitor | 통합 흐름 |
|---|---|---|---|---|---|---|
| UC-01 | 순찰 시작·결과 확인 | 요청·게이트·임무 조정 | 순찰, 관제 명령에 따른 복귀·도킹, 보고 | permit 제공 | 진행·결과 표시 | W-01·03 |
| UC-02 | 이상 탐지·경보·증적 | 운영 경보·후속 임무 판단 | 감지·정렬·확정·증적 | 로컬 Detection과 분리 | 수신 결과·증적 저장·조회 | W-06 |
| UC-03 | 권한 회수·교대 | 회수·정지 확인·선정·신규 발급 | 중단·상태 보고, 도킹·새 임무 실행 | permit 제공 | 교대 판단 결과 표시 | W-03 |
| UC-04 | 차량 대피·재개 | 취소·Keepout·대피·재개 조정 | 대피·대기·순찰 재개 | 차량 상태·permit 생성 | 관제 상태·경고 표시 | W-02 |
| UC-05 | 배터리·도킹·재투입 | 복귀·교대·출발 적격성 판단 | 배터리 상태, 도킹·결과 보고 | permit 제공 | 수신 상태 표시 | W-03 |
| UC-06 | 실시간 모니터링 | STALE·경고·UNREPORTED 판단 | 상태·결과 제공 | permit 제공 | 토픽 수신·읽기 전용 표시 | W-04 및 표시 연계 |
| UC-07 | 이력 조회 | 판단·운영 로그 제공 | 결과·이벤트 제공 | 진단 로그 제공 | 저장 이력·증적 읽기 전용 조회 | W-06 및 저장 연계 |
| UC-08 | 안전 정지·복구 | Safety Arbiter·복구 게이트·재개 결정 | 공통 로컬 안전·Goal 취소·보고·명령 대기 | permit 제공 | 판단 결과 표시 | W-04·05 |

UC와 코드 파일은 일대일 관계가 아니다. AMR은 [시나리오별 모듈](amr.md#11-시나리오별-코드-분리와-개발-단위)을 공유하고, UC-03·05의 교대 판단이나 UC-06·07의 조회 기능을 AMR 시나리오 코드로 복제하지 않는다. UC-02·04·05·08은 UC-01 진행 중에도 발생할 수 있으며 동시 발생 시 중재는 기존 안전 계약, [관제의 확정 중재·화재 정책](control_server.md), TBD-AMR-005 및 TBD-INT-001·002를 따른다.

통신·수치 기준은 [interfaces.md](interfaces.md), 팀별 처리 규칙은 [AMR](amr.md)·[관제](control_server.md)·[비전](vision.md)·[Monitor](monitoring_and_data.md), 기동·실제 시험 명세는 [integration.md](integration.md)가 기준이다. UC의 수치 요약을 변경할 때 기준 문서와 함께 대조한다.

원자료의 SW·FR·DATA 및 INT·AMR·DET·MON 요구사항 식별자는 출처 추적용으로 보존했다. 해당 요구사항 정의는 이 저장소에서 확인되지 않았으므로 구현 완료나 시험 통과의 근거로 사용하지 않는다. IT 식별자는 integration.md의 시험 명세와 연결한다.

## UC-01 · 순찰 시작 및 결과 확인

목표/액터: 관제 운영자가 순찰을 요청하고 임무 결과를 확인한다.

사전 조건: 지도·로봇 식별·상태·유효 pose·배터리·E-stop·Keepout·permit 조건 충족.

트리거: 관제 입력 경로의 START_PATROL 요청(운영자 UI 상세 TBD-CTRL-004). System Monitor는 명령 발행 주체가 아니다.

기본 흐름: ① 관제 게이트·대상 검증 ② token과 새 MissionCommand 발행 ③ AMR 중복·권한 검증 및 CommandCheck 반환 ④ 내부 Nav2로 순찰·관측하고 관제의 임무 조정에 따라 복귀·도킹 ⑤ RobotStatus 진행 및 command별 PatrolReport 결과 발행 ⑥ Monitor 조회.

예외/미정: token만 수신하면 출발하지 않는다. 차량 UC-04, 배터리 UC-05, 안전/복구 UC-08을 비동기로 적용한다. waypoint·scan·방문 완료·재개 위치 TBD-AMR-005.

완료 조건: 결과 SUCCEEDED/FAILED/CANCELED와 관련 ID·증거를 연결한다. 미수신 결과는 관제가 UNREPORTED로 판단하여 제공하고 Monitor가 표시한다. 관측점의 상세 방문·완료·재개 합격 조건은 TBD-AMR-005 합의가 필요하다.

관련: SW-01/02/04/10/11/23, FR-01/10/12, IT-02~04·12·13·16. 시험 결과 NOT_RUN.

### 설계 Flowchart

~~~mermaid
flowchart TD
    A[운영자 START_PATROL 요청] --> B{관제 게이트 통과}
    B -->|아니오| X[출발 차단·결과 제공]
    B -->|예| C[token·새 MissionCommand]
    C --> D{AMR 명령·권한 검증}
    D -->|실패| X
    D -->|성공| E[순찰·관측 / TBD-AMR-005]
    E --> F[관제 조정에 따른 복귀·도킹 / UC-05]
    F --> G[RobotStatus·PatrolReport]
    G --> H[관제 결과 연결·Monitor 표시]
    E -. 비동기 사건 .-> I[UC-02·04·05·08]
    G -. 결과 미수신 .-> J[관제 UNREPORTED 판단·Monitor 표시]
~~~

## UC-02 · 이상 탐지·경보·증적

목표/수혜자: 운영자·관리자가 화재·누수·적치물 확정 이벤트와 증적을 확인한다.

사전 조건: AMR 로컬 영상·감지 입력과 합의된 판정 계약. PC4 CCTV와 책임을 분리한다.

트리거: AMR 영상에서 후보 발생.

기본 흐름: ① 후보 생성 ② yaw 정렬 ③ 정렬 상태 1초 연속 탐지 의도 ④ 확정 이벤트·증적 생성 ⑤ 전달·저장 상태 연결 ⑥ 읽기 전용 경보·이력 조회. 화재 확정 시 부저 ON, 도킹 완료 후 OFF.

예외/미정: 정렬 오차·동일 대상·단절·confidence TBD-AMR-001, Detection·증적 계약 TBD-IF-006·007. 누락·순서 역전·저장 실패 TBD-MON-002. 화재 확정 후 현재 mission의 순찰·복귀·도킹까지 기존 token으로 완료하고 종료 시 회수하며, 이후 다른 로봇에 새 token을 발급하지 않는다. 위험도·고온·영상 비교는 확정 기능이 아니다.

완료 조건: 확정 이벤트와 증적의 연결·불완전 상태·중복을 검증한다. 로컬 image_path만으로 원격 전달 완료를 선언하지 않는다.

관련: SW-12~20, FR-05/06, IT-14·15. 시험 결과 NOT_RUN/BLOCKED.

### 설계 Flowchart

~~~mermaid
flowchart TD
    A[AMR 영상 후보] --> B[yaw 정렬 / 공통 안전 적용]
    B --> C{합의된 연속 탐지 조건}
    C -->|미충족| D[단절·재시도 처리 / TBD-AMR-001]
    C -->|충족| E[확정 이벤트·증적 생성]
    E --> F[전달·저장 상태 연결]
    F --> G[Monitor 경보·이력 조회]
    F -. 누락·실패 .-> H[관제 운영 경고 / 저장 복구 TBD-MON-002]
    E -. 화재 .-> I[부저 ON / 제어자 TBD-AMR-004]
    I --> J[현재 mission 순찰·복귀·도킹 / 기존 token 유지]
    J --> K[DOCKED·CHARGING 2초 후 부저 OFF]
    J -. 도킹 실패 .-> L[다른 활성 화재가 없으면 부저 OFF·관제 경고]
~~~

## UC-03 · 주행 권한 회수와 두 로봇 교대

목표/수혜자: 운영자의 반복 출발 조작을 줄이면서 로봇 간 주행 권한 중첩을 방지한다.

사전 조건: 기존 임무·token 소유자와 다음 후보의 최신 상태·pose·배터리·안전 조건 확인.

트리거: 관제의 교대 판단.

기본 흐름: ① 기존 임무/상태 확인 ② 기존 token 회수 ③ 합의된 실제 정지 확인 ④ 가용 다음 로봇 선정 및 출발 게이트 ⑤ 새 command_id와 token 발행 ⑥ 수락·진행·결과 관측.

예외/미정: 신규 token 전 실제 정지는 odometry 선속도 ≤0.05 m/s, 각속도 ≤0.1 rad/s, 0.5초 연속, age ≤0.5초로 확인한다. 이전 로봇의 도킹 이동과 신규 출발의 세부 중재는 TBD-INT-001이다. 명령 확인은 5초 Check timeout과 동일 ID 최대 2회 재전송을 사용한다. 무응답 30초 뒤 자동 교대나 n회 생략을 사용하지 않는다.

완료 조건: 이전 권한과 신규 권한의 중첩 없음, 중복 요청에서 재실행 없음, 적용 버전과 정지·출발 증거 확인. 미정 순서 의존 시험은 BLOCKED.

관련: SW-03~05/09/11, FR-02/10, INT-03·05, IT-02~04·10·13.

### 설계 Flowchart

~~~mermaid
flowchart TD
    A[관제 교대 판단] --> B[기존 임무·상태 확인]
    B --> C[기존 token 회수]
    C --> D{odometry 실제 정지 기준 충족}
    D -->|미확인| X[신규 출발 보류]
    D -->|확인| E[다음 로봇 선정·게이트 검증]
    E --> F{출발 조건 충족}
    F -->|아니오| X
    F -->|예| G[새 command_id·token 발행]
    G --> H[AMR 수락·진행·결과 / Monitor 표시]
    C -. 이전 로봇 도킹 이동 순서 .-> T[TBD-INT-001 합의 필요]
~~~

## UC-04 · 차량 이동 시 안전구역 대피와 재개

목표/수혜자: 차량 이동 시 AMR을 안전구역으로 대피시키고 조건 충족 후 순찰을 재개한다.

사전 조건: Gate·Center 관측, Keepout global/local 제어, 안전구역 후보와 상태·권한 게이트.

트리거: ENTERING 또는 EXITING에 따른 patrol_allowed=false.

기본 흐름: ① 관제 순찰 취소 ② Keepout ON transaction 성공 ③ 유효 token 유지한 MOVE_TO_SAFE_ZONE ④ 도착 확인 후 token 회수·대기 ⑤ Center PARKED 또는 Gate EXITED→permit=true ⑥ 재개 게이트 검증 ⑦ Keepout OFF 성공 ⑧ token 발급·RESUME_PATROL.

예외/미정: 부분 실패는 전체 rollback, rollback 실패 UNKNOWN·Safety Arbiter 정지 요청. 안전구역 없으면 정지·SAFE_ZONE_NOT_FOUND. 대피 중 독립 E-stop은 우선 적용한다. 빠른 permit 반전·늦은 이벤트·재시작 TBD-INT-002·VIS-002, Keepout 탈출 TBD-INT-003, 재개 지점 TBD-AMR-005.

완료 조건: 취소→Keepout ON→대피→도착→회수 및 게이트→OFF→재개 순서 증거. 단순 제자리 대기는 기본 대피 흐름의 대체가 아니다.

관련: SW-06/07/22, FR-03, IT-05~09, AMR-04·DET-02/03·INT-04.

### 설계 Flowchart

~~~mermaid
flowchart TD
    A[비전 ENTERING·EXITING / permit false] --> B[관제 순찰 취소]
    B --> C{Keepout ON transaction 성공}
    C -->|실패| X[전체 rollback / 실패 시 UNKNOWN·정지 요청]
    C -->|성공| D[MOVE_TO_SAFE_ZONE / 유효 token 유지]
    D --> E{대피 도착 확인}
    E -->|후보 없음·실패| Y[정지·실패 보고 / 관련 TBD]
    E -->|도착| F[token 회수·대기]
    F --> G[PARKED·EXITED / permit true]
    G --> H{관제 재개 게이트 통과}
    H -->|아니오| W[대기]
    H -->|예| I{Keepout OFF 성공}
    I -->|실패| X
    I -->|성공| J[token·RESUME_PATROL]
    D -. 독립 안전 원인 .-> S[UC-08 안전 정지]
~~~

## UC-05 · 배터리·도킹·재투입

목표/수혜자: SOC와 충전 방향의 상태를 정확히 보고하고 관제의 복귀·충전·재투입 판단을 지원한다.

사전 조건: 유효 배터리 입력·충전 방향·도킹 상태·센서.

트리거: SOC·충전 방향 또는 입력 유효성 변화.

기본 흐름: ① SOC 백분율 기준 방전 <10% CRITICAL, 10% 이상~20% 미만 LOW, ≥20% NORMAL / 충전 <50% CHARGING, 50% 이상~80% 미만 PATROL_READY, ≥80% FULL / 무효·미수신 UNKNOWN(메시지 SOC 비율은 interfaces.md 8절 기준) ② CRITICAL 즉시·나머지3초 지속 전이 ③ CRITICAL은 즉시 복귀·도킹 판단, LOW는 새 mission 없이 현재 mission의 순찰·복귀·도킹까지 완료 ④ DOCKING 진입 후60초 이내 DOCKED·CHARGING 2초 연속 확인 ⑤ 충전과 다음 출발 조건 확인.

예외/미정: LOW 진행 중 CRITICAL로 바뀌면 mission 완료 대기를 중단한다. UNKNOWN은 신규 순찰·교대 투입에서 제외한다. 입력·충전·센서 생성 방식은 TBD-AMR-003·004, 이전 로봇 도킹과 신규 출발의 세부 중재는 TBD-INT-001이다. 도킹 timeout은 관제에 보고한다.

완료 조건: 10/20/50/80 경계·충전방향·UNKNOWN·전이시간·도킹 성공/실패를 검증한다. 실제 주행/충전과 값 주입 시험을 구분한다.

관련: SW-02/08/09, FR-04, IT-13. 미정 정책 의존 부분 BLOCKED.

### 설계 Flowchart

~~~mermaid
flowchart TD
    A[SOC·충전 방향·입력 유효성 변화] --> B[AMR Battery 상태 / Q-11]
    B --> C[관제 복귀·교대 적격성 판단]
    C --> D[합의된 명령 / 필요 시 UC-03]
    D --> E[AMR DOCKING 진입]
    E --> F{Q-09 내 센서 성공 조건}
    F -->|충족| G[도킹 성공·충전 상태 보고]
    F -->|timeout| H[도킹 실패 관제 보고]
    G --> I{관제 다음 출발 게이트 충족}
    I -->|아니오| W[충전·대기]
    I -->|예| J[별도 명령·token으로 재투입]
    H --> T[후속 조치 관제 판단 / TBD-CTRL-003·TBD-INT-001]
~~~

## UC-06 · 읽기 전용 실시간 모니터링

목표/액터: 운영자·관리자가 로봇 상태와 확정 이벤트를 읽기 전용 화면에서 확인한다.

사전 조건: RobotStatus·PatrolReport·이벤트 구독과 저장 경로. 인증·Dashboard 상세 TBD-MON-003.

트리거: Monitor 열기 또는 상태·이벤트 갱신.

기본 흐름: ① robot1/robot6 식별 ② 위치·pose_valid·배터리·임무 상태 표시 ③ 갱신 시각·관제가 제공한 STALE·마지막 유효 위치와 age 구분 ④ 확정 이벤트·증적·PatrolReport 또는 UNREPORTED 조회.

예외/미정: RobotStatus 2Hz, 주요 상태 변경 즉시 최대10Hz. 관제가 판단하는 1.5초 STALE와 정상5초 복구 게이트를 구분한다. Monitor는 판단 토픽을 표시하며 자체 timeout·STALE·UNREPORTED를 계산하지 않는다(TBD-IF-011). Monitor 장애/저장 실패 처리 TBD-MON-002. 관련: SW-19/21/23, DATA-02/04, IT-10/12/15/16.

완료 조건: 현재 유효 정보와 과거 값을 구분하며 Monitor가 mission/token/E-stop을 발행하지 않는다.

### 설계 Flowchart

~~~mermaid
flowchart TD
    A[사용자 Monitor 열기·토픽 갱신] --> B[robot1·robot6 식별]
    B --> C[수신 위치·배터리·임무 표시]
    D[관제 STALE·경고·UNREPORTED 판단 토픽] --> C
    C --> E[유효·과거 위치 및 age 구분]
    E --> F[이벤트·증적·결과 조회]
    A -. 수신·저장 장애 .-> G[화면 표현·저장 처리 TBD-MON-002·003]
    G --> H[자체 운영 판단·제어 발행 없음]
~~~

## UC-07 · 읽기 전용 이력 조회

목표/액터: 운영자·관리자가 저장된 순찰·임무·이벤트·증적 이력을 조회한다.

사전 조건: 저장된 로그와 조회 기능. 실제 스키마·필터·보존 정책 TBD-MON-001·003.

트리거: 조회 조건 선택.

기본 흐름: ① 상태/이벤트/순찰 목록 조회 ② 동일 명령·임무·보고 및 증적 연결 확인 ③ 성공·실패·취소 사유와 미수신 UNREPORTED 구분 ④ 저장 불완전·중복 여부 확인.

예외/미정: 확인 메모·조치 상태 쓰기는 현재 확정 범위가 아니다. DB·증적 장애/재전달은 TBD-MON-002·IF-007.

완료 조건: 조회 행위가 로봇 제어를 유발하지 않으며 결과가 없으면 생성·대필하지 않는다.

관련: SW-19/21, DATA-01~04, FR-08/09, IT-12·15, MON-02~05.

### 설계 Flowchart

~~~mermaid
flowchart TD
    A[사용자 조회 조건 선택] --> B[저장된 상태·이벤트·순찰 목록]
    B --> C[명령·임무·보고·증적 ID 연결]
    C --> D[결과·사유·관제 제공 UNREPORTED 표시]
    D --> E[저장 불완전·중복 상태 확인]
    B -. DB·증적 장애 .-> F[조회 오류·복구 / TBD-MON-002]
    E --> G[읽기 전용 조회 종료]
    F --> G
~~~

## UC-08 · 안전 정지와 통신 복구

목표/액터: 운영자가 안전 정지 상태와 복구 가능 여부를 확인하고, 제안된 System monitor UI를 통해 관제에 OPERATOR 정지·해제를 요청한다. 사전 조건은 로컬 안전·Safety Arbiter·상태/권한 감시다. UI는 검토 대상이며 E-stop을 직접 발행하거나 해제를 판정하지 않는다.

트리거: token 만료/회수, E-stop, 통신 STALE 또는 독립 안전 원인. 차량 permit=false만으로 전 주행을 금지하지 않으며 UC-04 대피 절차와 구분한다.

기본 흐름: ① AMR 최종 속도 차단과 Goal 취소를 분리 수행 ② 상태·원인 보고 ③ STALE에서 관제 신규 mission/token 갱신 중단 ④ 정상 수신5초·유효 pose/age·배터리·E-stop·Keepout·permit 등 복구 게이트 확인 ⑤ 별도 유효 명령·token으로 재개한다.

예외/미정: 하드웨어·물리 E-stop과 수동 reset은 구현하지 않는다. 모든 활성 원인이 사라진 상태가 3초 연속 유지되어야 관제가 해제할 수 있다. heartbeat는 `ControlHeartbeat`로 관제 5 Hz 발행·AMR 1초 timeout이다. Ctrl+C/SIGINT 정상 종료는 E-stop이 아닌 `CONTROL_SHUTDOWN` 운영 이벤트이며, 재기동 뒤 새 control session과 새 token·별도 command 전에는 재개하지 않는다. reason 우선순위·UI 요청 API는 TBD-IF-004·TBD-CTRL-004다. 정지 감속·거리는 TBD-AMR-006이며 30초 경과 자동 교대를 사용하지 않는다.

완료 조건: 안전 출력 우회 없음·오래된 상태로 자동 출발 없음·결과 미수신 UNREPORTED 유지. 로그·실측 정지·적용 버전으로 IT-03/04/10/11/12/16을 검증한다. 현재 실제 시험 결과는 NOT_RUN, 미정 의존 부분 BLOCKED.

### 설계 Flowchart

~~~mermaid
flowchart TD
    A[token 만료·회수 / E-stop / 통신·안전 원인] --> B[AMR 공통 안전 출력 차단]
    A --> C[AMR Goal 취소 별도 수행]
    B --> D[상태·원인 보고]
    C --> D
    D --> E[관제 STALE 시 신규 mission·token 갱신 중단]
    E --> F[모든 활성 원인 제거 3초 연속]
    F --> G{관제 복구 게이트 충족}
    G -->|아니오| W[안전 정지·대기]
    G -->|예| H[별도 유효 명령·token]
    H --> I[AMR 검증 후 재개]
    D --> M[관제 판단 토픽·Monitor 표시]
~~~
