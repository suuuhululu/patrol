# 공용 메시지 소스 이관 기록

2026-09-07 사용자 요청에 따라 `/home/mook/final_turtlebot_ws/src/parking_interfaces/`의 메시지 5종과 `CMakeLists.txt`, `package.xml`을 최초 이관했다. 원본과 기존 `.gitkeep`은 보존했고 생성 결과인 build/install/log 및 AMR 동작 코드는 복사하지 않았다.

2026-09-07 [설계 기준 결정](../../docs/decisions/2026-09-07-design-baseline.md) 3항에 따라 ROS 패키지명을 `patrol_interfaces`로 통일했다. 이관 시점에는 디렉터리명만 `patrol_interfaces`이고 `package.xml`과 CMake의 패키지명은 `parking_interfaces`였다. 빌드 선택과 인터페이스 조회에는 `patrol_interfaces`를 사용한다. 메시지 필드와 계약 내용은 바꾸지 않았다. 관제 검토 요청은 [CR-AMR_09-07_14-32_공용_메시지_패키지명_통일.md](../../docs/change_requests/CR-AMR_09-07_14-32_공용_메시지_패키지명_통일.md)에 있다.

## 계약 상태

> **현행 계약:** 이 파일의 이관 이력보다 [v1.0 기준선](../../docs/decisions/2026-09-08-control-interface-baseline.md)과 [interfaces.md](../../docs/interfaces.md)가 우선한다. 아래 과거 필드 설명을 실행 계약으로 사용하지 않는다.

이관은 기존 소스의 재사용이며 공용 계약 합의나 TBD 해결을 뜻하지 않는다. 현재 계약 상태의 기준은 [interfaces.md](../../docs/interfaces.md)다. 원본 주석의 `[계약]`, `CR-001`, `CR-002`, `CR-004`와 package.xml의 과거 문서 경로·소유 설명은 이전 워크스페이스 기록이며 현재 저장소의 확정 결정으로 해석하지 않는다.

- 2026-09-07 사용자 요청으로 MissionCommand, DriveToken, RobotStatus, PatrolReport, EStop을 최신 `interfaces.md` 의미 필드와 이름에 맞추고 신규 CommandCheck를 추가했다. 빌드와 6종 `ros2 interface show` 조회를 완료했다.
- DriveToken은 `control_session_id`·`token_id`·`message_sequence`, RobotStatus는 `*_state`와 구조화 ID 필드, EStop은 `target_robot_id`·`active`·`reason`·`sequence`를 사용한다. `latched`·물리 E-stop·manual reset은 v1.0에 없다. PatrolReport의 `reason_code`는 uint32다.
- CommandCheck는 UNKNOWN=0, ACCEPTED=1, EXECUTING=2, REJECTED=3이며 RobotStatus safety enum과 EStop reason 0~6, 전체 대상 `all`은 v1.0에 확정됐다. 남은 상세 TBD는 차기 버전으로 이관한다.
- STOP/CANCEL/RESUME 관련 과거 주석은 현재의 TBD-AMR-005를 해결하는 근거가 아니다. [amr.md](../../docs/amr.md)를 따른다.

빌드·타입 조회 성공은 메시지 생성 가능성과 이름 동기화만 검증하며, 양측 동일 버전 배포와 로봇 통합시험은 별도다.
