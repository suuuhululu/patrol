# 공용 메시지 소스 이관 기록

2026-09-07 사용자 요청에 따라 `/home/mook/final_turtlebot_ws/src/parking_interfaces/`의 메시지 5종과 `CMakeLists.txt`, `package.xml`을 내용 변경 없이 복사했다. 원본과 기존 `.gitkeep`은 보존했다. 생성 결과인 build/install/log 및 AMR 동작 코드는 복사하지 않았다.

이 디렉터리명은 `patrol_interfaces`이지만 `package.xml`과 CMake의 ROS 패키지명은 `parking_interfaces`다. 빌드 선택과 인터페이스 조회에는 `parking_interfaces`를 사용한다.

## 계약 상태

이관은 기존 소스의 재사용이며 공용 계약 합의나 TBD 해결을 뜻하지 않는다. 현재 계약 상태의 기준은 [interfaces.md](../../docs/interfaces.md)다. 원본 주석의 `[계약]`, `CR-001`, `CR-002`, `CR-004`와 package.xml의 과거 문서 경로·소유 설명은 이전 워크스페이스 기록이며 현재 저장소의 확정 결정으로 해석하지 않는다.

- MissionCommand·DriveToken의 필드 레이아웃은 현재 문서의 권장안과 일치한다. 명령 해석과 토큰 검증의 미정 사항은 TBD-IF-001·002를 유지한다.
- RobotStatus의 safety/scan enum과 상세 필드·타입, PatrolReport의 상세 레이아웃은 기존 구현 초안이다. TBD-IF-003을 유지한다.
- EStop의 필드·원인 enum은 기존 구현 제안이다. TBD-IF-004를 유지한다.
- STOP/CANCEL/RESUME 관련 과거 주석은 현재의 TBD-AMR-005를 해결하는 근거가 아니다. [amr.md](../../docs/amr.md)를 따른다.

이번 이관에는 실행 노드나 안전 정책 구현이 없다. 빌드·타입 조회 성공은 메시지 생성 가능성만 검증하며, 팀 간 계약 합의와 로봇 통합시험은 별도다.
