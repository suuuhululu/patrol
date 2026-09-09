# 30분 코드리뷰 진행안

갱신 기준: 2026-09-08, 1~20단계 및 `patrol_interfaces 1.0.0` 소비부 반영 완료. 현재 시스템은 AMR 상태, 정적 지도, 로봇별 costmap, DetectionEvent와 chunk 증적, 이상 이벤트 관제, 네 카메라 영상, 차량 입출차, CCTV 차량 상태·순찰 허용 조건, 관측점 방문·순찰 결과와 Keepout·E-stop 안전 상태, 통합 이력을 구현했다. 활성 입력 25개와 IngestionAck 2개의 별도 프로세스 로컬 DDS 종단시험까지 확인했다. 실제 상대 publisher·TF·PC 간 부하 검증은 아직 예정이다. 시스템 모니터는 운영 명령을 요청하지 않는다.

## 1. 발표 순서 — 합계 30분

| 시간 | 주제 | 보여줄 자료·코드 | 전달할 핵심 |
| --- | --- | --- | --- |
| 00:00~02:00 | 프로젝트 목적과 담당 범위 | UI 목업·요구사항 | 로봇 상태·이벤트 관제와 이력 기록 담당 |
| 02:00~05:00 | 플로우차트와 실제 동작 | 플로우차트·구현 기록 | 시작→DB→로그인→대시보드→데이터 처리 |
| 05:00~09:00 | 코드 구조·day5 활용 | run.py, create_app, routes/services/models | 예제에서 무엇을 재사용하고 왜 분리했는가 |
| 09:00~13:00 | DB 설계와 데이터 보존 | database.py, schema.sql | 최신 상태와 이력 분리·이미지 경로·중복 방지 |
| 13:00~17:00 | 로그인·장치 인증 | security.py, auth.py, robots.py | 브라우저 세션·CSRF와 장치 토큰의 역할 분리 |
| 17:00~20:00 | 상태·Nav 지도 시연 | robot/map route·service·model, 화면 | 상태와 지도 수신→좌표 변환→마커·경로 표시 |
| 20:00~23:00 | 이상 이벤트·입출차 관제 | event·vehicle access route/service/model, 화면 | 수신·원자 저장→로그·상세→권한별 처리 기록 |
| 23:00~25:00 | 네 카메라 영상 | camera route·service·JS, 화면 | 최신 프레임만 교체·보호 조회·단절 표시 |
| 25:00~27:00 | 통합 이력 검색 | history route·service·model, 화면 | 기존 5종 테이블 조건 조회·UTC 변환·50건 페이지 |
| 27:00~29:00 | 검증과 실패 처리 | 테스트·시연 결과 | 중복·저장 실패·권한·연결 단절 처리 |
| 29:00~30:00 | 한계·질문 | 남은 이슈 표 | 실제 검증 범위와 다음 연동 과제 |

운영 명령 요청은 별도 로봇·미션 모듈의 책임이다. 시연에서는 AMR 상태·점유 지도와 화재 이벤트 입력, 증거 이미지·상세 화면, 순차 처리 상태와 메모 이력을 보여준다.

## 2. 설명 멘트와 코드 탐색 순서

### 00~02분: 어떤 문제를 해결하는가

“지하주차장 로봇 두 대의 상태와 이상 이벤트를 관제하고, 누가 어떤 조치를 했는지 기록하는 웹 시스템입니다. 저는 Flask 서버·SQLite 저장·대시보드와 모듈 연결 부분을 맡았습니다. 실제 주행과 인식은 해당 로봇 모듈이 수행합니다.”

완성된 UI 또는 목업에서 지도, AMR1·AMR2 상태, 영상 네 영역, 이벤트 로그를 짚는다. 현재 구현 화면과 목업을 구분한다.

### 02~05분: 플로우차트를 코드로 옮기는 방법

“시작 단계는 서버 실행입니다. 앱을 만들면서 DB 폴더와 테이블을 준비합니다. 사용자는 로그인 후 대시보드에 들어갑니다. 이후 로봇 상태·영상·이벤트 처리는 각 기능으로 나눕니다.”

마름모는 조건문이나 DB 제약으로, 네모는 함수 호출·조회·저장으로 옮긴다고 설명한다. `필수 테이블 존재 여부`는 `CREATE TABLE IF NOT EXISTS`가 수행하는 예를 든다. 연결기 A는 다른 페이지로 이동하는 URL이 아니라 데이터 수신 대기로 돌아간다는 도식 표현이다.

### 05~09분: 기본 실행 구조

파일 열기 순서:

1. [run.py](../run.py): create_app 호출과 app.run.
2. [ros_adapter.py](../ros_adapter.py): ROS 의존성 점검과 별도 구독 프로세스 시작.
3. [app/ros_adapter.py](../app/ros_adapter.py): 토픽 등록→메시지 변환→기존 서비스 callback.
4. [app/__init__.py](../app/__init__.py): 설정→DB 초기화→인증 등록→페이지 경로 등록.
5. [routes/dashboard.py](../app/routes/dashboard.py): 로그인 검사 후 HTML 렌더링.
6. [templates/index.html](../app/templates/index.html): 사용자·권한, 로봇·영상 영역, 이벤트 표와 상세 대화상자.
7. [dashboard.css](../app/static/css/dashboard.css): 지도·상태·영상의 grid 배치와 좁은 화면 전환을 대표로 보여준다.
8. [routes/robots.py](../app/routes/robots.py): 장치 POST와 로그인 사용자 GET 경로.
9. [services/robot_service.py](../app/services/robot_service.py): 외부 값을 내부 상태로 검증·정규화.
10. [models/robot.py](../app/models/robot.py): 최신·이력 원자적 저장과 중복·순서 판정.
11. [routes/maps.py](../app/routes/maps.py): 지도 POST·로그인 JSON·PNG GET 경로.
12. [services/map_service.py](../app/services/map_service.py): 점유 지도 검증·PNG·좌표 변환.
13. [models/map.py](../app/models/map.py): 지도 이력·현재 지도·최근 좌표 조회.
14. [map.js](../app/static/js/map.js): 지도·로봇 마커·경로의 2초 갱신.
15. [costmap_service.py](../app/services/costmap_service.py) → [costmap.py](../app/models/costmap.py) → [costmaps.py](../app/routes/costmaps.py) → [costmaps.js](../app/static/js/costmaps.js): 네 동적 격자의 최신 저장과 분리 표시.
16. [detection_service.py](../app/services/detection_service.py) → [detection.py](../app/models/detection.py): DetectionEvent와 EvidenceChunk 독립 수신·조립·ACK 흐름.
17. [routes/events.py](../app/routes/events.py): multipart 이벤트 POST와 보호된 증거 이미지 GET.
18. [services/event_service.py](../app/services/event_service.py): 이상 사건 필드·시각·이미지 검증과 파일 저장.
19. [models/event.py](../app/models/event.py): 이벤트·증거 경로 트랜잭션과 중복·충돌 판정.
20. [events.js](../app/static/js/events.js): 3초 목록 갱신·상세 조회·CSRF 상태 변경.
21. [routes/cameras.py](../app/routes/cameras.py): 장치 프레임 POST와 로그인 사용자 GET.
22. [services/camera_service.py](../app/services/camera_service.py): 영상 검증·최신 교체·중복/순서/단절 판정.
23. [cameras.js](../app/static/js/cameras.js): 1초 상태 조회와 변경 프레임 표시.
24. [routes/history.py](../app/routes/history.py): 로그인 이력 화면과 JSON API.
25. [services/history_service.py](../app/services/history_service.py): 검색 검증·한국 날짜 UTC 변환·표시 라벨.
26. [models/history.py](../app/models/history.py): 다섯 종류 SELECT의 조건 구성·UNION·페이지 조회.
27. [templates/history.html](../app/templates/history.html): 검색 폼·결과 표·페이지 이동.

“day5에서는 하나의 파일 안에서 앱 생성과 경로를 정의했습니다. 같은 기본 원리를 사용하되 실행·인증·DB·화면을 파일별로 나눴습니다. 이렇게 하면 이벤트 입력이 HTTP에서 ROS로 바뀔 때에도 처리 서비스를 재사용하기 쉽습니다.”

폴더를 전부 읽지 말고 `routes → services → models → SQLite`를 인증 코드 한 사례로 연결한다. CSS는 필요한 부분만 보여준다.

4단계 설명 멘트: “예시 화면을 실제 HTML 구조로 옮겼습니다. 서버가 로봇·카메라 이름 목록을 전달하고 템플릿이 반복해서 카드를 만듭니다. 실제 데이터는 아직 연결 전이므로 배터리는 대시, 영상은 미연결, 지도는 등록 대기로 표시합니다. 지도·영상이 보인다고 실시간 연동이 완료된 것은 아닙니다.”

실제 대시보드에서 메뉴의 지도·영상·로그 이동을 보여준다. 관리자 링크와 로그아웃은 기존 인증 기능을 사용한다. 개발 시각 표시는 `dashboard.js`의 한국 시간 시계이며 장비 수신 시각과 구분한다.

### 09~13분: DB 설계

[database.py](../app/database.py)에서 `init_db`, `get_db`, `close_db` 순으로 보여준다. 초기화 연결과 요청 중 연결이 별도 수명이라는 점을 설명한다.

“기존 예제에는 시작할 때 데이터를 삭제하는 코드가 있었습니다. 관제 이력은 재시작 뒤에도 남아야 해서 없는 테이블만 생성합니다. 새 DB 연결마다 외래 키 검사를 켜고, 저장 실패 시 롤백합니다.”

[schema.sql](../app/schema.sql)에서는 모든 테이블을 줄마다 읽지 말고 아래 핵심 관계를 보여준다.

```text
robots → 최신 상태 / 상태 이력
maps → map_latest (현재 표시 지도)
AMR1·AMR2 × global·local → costmap_latest (source별 최신 격자)
robots → events → event_evidence (한 장의 경로)
users + events → event_changes
robots → commands / patrol_runs / handovers
patrol_runs → patrol_visits
```

“이미지는 파일로 보관하고 DB에는 경로를 저장합니다. message_id UNIQUE는 동일 메시지 중복을 막습니다. 이벤트 서비스는 같은 내용의 재수신을 200으로 인정하고 같은 ID의 다른 내용은 409로 거부합니다.”

### 13~17분: 로그인 한 번 따라가기

[auth.py](../app/routes/auth.py)의 `login` → [auth_service.py](../app/services/auth_service.py)의 `authenticate` → [user.py](../app/models/user.py)의 `find_for_login` → 다시 `login`의 세션 생성 → 기본 페이지 순으로 이동한다.

“비밀번호 원문을 DB에 저장하지 않고 해시만 저장합니다. 로그인 요청에서는 해시를 비교합니다. 성공하면 사용자 ID를 세션에 기록합니다. 권한은 세션 값을 믿고 고정하지 않고 요청마다 DB에서 다시 확인합니다.”

[security.py](../app/security.py)의 `roles_required`와 사용자 로딩을 보여준다. 관리자 기능은 서버에서도 차단함을 시연한다. CSRF는 다른 경로에서 위조된 변경 요청을 보내는 것을 막기 위한 세션별 토큰이라고 설명한다.

5~9단계에서는 같은 파일의 `CSRF_EXEMPT_ENDPOINTS` 분기를 이어서 보여준다. “장치 API를 보호하지 않는 예외가 아닙니다. 브라우저 폼의 CSRF 대신 상태·지도·이벤트·영상 입력 경로가 공통 `X-Robot-Token`을 검사합니다. 사용자 상태 변경은 로그인·역할·CSRF를 모두 검사합니다.”

### 17~20분: 로봇 상태 한 건 따라가기

[routes/robots.py](../app/routes/robots.py)의 `receive_status` → [robot_service.py](../app/services/robot_service.py)의 `receive_status`, `validate_status` → [robot.py](../app/models/robot.py)의 `store_status` → [dashboard.js](../app/static/js/dashboard.js)의 `refreshRobotStatus` 순으로 연다.

시연 순서:

1. AMR1의 배터리·좌표·순찰 중 상태를 `POST /api/robots/status`로 보낸다.
2. 응답 201과 대시보드 카드·왼쪽 연결 상태 갱신을 확인한다.
3. 같은 message_id와 같은 내용을 다시 보내 200 `duplicate`이고 이력이 늘지 않음을 보여준다.
4. 같은 ID에 배터리만 바꿔 409 충돌을 확인한다.
5. 더 오래된 observed_at의 다른 ID를 보내 409이며 현재 카드가 되돌아가지 않음을 확인한다.
6. 15초간 새 입력을 보내지 않아 화면 연결 상태가 오프라인으로 바뀌는 것을 확인한다.

설명 멘트: “route는 전송 규약과 HTTP 응답을 맡고, service는 ROS가 와도 재사용할 내부 검증을 맡습니다. model은 `BEGIN IMMEDIATE` 뒤 중복과 시간 순서를 판단해 이력 INSERT와 최신 UPSERT를 한 번에 커밋합니다. 웹 페이지는 2초마다 로그인 전용 GET API를 조회합니다.”

DB에서는 다음 관계만 보여준다.

```text
robots 1 ── 1 robot_latest_status
robots 1 ── N robot_status_history
```

“최신 테이블은 카드 조회를 빠르고 단순하게 하고, 이력 테이블은 이전 값을 지우지 않습니다. 재전송 ID는 전체 이력에서 UNIQUE입니다.”

이어 [map_service.py](../app/services/map_service.py)의 `validate_map` → `occupancy_to_png` → `dashboard_map`을 보여준다.

“Nav2 지도는 사진이 아니라 점유 격자입니다. 격자를 PNG로 바꾸고 DB에는 해상도·크기·원점·yaw와 이미지 경로를 저장합니다. 로봇 좌표에서 지도 원점을 빼고 역회전한 뒤 resolution으로 나누며, PNG Y축 방향을 맞추기 위해 높이에서 뺍니다.”

이어 `costmap_service.receive_costmap`과 화면의 **DYNAMIC COSTMAP** 선택 상자를 보여준다. “동적 costmap도 OccupancyGrid 검증·PNG 변환을 재사용하지만 고주기 이력을 쌓지 않고 AMR·global/local별 최신 한 장만 유지합니다. 실제 TF 상호운용 전에는 정적 지도에 임의로 겹치지 않고 별도 미리보기로 제공합니다.”

지도 시연 순서:

1. `tools/send_demo_map.py`로 수동 시연 지도를 보낸다.
2. 지도 상태가 `NAV 지도 수신`으로 바뀌는지 확인한다.
3. AMR1 위치 두 건과 AMR2 한 건을 보내 마커 2개와 AMR1 최근 경로를 확인한다.
4. frame_id를 `odom`으로 보내 좌표계 불일치 문구를 확인한다.
5. 지도 범위 밖 좌표를 보내 마커 대신 범위 이탈 문구를 확인한다.

“브라우저는 점유 격자 전체를 2초마다 받지 않습니다. 저장된 PNG와 작은 메타데이터·마커·경로 JSON을 분리해 조회합니다. 실제 ROS 토픽이 정해지면 adapter가 같은 서비스에 OccupancyGrid를 전달합니다.”

### 20~23분: 화재 이벤트 한 건 따라가기

[routes/events.py](../app/routes/events.py)의 `receive_event` → [event_service.py](../app/services/event_service.py)의 `validate_event`, `validate_evidence`, `receive_event` → [event.py](../app/models/event.py)의 `store_event` 순으로 연다.

시연 순서:

1. `tools/send_demo_event.py --robot AMR2 --risk HIGH`로 화재 메타데이터와 PNG 한 장을 보낸다.
2. HTTP 201 `accepted`, 이벤트 ID와 `NEW` 상태를 확인한다.
3. `events`의 AMR2·FIRE·좌표·HIGH·NEW 행과 `event_evidence`의 같은 event_id 경로를 보여준다.
4. `instance/evidence`에 이미지 파일 한 장이 있고 DB에는 바이너리가 없음을 설명한다.
5. 테스트에서 같은 내용 재전송은 200 `duplicate`, 같은 ID의 다른 내용은 409임을 보여준다.
6. 대시보드에 새 행과 썸네일이 나타나는지 확인하고 상세 화면을 연다.
7. 관제자로 `신규 → 확인중`을 기록하고 사용자·시각·메모가 처리 이력에 남는지 확인한다.
8. 조회자 변경 차단, 잘못된 단계 건너뛰기와 DB 경로 이탈 차단 테스트를 보여준다.

설명 멘트: “route는 장치 토큰과 multipart 규약을, service는 로봇·화재·좌표·위험도·시각과 이미지 바이트를 검증합니다. 파일을 먼저 원자적으로 완성한 뒤 model이 이벤트와 증거 경로를 한 트랜잭션으로 저장합니다. 브라우저는 최근 50건을 3초마다 조회하고, 상태와 메모는 별도 감사 이력에 남깁니다.”

사진 출처는 로봇1로 고정하지 않고 이벤트의 `robot_id`로 결정한다. 위험도 `HIGH·MEDIUM·LOW`와 처리 상태는 다른 개념이다. 저장 성공 응답은 수신 확인이며 다음 행동 명령이 아니다. `WORK_REQUESTED`도 외부 조치 요청을 기록할 뿐 로봇 명령을 만들지 않는다.

### 이벤트 설명 중 함께 말할 시스템 경계

“시스템 모니터는 로봇 상태·Navigation 결과·이벤트를 관제하고 기록합니다. 순찰 시작·복귀·대피 같은 운영 명령 요청은 별도 로봇·미션 모듈이 담당합니다.”

```text
Nav2 / 로봇 / 인식 모듈 → ros_adapter → 상태·지도·이벤트 서비스
→ SQLite·파일 → 로그인 대시보드
```

현재 `POST /api/maps/current`, `POST /api/robots/status`, `POST /api/events`, `POST /api/cameras/{camera_id}/frame`은 ROS 연결 전 검증용 입력이다. 실제 토픽명·메시지 타입이 정해지면 adapter를 추가하며 검증·저장 서비스는 재사용한다. `/map`만으로 동적 장애물을 판단하지 않고 costmap 결과가 있을 때 별도 표시한다.

### 23~25분: 네 카메라 최신 영상

[routes/cameras.py](../app/routes/cameras.py)의 `receive_frame` → [camera_service.py](../app/services/camera_service.py)의 `validate_frame`, `receive_frame`, `dashboard_cameras` → [cameras.js](../app/static/js/cameras.js)의 `refreshCameras` 순으로 연다.

시연 순서:

1. `tools/send_demo_video.py`를 실행해 AMR1·AMR2·고정 웹캠 1·2에 서로 다른 움직이는 시연 프레임을 보낸다.
2. 네 카드가 `LIVE`와 `방금 수신`으로 바뀌고 영상이 갱신되는지 확인한다.
3. 전송을 끝내고 5초 뒤 최근 프레임은 남지만 `연결 끊김`으로 바뀌는지 확인한다.
4. 미로그인 브라우저에서 영상 URL에 직접 접근하면 로그인 화면으로 이동하는 테스트를 설명한다.

설명 멘트: “실시간 일반 영상은 DB에 저장하지 않고 카메라별 최신 파일 한 장만 덮어씁니다. route는 토큰과 HTTP 규약, service는 이미지·시각 검증과 순서·원자적 교체를 담당합니다. 화면은 1초마다 작은 상태 JSON을 받고 해시가 바뀐 영상만 다시 요청합니다. 실제 ROS 영상은 adapter가 같은 service 입력으로 변환합니다.”

### 25~27분: 통합 이력 검색

[routes/history.py](../app/routes/history.py)의 `index`, `search_api` → [history_service.py](../app/services/history_service.py)의 `validate_filters`, `search_history` → [history.py](../app/models/history.py)의 `search` 순으로 연다.

시연 순서:

1. 대시보드에서 **통합 이력 검색**을 열어 사건·처리·상태·순찰·교대 기록이 시간순으로 합쳐지는 것을 보여준다.
2. 기록 종류를 화재 이벤트, 위험도를 상으로 선택해 결과가 해당 사건으로 좁혀지는지 확인한다.
3. AMR, 한국 날짜, 처리 상태와 메모·관측점 검색 예를 보여준다.
4. 화재 사건의 증거 이미지 링크와 50건 이후 이전·다음 페이지를 설명한다.

설명 멘트: “기록을 새 통합 테이블에 복사하지 않고 기존 다섯 테이블을 공통 열로 SELECT하고 UNION합니다. route는 로그인과 HTML·JSON 응답, service는 허용 조건과 한국 날짜의 UTC 변환, model은 매개변수 SQL과 시간순 페이지 조회를 담당합니다. 시스템 모니터가 생성하지 않는 명령과 일반 영상은 검색 대상이 아닙니다.”

### 27~29분: 검증 증거

[tests/test_database.py](../tests/test_database.py)에서 재시작 데이터 보존, [tests/test_auth.py](../tests/test_auth.py)에서 세션 분리·권한 변경을 대표로 보여준다.

기록된 현재 검증: 2026-09-08 ROS를 source한 전체 실행에서 **120개 시험과 86개 subtest 통과**를 확인했다. 별도 프로세스 DDS 시험 6개도 모두 통과했으며, 첫 KeepoutStatus가 첫 RobotStatus보다 먼저 도착하는 순서를 포함해 callback 처리 실패 0과 DB 외래 키 오류 0을 확인했다. 실제 상대 publisher와 여러 PC 네트워크는 아직 시험하지 않았다.

### 29~30분: 현재 한계와 질문

발표 시점에 맞춰 아래 상태를 갱신한다.

- ROS 실제 토픽·메시지와 좌표계 연동 여부.
- Nav2 costmap 동적 장애물과 관측점·도크의 실제 좌표.
- 임시 HTTP 입력의 장치 인증과 중복·재시도 처리 여부.
- 여러 PC 접속·영상 네 개의 성능·동시 쓰기 검증 여부.
- 로컬 개발 서버와 실제 운영 배포의 차이.
- SQLite 테이블 구조 변경 시 마이그레이션 방식.

## 3. 현재 가능한 시연

1. 서버에서 최초 관리자 계정을 생성한다. 명령은 README를 참고한다.
2. 미로그인 상태로 `/`를 열어 로그인 화면으로 이동하는지 확인한다.
3. 잘못된 비밀번호로 실패 안내를 보고 올바른 비밀번호로 로그인한다.
4. 사용자 관리에서 시연용 조회자 계정을 만든다.
5. 다른 브라우저/시크릿 창에서 조회자로 로그인한다.
6. 조회자가 `/admin/users`를 직접 열어도 접근이 차단되는 것을 보여준다.
7. 관리자에서 조회자를 비활성화하고 조회자 화면을 새로고침해 로그인 화면으로 이동하는지 확인한다.
8. 관리자 로그아웃 후 보호 페이지에 다시 접근할 수 없는 것을 확인한다.

시연용 계정만 사용한다. 실제 비밀번호 입력과 세션 키·쿠키는 영상이나 발표 자료에 노출하지 않는다. 테스트 클라이언트로 검증한 것과 실제 브라우저에서 시연한 것은 따로 기록한다.

## 4. 예상 질문과 답변

| 질문 | 답변 요지 |
| --- | --- |
| Flask 실행만 하면 DB가 자동 연결되나? | create_app에 우리가 초기화 호출을 넣었다. Flask 자체의 자동 기능은 아니다. |
| day5를 그대로 복사했나? | 기본 실행·템플릿·세션·SQL 흐름을 참고하고 기능별 구조·DB 보존·인증 규칙을 추가했다. |
| 왜 DB 파일을 instance에 두나? | 실행 중 생성되는 데이터와 소스 코드를 분리하고 경로를 일정하게 관리한다. |
| 왜 최신 상태와 이력을 나누나? | 현재 상태 조회와 과거 기록 보존의 목적이 다르기 때문이다. |
| 여러 명이 로그인할 수 있나? | 사용자별 브라우저 세션을 분리했다. 실제 여러 PC 부하 검증은 별도 단계다. |
| 권한을 바꾸면 재로그인해야 하나? | 매 요청 DB 권한을 확인해서 다음 요청에 반영한다. |
| 관리자 버튼만 숨기면 안 되나? | 직접 URL·POST 접근이 가능하므로 서버에서도 권한을 검사해야 한다. |
| 비밀번호를 복호화해서 비교하나? | 해시는 복호화하지 않는다. 해시 검증 함수로 일치 여부를 판단한다. |
| 이미지를 받으면 다음 행동을 바로 지시하나? | 시스템 모니터는 이벤트를 관제·기록하며 운영 명령 요청은 별도 로봇·미션 모듈이 담당한다. |
| 실제 퍼블리셔가 없는데 ROS 연결을 구현했나? | 공용 메시지를 PC 3에서 빌드하고 별도 프로세스의 실제 rclpy로 현재 활성 입력 25개와 ACK 2개를 검증했다. 실제 상대 publisher·PC 간 QoS 상호운용은 NOT_RUN이다. |
| 이벤트와 증적 순서가 바뀌면 실패하나? | 아니다. event_id·evidence_id로 독립 보관하고 둘이 모두 완성된 시점에 연결한다. 누락 chunk는 INCOMPLETE ACK로 알린다. |
| chunk 이미지가 DB에 계속 쌓이나? | 조립 중에만 BLOB을 두며 완료·거부 후에는 message_id·index·hash 영수증만 남기고 data를 NULL로 비운다. 완성 이미지는 파일로 저장한다. |
| costmap을 정적 지도에 바로 겹치지 않은 이유는? | source마다 원점·해상도·범위가 다를 수 있고 TF 실연동이 아직 없어, 잘못된 좌표 합성을 피하고 네 최신 격자를 선택형 미리보기로 분리했다. |
| WAL이면 동시 쓰기가 무제한인가? | 아니다. 읽기·쓰기 경합을 줄이지만 쓰기는 한 번에 하나다. |
| 13단계 성능시험은 실제 운영 성능인가? | 아니다. 임시 Flask client와 SQLite로 병목을 미리 측정한 결과다. 실제 PC·ROS 네트워크 성능은 후속 통합시험에서 확인한다. |
| 테이블이 있으면 기능도 완성인가? | 아니다. 서비스·API·UI·실패 처리를 구현하고 검증해야 기능이 완성된다. |
| 대시보드의 —는 로봇 고장인가? | 아니다. 4단계는 화면 배치이며 아직 데이터를 받지 않아 값이 없다는 뜻이다. |
| 주차장 그림은 실제 지도인가? | 아니다. 등록 전 배치 예시라고 표시했다. 실제 지도·좌표는 6단계에서 연결한다. |
| 로봇 API도 CSRF를 껐으니 누구나 보낼 수 있나? | 아니다. 장치 endpoint만 브라우저 CSRF 대신 서버의 전용 장치 토큰을 검사하며 미설정 시 닫힌다. |
| 같은 상태가 두 번 오면 이력도 두 개인가? | message_id와 내용이 같으면 재전송으로 보고 200을 반환하지만 추가 저장하지 않는다. |
| 늦게 도착한 상태가 현재 카드를 바꾸나? | 로봇별 observed_at을 비교해 같거나 오래된 다른 메시지는 409로 거부한다. |
| 온라인 값만 받으면 계속 온라인인가? | 마지막 서버 수신 후 기본 15초가 지나면 화면에서 오프라인으로 계산한다. |
| ROS 토픽으로 바꾸면 전부 다시 짜나? | adapter가 토픽 메시지를 현재 내부 필드로 변환해 service를 호출하므로 검증·DB·화면 흐름은 재사용한다. |
| Nav2 지도는 이미지 토픽인가? | 보통 `nav_msgs/OccupancyGrid`다. 점유 격자를 서버에서 PNG로 변환한다. |
| `/map`만 받으면 현재 장애물이 보이나? | 정적 지도만 보인다. 현재 구현은 네 costmap 토픽을 별도 미리보기로 표시하며, 실제 TF 검증 전에는 정적 지도와 임의 합성하지 않는다. |
| frame_id가 odom이면 바로 그리나? | 지도 frame과 다르면 TF 변환 근거가 없으므로 마커를 숨기고 불일치를 표시한다. |
| 이벤트 이미지는 DB에 넣나? | 이미지 파일은 `instance/evidence`에 두고 DB에는 한 이벤트당 한 경로만 저장한다. |
| 성공 응답이면 로봇이 다음 행동을 하나? | 아니다. 201은 이벤트와 이미지 수신·기록 완료이며 다음 행동 명령은 별도 모듈의 책임이다. |
| 로봇 상태보다 이벤트가 먼저 오면 실패하나? | AMR1·AMR2로 검증된 경우 기본 로봇 행을 준비한 뒤 이벤트를 저장한다. |
| 조회자도 이벤트 상태를 바꿀 수 있나? | 목록·상세 조회만 가능하며 변경 API는 관리자·관제자만 접근한다. |
| 작업요청 상태가 로봇 명령인가? | 아니다. 외부 조치 요청을 했다는 관제 기록이며 `commands` 행이나 로봇 메시지를 생성하지 않는다. |
| 통합 이력은 새 테이블에 다시 저장하나? | 아니다. 기존 사건·처리·상태·순찰·교대 테이블을 조건에 맞게 조회해 공통 결과로 합친다. |
| 왜 명령과 일반 영상은 검색에 없나? | 시스템 모니터는 운영 명령을 생성하지 않고 일반 영상도 보존하지 않는다. 이벤트 증거 이미지만 연결한다. |
| 날짜 검색은 UTC인가? | 사용자는 한국 날짜로 입력하고 서버가 해당 날짜의 시작과 다음 날 시작을 UTC로 변환한다. |

## 5. 발표 전 준비

- 현재 기능 상태와 이 문서의 예정 표기를 맞춘다.
- 플로우차트, UI 목업, DB 구조, 실제 페이지, 대표 함수 탭을 미리 준비한다.
- 사용하는 서버 포트를 확인한다. 기본은 5000이며 3단계 화면 검증에는 임시로 5001을 사용했다.
- 4단계 화면 검증은 실제 DB를 사용하지 않는 임시 사본과 5002번 포트로 진행했다. 프로젝트에 적용한 뒤에는 기본 서버를 재시작해 기존 계정으로 접속한다.
- 5단계 상태 시연 전 서버에 `SYSMON_ROBOT_API_KEY`를 설정하고, 요청 예시의 observed_at을 현재 시간대로 바꾼다. 토큰 값은 화면 녹화에 노출하지 않는다.
- 6단계 지도 시연은 같은 토큰을 설정한 터미널에서 `.venv/bin/python tools/send_demo_map.py`를 실행한다. 시연용 지도임을 설명한다.
- 7단계 이벤트 시연은 같은 토큰으로 `.venv/bin/python tools/send_demo_event.py --robot AMR1 --risk HIGH`를 실행한다. 생성 PNG가 실제 카메라 사진이 아님을 설명한다.
- 8단계는 관제자 계정으로 상세 보기를 열어 `신규 → 확인중`과 메모를 기록하고, 조회자 계정에는 변경 영역이 없음을 확인한다.
- 9단계는 `.venv/bin/python tools/send_demo_video.py`를 실행해 네 영상의 LIVE 상태를 보인 뒤, 종료 5초 후 연결 끊김 표시도 보여준다.
- 10단계는 전체 이력을 연 뒤 화재 이벤트·위험도 상·AMR·날짜·메모 검색과 증거 이미지 링크를 확인한다.
- 11단계는 `send_demo_event.py --type LEAK`, `--type OBSTACLE`과 `send_demo_vehicle_access.py`로 세 이상 이벤트와 이미지 없는 입차·출차 내역을 확인한다.
- 두 로그의 `표시 초기화`를 누른 뒤 목록은 비워지고 통합 이력 검색에는 기존 기록이 남는 것을 확인한다.
- 기존 DB를 초기화하거나 삭제하지 말고 시연용 입력과 실제 데이터를 구분한다.
- 최종 테스트 결과와 시연 실패 시 보여줄 결과 화면을 준비한다.
- 타이머로 한 번 리허설하고, 긴 설명은 코드 줄 읽기보다 데이터 이동 중심으로 줄인다.

## 현재 대시보드 배치 설명

- 상단 상태 줄에서 시스템과 두 로봇의 배터리·위치·임무·최근 수신을 비교한다.
- 중앙 관제 영역은 `지도 | 네 카메라 2×2 | 최근 이벤트·입출차` 순서다.
- 네 영상은 모두 동시에 갱신하며, 이벤트 종류를 선택하면 상세 창에서 좌표·감지 로봇·처리 상태·증거 이미지를 확인한다. 로그가 누적되어도 영상 높이는 고정되고 각 로그 표만 내부 스크롤된다.
- 전체 사건·상태·순찰·교대 기록은 통합 이력 검색 화면에서 조회한다.
