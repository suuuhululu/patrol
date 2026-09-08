# [AMR] Detection·증적·화재 부저 계약 검토

- 상태: 초안
- 최초 작성 시각: 2026-09-07 19:10 KST
- 요청자: 박성현
- 요청 단위: AMR
- 대상 단위 및 로봇: AMR robot1·robot6, 관제, System monitor
- 관련 TBD ID: TBD-AMR-001, TBD-AMR-004, TBD-IF-006,
  TBD-IF-007, TBD-IF-009, TBD-MON-001, TBD-MON-002
- 기준 문서·절: `docs/amr.md` 6절, `docs/interfaces.md` 1.2·6·9절,
  `docs/integration.md` W-06·IT-14·15
- 결정 일자·근거: 화재 후 mission/token/부저 흐름과 Q-12는
  2026-09-07 관제 요청서에서 일부 결정. Detection과 증적 wire contract는 미결정
- 코드 변경 승인 근거·범위: 사용자의 단일 기능 순차 구현 승인. 미정 공용
  메시지·토픽 및 다른 팀 코드는 미승인

## 변경 이유

robot6 실기에서 `irobot_create_msgs/action/AudioNoteSequence`의
`/robot6/audio_note_sequence` Action에 880 Hz·660 Hz 각 1초, 1회 goal을
보내 실제 음이 들리는 것을 확인했다. 같은 장비의 `/robot6/cmd_audio` 토픽
발행은 subscriber 대기와 발행 로그까지 확인했지만 음은 들리지 않았다.
따라서 화재 부저의 장비 출력 후보는 동작이 확인된 Action이 적합하다.

AMR 코드에는 Action 전송 형식과 취소 수명, 여러 활성 화재가 있을 때 마지막
화재가 해소되기 전까지 부저를 유지하는 ROS 독립 로직을 분리했다. 그러나
Detection 입력과 확정 출력의 타입·토픽, yaw 정렬 기준, 화재음 패턴이 없으므로
이를 임의로 묶은 ROS event node는 만들 수 없다.

## 변경 전 → 변경 후

현재 반영:

- `fire_event_registry.py`: 활성 event ID 집합과 다중 화재 부저 ON/OFF 판단.
  같은 활성 ID의 반복 입력은 상태를 두 번 바꾸지 않는다.
- `audio_note_sequence_adapter.py`: 호출자가 제공한 음표를 INFINITE Action
  goal로 만들고, 중복 goal을 막고, OFF 요청 시 goal을 cancel한다.
- 음의 주파수·길이·반복 패턴은 설정값을 제공하기 전까지 코드에 기본 화재음으로
  고정하지 않는다.
- Detection 수신 ROS 노드, yaw 속도 발행, DetectionEvent와 evidence 전송은
  아직 만들지 않는다.

결정 요청:

1. DetectionCandidate와 DetectionEvent의 메시지 패키지·필드·enum,
   robot별 토픽명·QoS·발행자와 subscriber.
2. 동일 대상 key, confidence 기준, bbox 중심 정렬 오차, 연속 탐지 중 허용 gap,
   yaw 각속도·timeout·실패 결과.
3. yaw 후보 속도가 통과할 local safety 입력 토픽·타입·remap.
4. event ID 중복 보관 시간과 해소/종료 이벤트 표현. 여러 활성 화재 중 어느
   event가 종료됐는지 전달하는 방법.
5. evidence 메타데이터, 이미지 형식·전송 경로, event보다 이미지가 먼저/나중에
   도착할 때 연결, ACK·재시도·영속 queue.
6. 화재 부저 제어자가 AMR인지, Action endpoint를 상대 이름
   `audio_note_sequence`로 확정할지, robot1·robot6 장비 차이.
7. 승인된 화재음의 주파수·note 길이·패턴과 Action server timeout. START와
   OFF 실패를 RobotStatus/PatrolReport/운영 경고 중 어디에 기록할지.

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| AMR | 1~3·6·7의 센서/정렬/안전/장비 동작안과 robot별 실기 결과 제시 | Detection 처리, local safety 입력, AudioNoteSequence | 박성현·조정묵 |
| 관제 | 확정 event 수신, 중복, 화재 후 명령·경고, event 해소 계약 결정 | DetectionEvent 소비·MissionCommand 발행 | 관제 담당 |
| System monitor | evidence 수집·저장 ACK, 순서 변경·DB 실패·복구 계약 결정 | 증적 수집·DB queue | System monitor 담당 |
| 비전 | 해당 없음. CCTV CameraState 계약과 OAK-D 로컬 Detection을 합치지 않음 | 해당 없음 | 해당 없음 |

## 영향과 적용 순서

먼저 1~7을 합의해 `interfaces.md`·`amr.md`·`monitoring_and_data.md`에
반영한다. 다음으로 Candidate adapter, 연속 확인기, yaw controller,
DetectionEvent publisher, evidence queue, fire buzzer coordinator를 각각
별도 파일로 구현한다. 마지막에 event node가 이 모듈을 조합하고 IT-14·15를
실행한다. yaw 출력은 TBD-IF-009의 local safety를 우회하지 않는다.

혼합 버전이나 Action 실패에서는 미확정 event node를 실행하지 않는다. 부저
goal 전송 실패를 화재 없음으로 해석하지 않으며, 화재 mission을 자동 재시작하지
않는다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | 일부 반영 | 공통 active-fire 로직·Action adapter 단위시험 | Action server 실기·event node |
| AMR / robot6 | 일부 반영 | 수동 AudioNoteSequence Action 실제 음 확인 | 자동 START/OFF·Detection 종단 |
| 관제 | 검토 요청 | W-06·Q-12 후속 정책 일부 확정 | event·경고 세부 계약 |
| System monitor | 검토 요청 | IT-15 요구만 존재 | evidence wire/DB 실패 계약 |
| 비전 | 변경 불필요 | CCTV와 OAK-D 로컬 경계 유지 | 없음 |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: IT-14, IT-15, IT-16
- 추가 시험·기대 결과: yaw 정렬·1초 연속 조건·동일 event 중복·증적 순서
  변경/전송/DB 실패·다중 화재·도킹 성공/실패·Action 실패를 각각 주입하고
  합의된 출력과 복구 결과 확인
- 실제 실행 결과와 증거: robot6 AudioNoteSequence 수동 Action 가청 PASS;
  active-fire registry와 infinite goal·중복 start·pending stop 단위시험 9건 PASS
- 미실행 또는 BLOCKED 항목: robot1 Action, 자동 부저 OFF, Detection/yaw,
  event/evidence pub-sub와 DB 종단

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-07 | 박성현·AMR | 실기 성공 Action을 출력 후보로 사용하고 미정 Detection 입력 노드는 계약 뒤 구현 요청 | 사용자 robot6 실행 결과·TBD 대조 |
