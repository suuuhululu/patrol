# 시스템 통합과 시험

상태: 실행 전 통합 명세 초안 · 담당: AMR·관제·시스템 모니터·비전 공동

아래 절차는 시험 계획이며 실제 실행 결과가 아니다. 미정 계약에 의존하는 시험은 해당 TBD 해결 전 BLOCKED로 기록한다. 각 시험 결과는 NOT_RUN / PASS / FAIL / BLOCKED로 구분한다.

## 1. 통합 기준

통신 이름·필드·시간·거리 수치의 원본은 [interfaces.md](interfaces.md)다. 아래 Q-ID는 그 문서 9절을 참조한다. 각 단위의 구현 책임은 [AMR](amr.md), [관제](control_server.md), [비전](vision.md), [시스템 모니터](monitoring_and_data.md)를 따른다.

통합은 AMR, 관제, 시스템 모니터, 비전의 네 개발 단위로 관리한다. 관제와 시스템 모니터는 통합 실행 시 PC 3에서 함께 실행하며 개발·반영 상태는 각각 기록한다. PC 번호는 통합 실행 위치를 나타내며 개발자의 작업 PC를 지정하지 않는다. 문서 합의, 코드 반영, 장비 배포, 통합 검증은 별도 상태다.

UC별 목표·사전 조건·기본/예외 흐름·완료 조건과 W 흐름의 대응은 [scenarios.md](scenarios.md)를 따른다. UC-01~08은 외부 액터 관점이며 아래 W-01~06은 여러 UC가 재사용하는 내부 종단 동작이다. UC 번호를 W 번호와 동일한 것으로 해석하지 않는다. 시험 기록에는 대상 UC와 IT ID를 함께 적는다.

## 2. 통합 준비와 기동 확인

다음은 권장 점검 순서이며 정확한 실행 명령·서비스 의존성은 TBD-ARCH-001에서 확정한다.

1. [AGENTS.md](../AGENTS.md)의 승인 범위와 개발 단위별 반영 버전을 확인한다.
2. robot1/robot6, /robot1·/robot6, AMR1/AMR2 매핑 및 대상 장비를 확인한다.
3. 기존 TB4 Onboard 서버 ID 1·6 설정이 유지되는지 확인한다. 단일 서버로 통합하지 않는다.
4. PC 3 Offboard 서버 ID 0, UDP 11811의 접속 주소와 서비스를 확인한다.
5. 각 TB4의 Offboard 연결과 PC 1·2·3·4 Client 참여를 확인한다. 토픽 발견 이후 실제 송수신을 별도로 확인한다.
   관제와 시스템 모니터의 기동·수신 상태를 각각 확인하고, 제어 기록 전달·저장·조회 연계는 두 팀의 적용 버전으로 검증한다.
6. 시간 동기화, map frame, 노드 lifecycle, 센서·pose·배터리 상태, Keepout 구성과 최종 속도 출력 경로를 확인한다.
7. E-stop·token·임무 실행 게이트가 준비되었는지 확인한 후 승인된 시험을 시작한다.

Onboard/Offboard 설정은 실제 장비에서 조사하며 서버끼리 직접 연결된다고 가정하지 않는다. Discovery 장애와 데이터 통신 단절은 별도로 시험한다. 기존 참여자 통신 여부는 관측 결과로 판정한다.

## 3. 종단 동작

### W-01 정상 순찰

사전 조건: RobotStatus 유효, pose·배터리·E-stop·Keepout 조건 충족, permit 허용. 관제가 token과 START_PATROL을 발행하고 AMR이 검증 후 내부 Nav2 Action을 실행한다. 상태는 AMR에서 보고하고 목표 종료 시 PatrolReport를 제공한다. 순찰 waypoint·완료 정의는 TBD-AMR-005다.

### W-02 차량 진입·출차와 대피·재개

PC 4 ENTERING 또는 EXITING → permit=false → 관제의 기존 순찰 취소 → Keepout ON 성공 → MOVE_TO_SAFE_ZONE → AMR 도착 확인 → token 회수 순서다. 대피 중 token은 유지하되 다른 안전 조건은 우선 적용한다.

PARKED 또는 EXITED → permit=true → 관제가 상태·E-stop 등 재개 조건 확인 → Keepout OFF 성공 → token 발급 → RESUME_PATROL 순서다. 진입·출차 이벤트 쌍은 vision.md를 따른다. 중간 실패 시 다음 주행 단계를 진행하지 않고 해당 안전·실패 정책으로 처리한다.

비전 이벤트의 P0 통합 기준은 [비전 수정 요청서](change_requests/CR-관제_09-07_17-53_비전_CameraState와_permit_반영.md)를 따른다. ENTERING·EXITED·EXITING은 유효 조건이 monotonic 시간 0.2초 연속 유지될 때 확정하고, 조건 이탈이나 미검출이 발생하면 확인 시간을 초기화한다. PARKED는 5초 체류 조건을 유지한다. cam_master는 permit 상태 변경 시 즉시 발행하고 동일 값을 5 Hz로 반복 발행한다.

관제는 permit을 5초 동안 받지 못하면 timeout 경고를 발생시키되 마지막 값을 임의로 반전하지 않는다. 현재 Bool 계약에서 정상 수신 복구는 동일 값을 3회 연속 수신하고, 각 수신 간격이 0.5초 이하이며 첫 수신부터 세 번째 수신까지 로컬 monotonic 경과가 0.3초 이상일 때로 확인한다. 중간에 값이 달라지거나 시간 조건이 깨지면 첫 수신부터 다시 확인한다. cam_master 세션·발행 sequence까지 검증하는 방식은 Bool 필드만으로 구현할 수 없으므로 [비전 P1 권장안](vision_P1.md)의 별도 permit 메시지 채택 전에는 통합 기준으로 간주하지 않는다.

빠른 permit 반전, 도착 확인 방식, Keepout ON 상태에서 탈출할 수 있는지 사전 검증은 TBD-INT-002·003이다.

### W-03 배터리·도킹·역할 교대

AMR의 Battery 상태 보고 → 관제의 도킹/교대 판단 → AMR의 도킹 실행·상태 보고 → 성공 또는 실패 보고로 진행한다. CRITICAL은 현재 waypoint 완료를 기다리지 않고 관제가 즉시 복귀 또는 도킹을 판단한다. LOW는 새 mission을 시작하지 않고 현재 mission의 순찰·복귀·도킹까지 완료하며, 중간에 CRITICAL로 전환되면 즉시 복귀 또는 도킹 판단으로 바꾼다. UNKNOWN은 신규 순찰과 교대 투입에서 제외한다.

도킹은 DOCKING 진입 후 60초 안에 DOCKED 완료 센서와 CHARGING 상태가 모두 2초 연속 유지되면 성공이다. 실패 시 관제가 Battery 상태, 인계 지점까지 거리, 최근 장애·도킹 실패 이력을 기준으로 가용 로봇을 선정한다.

교대는 기존 token 회수 후 새 command ID를 사용한다. 회수는 빈 token ID와 이전 holder robot ID로 발행한다. 기존 AMR의 회수 수락 뒤 odometry 선속도 ≤ 0.05 m/s, 각속도 ≤ 0.1 rad/s가 0.5초 연속이고 측정 age ≤ 0.5초인 실제 정지를 확인한 다음 신규 holder token을 발급한다. 이전 로봇의 도킹 주행과 신규 출발의 세부 중재는 동일한 단일 holder 원칙을 지키며 AMR 반영 검토에서 확정한다.

### W-04 통신 단절과 복구

token 미수신/만료 또는 heartbeat 1초 미수신 → AMR 로컬 안전 정지. heartbeat는 관제가 5 Hz로 발행한다. RobotStatus 미수신 → 관제 STALE, 신규 임무·token 갱신 중단. 임무 결과가 없으면 UNREPORTED 유지.

복구 후 Q-04 정상 수신, Q-05 현재 pose, E-stop 해제·Keepout·배터리 확인 및 유효 token을 확보한 뒤 재개한다. 단순 연결 복구나 token 재수신만으로 자동 출발하지 않는다. 단절 중 완료된 결과의 전달은 TBD-IF-003이다.

### W-05 E-stop과 해제

안전 원인 발생 → Safety Arbiter 단일 E-stop 발행 → AMR 로컬 안전 반영 → 활성 로그 기록. 물리 원인은 수동 reset까지 latch한다. 그 외 원인은 제거 후 Q-10을 충족하면 관제가 해제를 결정한다. 조건이 다시 깨지면 해제 조건 취소를 기록한다. E-stop 해제 부저는 없다.

해제가 곧바로 이동 명령을 뜻하지 않는다. 재개를 위한 상태·token·임무 조건을 별도로 확인한다. 정확한 요청/응답·원인 범위는 TBD-IF-004다.

### W-06 확정 이벤트·증적·화재 부저

AMR 로컬 후보 → yaw 정렬 → 연속 탐지 → 확정 이벤트·증적 → 시스템 모니터 수집·중복 처리 방지·저장·화면 조회로 연결한다. Detection 세부는 TBD-AMR-001 및 TBD-IF-006·007을 따른다.

화재 확정 시 부저를 ON하고 신규 순찰 구간을 추가하지 않은 채 현재 mission ID로 순찰·복귀·도킹까지 완료한다. 기존 Drive Token은 도킹 완료 또는 실패까지 유지하고 종료 시 회수한다. 이후 다른 로봇에 새 token을 발급하지 않고 전체 순찰을 중단한다. token 만료나 E-stop은 이 흐름보다 우선하며 새 token ID를 자동 발급해 복구하지 않는다.

DOCKED 완료 센서와 CHARGING 상태가 2초 연속이면 도킹 성공과 부저 OFF로 판정한다. 도킹 timeout 또는 실패 시 다른 활성 화재가 없으면 부저를 OFF하고 FIRE_DOCKING_FAILED 관제 경고를 발생시킨다. 다른 활성 화재가 있으면 부저를 유지한다. 화재 확정만으로 mission을 FAILED로 바꾸지 않으며 FIRE_DETECTED=702는 reason code로만 사용한다.

## 4. 통합시험 명세

모든 시험의 초기 결과는 NOT_RUN이다. 실패·중단 시험은 안전한 시험 환경과 승인된 범위에서 수행한다. 계약 미정 부분은 실행 전에 BLOCKED로 표시한다.

| ID | 사전 조건·수행 절차 | 개발 단위별 기대 결과·통과 기준 | 관련 기준 |
|---|---|---|---|
| IT-01 Discovery·식별 | 기존 Onboard 유지, PC 3 서버 준비 후 각 Client와 TB4 연결; 로봇별 상태 송수신 | 두 로봇의 올바른 토픽 발견 및 데이터 수신, 식별 혼선 없음; 로컬 통신 확인 | architecture, TBD-ARCH-001 |
| IT-02 명령 확인·중복 | ACCEPTED/REJECTED 정상 응답, 각 5초 Check timeout, 동일 ID·payload 재전송, 동일 ID·다른 payload, 완료 뒤 재전송, 재시작 뒤 기록 검사 | ACCEPTED/EXECUTING/REJECTED와 최종 report 연결; timeout마다 동일 ID로 최대 2회 재전송; 중복 실행 없음; ID 충돌 거절; 완료 뒤 기존 report 재전달 | Q-14·15, TBD-IF-001 |
| IT-03 토큰 검증 | 유효 token 이후 낮은/동일 message sequence·오래된 메시지·다른 holder·새 control session을 각각 주입 | AMR이 잘못된 권한을 수락하지 않고 lease가 부당 연장되지 않음; 새 control session에서 이전 token 폐기 | Q-01, TBD-IF-002 |
| IT-04 토큰 만료·회수 | 활성 mission에서 갱신 중단, 이전 holder를 지정한 빈 token ID 회수, 실제 정지 조건 경계 시험 | 만료/회수 시 AMR 안전 정지·신규 주행 차단; 새 token만으로 자동 출발 없음; odometry 정지 조건 전 신규 holder 금지 | Q-01, TBD-AMR-006·INT-001 |
| IT-05 CCTV 정상·중복 | gate_cam·center_cam별 구조화 event ID와 source session·sequence, enum 0~4, 허용 상태를 검사한다. ENTERING·EXITED·EXITING은 0.2초 직전·경계·직후, 중간 조건 이탈·미검출을 주입한다. PARKED는 5초 체류와 confidence 계산 구간을 검사한다. 동일 ID 반복과 topic별 금지 enum도 발행한다. | `patrol_interfaces/msg/CameraState`, camera_id `gate_cam`·`center_cam`, 상태별 enum과 ID가 요청 계약에 일치한다. 0.2초 미만 또는 중간 단절에서는 이벤트가 없고 조건을 연속 충족한 경우에만 1회 발행한다. confidence는 일반 상태의 유효 0.2초 평균, PARKED의 마지막 유효 0.2초 평균이다. 중복은 1회만 처리하고 금지 enum은 폐기·기록한다. | [비전 P0 요청](change_requests/CR-관제_09-07_17-53_비전_CameraState와_permit_반영.md), Q-13, TBD-IF-005 |
| IT-06 CCTV permit·단절·복구 | permit true/false 각각에서 상태 변경 즉시 발행과 5 Hz 반복 주기를 측정한다. 이후 permit 통신을 5초 미만·이상 중단하고, 동일 Bool 3회 수신의 간격·전체 경과 조건을 경계값으로 시험한다. | 변경 값은 즉시 전달되고 반복 주기는 5 Hz다. 5초 미만 단절은 timeout이 아니며 5초 도달 시 관제가 경고하고 마지막 permit을 유지한다. 동일 값 3회, 각 간격 ≤0.5초, 전체 경과 ≥0.3초를 모두 만족한 경우에만 정상 복구한다. 모니터는 관제 판단 결과를 표시·기록하고 임의로 permit을 반전하지 않는다. | [비전 P0 요청](change_requests/CR-관제_09-07_17-53_비전_CameraState와_permit_반영.md), TBD-IF-010 |
| IT-07 대피·재개 | 순찰 중 permit false, 대피 완료 후 true | 관제·AMR W-02 순서 일치, 대피 중 token 유지, 도착 후 회수 | Q-08, TBD-INT-002·003 |
| IT-08 Keepout 실패 | global/local 일부 적용 실패와 rollback 실패를 각각 주입 | 전체 snapshot 복구 또는 UNKNOWN·Safety Arbiter 정지 요청; 부분 성공을 commit하지 않음 | Q-07, TBD-CTRL-002 |
| IT-09 안전구역 없음 | 후보 조건 불충족 지도/동선, 별도로 Keepout 탈출 불가 조건 | AMR 현 위치 정지, SAFE_ZONE_NOT_FOUND; 불가능 경로 주행 방지 확인 | Q-08, TBD-INT-003 |
| IT-10 상태·복구 | RobotStatus 중단 후 복구; heartbeat 1초 timeout; 각 재개 조건을 하나씩 실패시킴 | 관제 Q-03 STALE·갱신 중단, AMR heartbeat 안전 정지, Q-04·05 통과 전 자동 재개 없음; 모니터는 관제가 제공한 상태 표시 | Q-03~06·16, TBD-CTRL-003 |
| IT-11 E-stop | 물리/비물리 원인, 해제 조건 유지·중단을 각각 시험 | 단일 발행, 물리 latch, 즉시 활성, 조건 시작/취소/해제 로그; 해제 후 새 token·command 전 이동 없음; 해제 부저 없음 | Q-10, TBD-IF-004 |
| IT-12 pose·보고 | 무효 pose, snapshot/pose 시각 차이, 결과 전 단절, 복구 후 같은 report ID 재전달 | 마지막 유효 pose와 age 구분; UNREPORTED 유지·대필 없음; command·mission·report ID 연결과 중복 제거 | TBD-IF-003 |
| IT-13 배터리·도킹·교대 | SOC 경계, LOW mission 완료, LOW→CRITICAL, UNKNOWN, DOCKED·CHARGING 2초 경계, 도킹 timeout | enum·Q-11 일치; LOW는 현재 mission 도킹까지 완료; CRITICAL은 즉시 전환; Q-09 성공 조건; 실제 정지 뒤 교대 token | Q-09·11, TBD-INT-001 |
| IT-14 Detection·화재 | 화재 확정, 현재 mission 순찰·복귀·도킹, token 만료/E-stop, 도킹 성공·실패, 복수 활성 화재 | 부저 ON; 기존 token 종료까지 유지·회수; 종료 후 다른 로봇 신규 token 없음; Q-12 OFF 또는 실패 경고; 미정 Detection 조건은 BLOCKED | Q-12, TBD-AMR-001·004, TBD-INT-004 |
| IT-15 증적·DB | 이벤트/이미지 순서 변경·전송 실패·DB 실패·복구 | 합의된 중복/재시도·불완전 상태·복구 결과, 읽기 전용 조회 | TBD-IF-007, TBD-MON-001·002 |
| IT-16 최종 속도 경계 | Nav2·yaw 후보와 E-stop/token 만료를 함께 발생시킴 | 최종 출력 발행권 하나, 안전 차단을 우회하는 경로 없음 | TBD-IF-009, TBD-AMR-006 |

IT-13의 배터리 경계는 interfaces.md 8절의 모든 임계값을 사용한다. 도킹 접점 유지가 짧게 끊기는 경우와 timeout 경계도 포함한다. 반복 시험 결과는 실행 일자·대상 robot_id·각 PC 버전·실제 값·로그 위치와 함께 기록한다.

관제와 시스템 모니터 분리 검증: 관제가 제공한 STALE·경고·UNREPORTED가 화면과 일치하는지 확인한다. 모니터만 토픽 수신을 중단하는 경우 자체 운영 판단·제어 발행이 없어야 한다. 화면 미수신 표현은 TBD-MON-003, 결과 전달 계약은 TBD-IF-011 확정 후 검증하며 미확정 시 BLOCKED로 기록한다.

## 5. 변경 반영과 완료 판정

공용 계약 변경은 수정 요청서에 대상 단위별 상태를 기록한다. 한 단위 구현 완료만으로 통합 완료를 선언하지 않는다. 관련 시험 PASS와 미반영 상대 단위가 없음을 확인한다.

결과 기록 양식:

~~~text
UC ID / 시험 ID / 실행 일자 / 실행자:
계약 버전 또는 수정 요청서 파일명 또는 링크:
AMR·관제·시스템 모니터·비전 적용 버전:
대상 로봇과 사전 조건:
수행 절차·주입 장애:
기대 결과 / 실제 결과:
증거(로그·상태·측정값):
판정(NOT_RUN/PASS/FAIL/BLOCKED):
남은 이슈·재시험 조건:
~~~

## TBD

| ID | 미정 사항 | 영향 단위 | 상태 |
|---|---|---|---|
| TBD-INT-001 | 교대 시 회수 전달·실제 정지 확인·새 token·이전 로봇 도킹 순서 | AMR·관제 | 일부 결정: 실제 정지 뒤 신규 token; 이전 로봇 도킹과 신규 출발 세부 중재는 AMR 검토 대기 |
| TBD-INT-002 | permit 빠른 반전·중복, 대피 도착 확인, 진행 중 명령 재중재 | AMR·관제·비전 | OPEN |
| TBD-INT-003 | Keepout ON과 탈출 경로 검증 순서·실패 처리 | AMR·관제 | OPEN |
| TBD-INT-004 | 화재 확정 후 임무 결과·정지·도킹·부저 책임의 종단 순서 | AMR·관제 | 관제 결정 완료, [AMR 반영 요청](change_requests/CR-관제_09-07_15-55_AMR_명령_토큰_상태_안전_계약_변경.md) 검토 대기 |

TBD 상세 중 메시지 정의나 알고리즘 수치는 각각 interfaces.md와 기능 문서에 남긴다.
