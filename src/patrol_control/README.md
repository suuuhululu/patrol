# patrol_control

관제 팀의 ROS 2 패키지다. 1단계에서는 논리 기능을 지나치게 잘게 나누지 않고 `command_control_node` 하나가 Robot Command Manager와 명령 경로의 ROS 2 Gateway를 함께 담당한다.

현재 구현 범위:

- 구조화 control session·mission·command ID 생성
- 명령별 mission_id·target_id 검증
- MissionCommand 발행과 동일 payload 재전송
- CommandCheck 정상·복구 예외·역방향 전이 처리
- 중간 Check가 누락된 PatrolReport 최종 수락과 중복 제거
- 정상 Ctrl+C의 CONTROL_SHUTDOWN 로컬 기록

`WAITING → EXECUTING` 복구 예외에서는 `ACCEPTED_MISSING`을 기록한 뒤 재전송 정책을 진행하지 않고 `POLICY_PENDING` 진단을 한 번 발생시킨다. AMR 팀과 재전송 중단 여부가 합의되기 전까지 어느 쪽 동작도 확정하지 않기 위한 차단이다.

미구현 범위:

- System monitor 또는 운영자 입력 API(TBD-CTRL-004)
- 활성 mission 존재 여부와 동시 명령 우선순위 중재(TBD-CTRL-001)
- Drive Token·Heartbeat·E-stop·복구 게이트
- Keepout transaction·교대·배터리·화재 정책
- 관제 운영 이벤트의 공용 토픽(TBD-IF-011)

`submit_command()`는 이후 관제 소유 API가 호출할 내부 진입점이다. 미정 API를 임의로 만들지 않기 위해 현재 노드는 외부 명령 service/action을 노출하지 않는다.
