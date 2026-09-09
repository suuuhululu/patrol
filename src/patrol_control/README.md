# patrol_control

관제 팀의 ROS 2 패키지다. 논리 기능을 지나치게 잘게 나누지 않고 `patrol_control_node` 하나가 관제 상태를 소유한다. 현재는 launch 없이 노드를 직접 실행하는 1차 비전·시스템 모니터 통합 단계다.

현재 구현 범위:

- 시작 시 고정되는 `integration_profile=vision_integration`
- `/vision/cctv/patrol_allowed` 수신, 5초 timeout, 마지막 값 유지와 정상 복구 판정
- v1.1 `/{robot}/detection/event`의 robot ID·필수 ID·event_type 검증과 중복 제거
- AMR 입력·출력 비활성 및 MissionCommand 발행 차단
- 구조화 control session·mission·command ID 생성
- 명령별 mission_id·target_id 검증
- 동일 payload 재전송을 포함한 명령 도메인 로직
- CommandCheck 정상·복구 예외·역방향 전이 처리
- 중간 Check가 누락된 PatrolReport 최종 수락과 중복 제거
- 정상 Ctrl+C의 CONTROL_SHUTDOWN 로컬 기록

직접 실행:

~~~bash
source install/setup.bash
ros2 run patrol_control patrol_control_node \
  --ros-args -p integration_profile:=vision_integration
~~~

`full_system` 프로파일 이름은 예약돼 있지만 AMR 안전 통합이 완료되지 않았으므로 현재는 시작을 거부한다. 두 프로파일을 별도 코드나 장기 브랜치로 관리하지 않는다.

`WAITING → EXECUTING` 복구 예외에서는 `ACCEPTED_MISSING`을 기록하고 해당 명령 재전송을 즉시 중단한다. START_PATROL의 target은 robot1=`robot1_default`, robot6=`robot6_default`만 허용한다.

미구현 범위:

- System monitor 또는 운영자 입력 API(TBD-CTRL-004)
- 활성 mission 존재 여부와 동시 명령 우선순위 중재(TBD-CTRL-001)
- Drive Token·Heartbeat·E-stop·복구 게이트
- Keepout transaction·교대·배터리·화재 정책
- 관제 운영 이벤트의 공용 토픽(TBD-IF-011)

`patrol_interfaces 1.1.0`의 16개 메시지 manifest를 사용한다. v1.1에서 관제는 `DetectionEvent`를 소비하지만 `AlignmentStatus`·`DetectionResult`에는 개입하지 않는다. DetectionEvent의 최종 보존 기간과 화재 mission 동작은 잔여 계약·AMR 통합 단계에서 확정한다.

`submit_command()`는 이후 관제 소유 API가 호출할 내부 진입점이다. 미정 API를 임의로 만들지 않기 위해 현재 노드는 외부 명령 service/action을 노출하지 않는다.

## 관제 PC 정상 시나리오 수동시험

launch 파일 없이 터미널을 나눠 실행한다. 테스트 publisher는 비전 입력만 대신하며 설치 executable이나 운영 구성에 포함하지 않는다.

터미널 1:

~~~bash
source install/setup.bash
ros2 run patrol_control patrol_control_node \
  --ros-args -p integration_profile:=vision_integration
~~~

터미널 2의 단계별 정상 입력:

~~~bash
source install/setup.bash
python3 tests/integration/publish_control_inputs.py \
  permit-steady --permit true

python3 tests/integration/publish_control_inputs.py \
  permit-cycle --duration 6.5

python3 tests/integration/publish_control_inputs.py \
  detection --robot-id robot1 --event-type fire --duration 3
~~~

정상 기준은 steady 구간의 timeout 없음, cycle의 `false → true` 로그, DetectionEvent 수락, AMR 출력 없음이다. 시스템 모니터 ROS adapter를 함께 실행하면 같은 permit과 DetectionEvent가 저장·표시되는지 별도로 확인한다. timeout·복구, 중복·잘못된 enum·robot 불일치는 다음 오류 시나리오 단계에서 시험한다.
