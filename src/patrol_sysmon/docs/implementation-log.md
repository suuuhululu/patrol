# 시스템 모니터 구현 기록

최종 갱신: 2026-09-06, 11단계. 최초 작성은 2026-09-05이며 1~3단계는 대화의 구현·검증 기록과 당시 파일을 바탕으로 정리했다. 분 단위 작업 시간이나 Git 커밋은 추정하지 않았다. 이후 단계는 이 문서 아래에 이어서 기록한다.

## 1. 무엇을 만드는가

지하주차장의 AMR1·AMR2를 관제하고 상태·지도·이벤트·순찰·교대 이력을 기록하는 Flask + SQLite 웹 시스템이다. 관제·기록 담당자의 구현 범위는 웹 화면, 서버 API, 데이터 저장, 외부 모듈과의 연결이다.

현재 완료: 서버 기본 구조, DB 초기화, 인증·권한, 기본 대시보드, AMR 상태 수신·저장·표시, 점유 지도 수신·PNG·로봇 위치와 최근 경로 표시, 화재 이벤트·증거 이미지 수신·저장, 이벤트 목록·상세·처리 상태·메모 이력 UI, 네 카메라 최신 프레임 수신·표시·단절 감지, 사건·처리·상태·순찰·교대 통합 이력 검색.

아직 미구현: 실제 ROS·Nav2·TF·costmap·영상 토픽 연결과 실제 환경 전체 통합. 운영 명령 요청은 시스템 모니터 범위에서 제외한다. 관련 DB 테이블과 화면이 존재하는 것과 데이터 처리 기능의 완성은 구분한다.

## 2. 회의에서 정한 구현 원칙

| 원칙 | 코드·설계에 반영하는 방식 |
| --- | --- |
| 기능별 파일 분리 | routes는 HTTP·화면, services는 처리 규칙, models는 DB 접근, database는 연결·초기화 |
| 기존 day5 활용 | 기본 Flask·템플릿·세션·DB 예제의 흐름을 참고하고 프로젝트 요구에 맞게 분리 |
| 실행 시 데이터 보존 | `CREATE TABLE IF NOT EXISTS` 사용, 기존 예제의 시작 시 DELETE 제거 |
| 비밀번호 원문 저장 금지 | 계정 생성 시 scrypt 해시 생성, 로그인 시 해시 검증 |
| 로봇 출처 고정 금지 | 이벤트의 robot_id로 AMR1 또는 AMR2와 증거 이미지 연결 |
| 영상 전체를 DB에 저장하지 않음 | 이벤트 증거 한 장만 보존하며 실시간 영상은 카메라별 최신 파일 한 장만 덮어쓰기 |
| 이벤트 필드 | 시각·화재 종류·좌표·위험도 상/중/하·감지 로봇·증거 이미지 한 장 |
| 이벤트 중복 방지 | message_id UNIQUE와 서비스의 동일 재전송·ID 충돌 판정 구현 |
| 처리 상태와 위험도 구분 | 신규→확인중→작업요청→조치완료는 작업 상태, 상/중/하는 위험도 |
| 시스템 모니터는 운영 명령을 요청하지 않음 | 순찰·복귀·대피 요청은 별도 로봇·미션 모듈 담당 |
| ROS 인터페이스 미확정 | 우선 내부 형식·임시 HTTP API, 이후 adapter에서 외부 메시지 변환 |
| 가상 이벤트 시연 가능 | 수동 도구가 실제 `POST /api/events`와 같은 저장 서비스를 호출 |
| 읽기 쉬운 플로우차트 | 긴 복귀선 대신 연결기 A를 사용, A는 데이터 수신 대기를 뜻함 |

추가 확인이 필요한 결정:

- 이미지 수신 완료 ACK가 필요하다면 이벤트 저장 성공을 알리는 용도로만 정의한다. 다음 행동 명령은 시스템 모니터가 발행하지 않는다.
- ROS 토픽명, 메시지 형식, 좌표계, 위험도 산정 기준은 연동 담당자와 확정한다.
- ROS와 임시 HTTP API의 입력 부분을 분리하면 기존 서비스를 재사용할 수 있지만, 최종 인터페이스 차이에 따라 내부 필드·DB 조정이 필요할 수 있다.

## 3. 단계별 진행표

| 단계 | 기능 | 현재 상태·완료 기준 |
| --- | --- | --- |
| 1 | 프로젝트 구성·Flask 실행 | 완료: 기본 페이지와 CSS 응답 검증 |
| 2 | DB 폴더·연결·필수 테이블 | 완료: 기존 11개와 지도 2개 테이블, 재시작 데이터 보존 검증 |
| 3 | 로그인·로그아웃·권한 관리 | 완료: 계정 생성·세션·관리자 전용 접근 검증 |
| 4 | 기본 대시보드 | 완료: 지도 자리·상태 카드·영상 4개·빈 로그 배치 |
| 5 | 로봇 상태 수신·검증·저장 | 완료: AMR1·AMR2 상태 갱신·이력·중복·단절 표시 |
| 6 | 지도 | 완료: 점유 지도·로봇 위치·최근 경로, 좌표 오류 표시 |
| 7 | 이벤트·증거 이미지 수신 | 완료: 화재 검증·중복 처리·파일 및 DB 저장·수동 시연 도구 |
| 8 | 이벤트 로그·상세 | 완료: 최근 목록·썸네일·상세·권한별 순차 상태와 메모 이력 |
| 9 | 영상 | 완료: 최신 프레임 수신·네 영역 표시·중복/순서·5초 단절 처리 |
| 10 | 이력 검색 | 완료: 사건·처리·상태·순찰·교대 조건 검색·50건 페이지 |
| 11 | 이벤트 확장·차량 입출차 | 완료: 누수·장애물·입차·출차·표시 초기화·통합 이력 |
| 12 | ROS 연동 | 예정: 인터페이스 확정 후 실제 로봇·인식 모듈 검증 |
| 13 | 전체 통합 | 예정: AMR 2대·다중 접속·실패 복구 검증 |
| 14 | 시연·코드리뷰 | 예정: 사용자 시나리오 영상과 30분 리뷰 |

## 4. 1단계 — 기본 구조

### 목적과 작업 순서

1. `/home/hun/finalproject/day5`의 예제를 확인했다.
2. `0_app.py`의 Flask 생성·경로·템플릿 표시를 기반으로 별도 `sysmon` 폴더를 만들었다.
3. 실행, 앱 생성, 페이지 처리, HTML, CSS를 각각 분리했다.
4. 이후 기능을 넣을 routes·services·models 패키지를 준비했다.
5. 가상환경에 Flask를 설치하고 서버·기본 페이지를 확인했다.

### 주요 파일과 실행 흐름

```text
run.py
  → app/__init__.py:create_app()
  → routes/dashboard.py의 Blueprint 등록
  → 브라우저 GET /
  → dashboard.index()
  → templates/index.html 렌더링
  → static/css/style.css 적용
```

`create_app()`은 앱을 만드는 함수다. 테스트에서 임시 설정을 넣어 별도 앱을 생성하기 쉽도록 하는 기반이기도 하다. Blueprint는 같은 기능의 URL 처리를 묶어 앱에 등록하는 Flask의 방식이다.

### 검증과 다음 단계

- 당시 기본 페이지 GET `/`와 CSS 응답이 200인지, 한글 본문이 나오는지 확인했다.
- 현재는 3단계 로그인 보호가 추가되어 미로그인 GET `/`는 302로 `/login`에 이동한다. 이것은 의도한 동작 변경이다.
- 1단계 당시에는 DB·로그인·관제 데이터가 없었다.

## 5. 2단계 — SQLite 초기화

### 목적과 작업 순서

1. 앱 설정에 DB·증거 폴더 경로를 등록했다.
2. `database.py`로 연결·정리·초기화 코드를 분리했다.
3. `schema.sql`에 11개 테이블과 제약·인덱스를 정의했다.
4. 앱 생성 시 초기화를 호출하고, 실패하면 서버 시작을 중단하도록 했다.
5. 임시 DB 테스트와 실제 개발 DB의 테이블·무결성을 확인했다.

### 플로우차트에서 코드로 연결

| 플로우차트 단계 | 코드 위치·역할 |
| --- | --- |
| DB 경로·폴더 준비 | `create_app()`의 설정, `database.init_db()`의 mkdir |
| SQLite 연결 | `database.get_db()`의 sqlite3.connect |
| 외래 키 활성화 | 새 연결마다 PRAGMA foreign_keys = ON |
| 테이블 존재 판단·생성 | schema.sql의 CREATE TABLE IF NOT EXISTS |
| 초기화 성공 | 트랜잭션 COMMIT 후 앱 구성 계속 |
| 초기화 실패 | ROLLBACK, logger.exception, 예외 재발생 |
| 연결 정리 | teardown_appcontext로 database.close_db 호출 |

Flask 자체가 SQLite를 자동으로 연결하는 것은 아니다. 우리가 앱 생성 과정에 `database.init_app(app)`을 넣었기 때문에 실행 때 초기화된다. 이후 요청에서는 `get_db()`가 필요할 때 연결을 열고 Flask의 `g`에 보관한다.

### 데이터 구조의 이유

- `robots`는 기본 정보, `robot_latest_status`는 로봇별 최신 한 행, `robot_status_history`는 이전 수신 기록이다.
- `events`는 이벤트 정보, `event_evidence`는 한 장의 이미지 경로, `event_changes`는 사용자 처리 이력이다.
- `commands`는 요청·결과, `patrol_runs`·`patrol_visits`는 순찰과 관측점 방문, `handovers`는 교대 기록이다.
- `users`에는 username UNIQUE와 password_hash를 둬 3단계 로그인을 준비했다.
- 외래 키는 존재하지 않는 로봇·이벤트와의 연결을 막는다.
- UNIQUE는 중복 메시지·이벤트당 두 번째 증거 행을 차단한다. 재수신 시 기존 이벤트를 반환하는 API 처리는 후속 단계에서 구현한다.
- 위험도와 상태의 CHECK 제약은 허용하지 않은 값의 저장을 막는다. 상태를 순서대로 변경하는 규칙까지 검사하는 것은 아니다.
- 테이블 존재 판단을 SQL 한 줄로 표현했지만 플로우차트의 ‘있으면 유지, 없으면 생성’ 의미와 같다.

### 다중 접속을 위한 준비와 한계

요청별 연결로 사용자의 DB 연결 공유를 피했다. WAL은 읽기·쓰기 경합을 줄이고, 연결의 5초 timeout은 잠긴 DB를 기다리게 한다. SQLite 쓰기는 여전히 한 번에 하나다. 이 설정만으로 다중 PC 배포나 부하 검증이 완료된 것은 아니다.

### 검증 기록

- 2단계 당시 `tests/test_database.py`의 5개 테스트 통과.
- 최초 실행에서 빈 테이블·폴더 생성 확인.
- 재시작 시 이벤트·증거 경로·증거 파일 보존 확인.
- 중복 message_id, 없는 robot_id, 잘못된 위험도, 추가 증거 행 차단 확인.
- 문맥 종료 후 연결 닫힘·미커밋 데이터 롤백 확인.
- 잘못된 저장 경로에서 오류 기록·앱 시작 중단 확인.
- 실제 개발 DB에서 테이블 11개, integrity_check 결과 ok 확인.

### 남은 사항

계정·로봇·이벤트를 자동으로 입력하지 않았다. 이후 구조 변경에는 마이그레이션이 필요하다. `IF NOT EXISTS`는 기존 테이블 열을 수정하지 않는다.

## 6. 3단계 — 인증과 권한

### 목적과 작업 순서

1. `models/user.py`에 사용자 SQL 조회·생성·권한 변경을 분리했다.
2. `services/auth_service.py`에 입력 검사와 비밀번호 해시 생성·검증을 구현했다.
3. `security.py`에 사용자 로딩·세션 키·CSRF·로그인 및 권한 검사를 추가했다.
4. `routes/auth.py`에 로그인·로그아웃·관리자 계정 관리 경로와 CLI 명령을 연결했다.
5. 공통 템플릿과 로그인·사용자 관리 화면을 만들고 기본 페이지를 로그인 뒤로 이동했다.
6. 인증·권한 테스트와 기존 DB 테스트를 함께 실행했다.
7. 5000번에 기존 서버가 있어 5001번으로 별도 실행한 뒤 브라우저에서 로그인 화면을 확인했다. 기본 실행 설정은 여전히 5000번이다.

### 계정 생성 흐름

```text
최초 관리자: flask --app run create-admin
  → 아이디·비밀번호·확인 입력
  → auth_service.create_user()
  → 아이디·비밀번호 길이·권한 검증
  → generate_password_hash()
  → user_model.insert_user()
  → DB 커밋

추가 사용자: 관리자 로그인 → /admin/users의 계정 생성 폼
  → 같은 auth_service.create_user() 호출
```

최초 계정은 기본 비밀번호로 자동 생성하지 않는다. 서버 담당자가 터미널에서 입력한다. 중복 아이디는 오류를 안내하고 기존 계정과 비밀번호를 유지한다. 비밀번호 길이는 8~128자, 아이디는 영문·숫자·밑줄·점·하이픈 3~32자다.

### 로그인 요청의 실제 호출 순서

```text
GET /login → csrf_token() 생성 → 입력 폼 표시
POST /login
  → security의 before_request
      → 기존 사용자 세션 확인
      → CSRF 토큰 검증
  → auth.login()
  → auth_service.authenticate()
  → user_model.find_for_login() → users 조회
  → check_password_hash() + 활성 상태 확인
  → 성공: session.clear() → user_id 저장 → /로 이동
  → 실패: 같은 화면에 오류 안내(401)
GET /
  → before_request에서 DB 사용자·권한 재조회
  → login_required 검사
  → dashboard.index() → 사용자·권한 표시
```

잘못된 아이디·비밀번호·비활성 계정은 같은 안내로 응답한다. 없는 계정도 더미 해시를 검증한다. SQL은 매개변수 바인딩으로 입력값을 전달한다.

### 세션과 권한을 설명할 때

- Flask 서명 쿠키에 사용자 ID·CSRF 토큰·만료 관련 정보가 담긴다. 권한과 비밀번호 해시는 쿠키에 넣지 않는다. 서명은 위변조 확인 수단이며 쿠키 내용을 암호화하는 것은 아니다.
- 세션 유효기간은 로그인 후 8시간이다. 페이지를 요청할 때마다 만료 시점을 연장하지 않는다.
- `session.key`는 최초 생성 후 유지한다. 파일은 소유자만 읽고 쓸 수 있으며, 동시에 앱이 시작되어도 완성된 키 파일을 사용하도록 원자적으로 연결한다.
- 다른 브라우저의 세션은 분리된다. 같은 브라우저 프로필의 탭은 세션을 공유한다.
- `login_required`는 로그인 여부, `roles_required('ADMIN')`은 관리자 권한을 검사한다.
- 관리자 화면 링크를 숨기는 것에 더해 서버 경로에서도 검사하므로 직접 URL·POST로 접근해도 관제자·조회자는 403을 받는다.
- 모든 요청에서 DB를 다시 읽으므로 강등·비활성화는 기존 로그인에도 다음 요청부터 반영된다.
- 마지막 활성 관리자를 제거하지 않도록 `BEGIN IMMEDIATE` 안에서 관리자 수 확인과 UPDATE를 함께 처리한다.
- 로그아웃은 CSRF 토큰이 있는 POST로 현재 세션을 비운다. 다른 사용자 세션은 유지된다.

### 검증 기록과 범위

3단계 최종 실행: 아래 명령으로 총 **16개 테스트 통과**. 인증 11개 + DB 5개다. 이 문서를 작성하면서 테스트를 재실행한 것은 아니며, 직전 구현 검증 결과를 기록했다.

```bash
cd /home/hun/finalproject/sysmon
.venv/bin/python -m unittest discover -s tests -v
```

인증 테스트가 확인한 동작:

1. 미로그인 접근 이동, 잘못된 비밀번호·계정·SQL 형태 입력으로 인증 불가.
2. 비밀번호 해시 저장 및 중복 계정의 기존 비밀번호 보존.
3. 서로 다른 클라이언트의 로그인 분리, 한쪽 로그아웃 후 다른 쪽 유지.
4. CSRF 누락·위조·다른 세션 토큰·비ASCII 토큰 차단.
5. 관리자 계정 생성, 관제자·조회자의 관리 URL과 POST 차단.
6. 잘못된 아이디·권한·비밀번호·확인 값의 계정 생성 차단.
7. 기존 로그인에 권한 변경·비활성화 반영.
8. 마지막 관리자 강등·비활성화 차단.
9. CLI 관리자 생성 및 중복 생성 차단.
10. 재시작 후 계정·세션 키·유효 세션 유지, 키 파일 권한 확인.
11. 두 관리자의 동시 강등 요청에서 활성 관리자 한 명 유지.

브라우저에서는 로그인 폼·초기 관리자 미생성 안내와 좁은 화면 배치를 확인했다. 로그인 성공·관리자 폼 기능은 임시 DB와 Flask 테스트 클라이언트로 검증했다. 실제 여러 PC의 접속 부하나 HTTPS 운영 배포를 검증한 것은 아니다.

### 개발 중 수정한 문제

- `database.py` 첫 줄 설명 문자열 앞에 들여쓰기가 들어가 ImportError가 발생했다. 첫 줄의 불필요한 공백만 제거하고 다시 검증했다.
- 세션 키 파일을 생성하자마자 다른 프로세스가 읽는 경우를 고려해 임시 파일에 완성한 뒤 원자적으로 연결하도록 변경했다.
- 한글 등 비ASCII CSRF 입력도 서버 오류가 아닌 400으로 처리되도록 바이트 비교를 사용했다.
- 2단계의 ‘기본 페이지는 200’ 검증을 3단계의 ‘미로그인 기본 페이지는 302, 로그인 화면은 200’으로 변경했다.

## 7. 앞으로 매 단계 기록할 양식

```text
단계 / 작성 날짜:
요청·목표:
구현 전 상태:
실제 작업 순서:
변경 파일 및 주요 함수:
플로우차트 → 코드 대응:
사용자 동작 → HTTP → 서비스 → DB → 화면의 실행 흐름:
정상 / 실패 / 중복 / 권한 처리:
설계 이유와 day5에서 바뀐 부분:
실행한 검증 명령·결과·검증하지 않은 부분:
발생 문제와 해결:
기존 기능에 미친 영향:
남은 일·미확정 인터페이스:
30분 코드리뷰 문서에 반영한 내용:
```

## 8. 참고 파일

- [실행·기능 요약](../README.md)
- [30분 코드리뷰 진행안](code-review-30min.md)
- [프로젝트 작업 지침](../AGENTS.md)
- [앱 생성](../app/__init__.py)
- [DB 초기화](../app/database.py), [테이블 구조](../app/schema.sql)
- [인증 경로](../app/routes/auth.py), [인증 서비스](../app/services/auth_service.py)
- [사용자 DB 접근](../app/models/user.py), [세션·권한 보호](../app/security.py)

## 9. 4단계 — 기본 대시보드 (2026-09-06)

### 목적과 구현 전 상태

로그인 후 보이던 사용자 이름·권한 안내 페이지를 지하주차장 관제 화면으로 확장했다. 예시 이미지의 왼쪽 메뉴, 지도, 로봇 두 대의 상태, 영상 네 영역, 하단 이벤트 로그 구성을 참고했다. 이번 범위는 화면 배치이고, 실제 데이터 수신은 5단계 이후다.

### 실제 작업 순서

1. AGENTS.md와 기존 인증·기본 템플릿을 읽었다.
2. 현재 환경에서 `finalproject`가 쓰기 허용 경로에 포함되지 않아 `/tmp`의 사본에서 변경과 검증을 준비했다. 실제 계정·DB·세션 키는 복사하지 않았다.
3. 공통 base 템플릿에 화면별 스타일·body 클래스·header·script 확장 지점을 추가했다.
4. dashboard.index에 로봇 두 대와 카메라 네 개의 표시용 식별자·이름을 구성했다.
5. index.html을 대시보드로 교체하고 전용 CSS·아이콘·한국 시간 표시 JS를 분리했다.
6. 인증·DB 테스트를 실행하고 임시 서버에서 데스크톱·모바일 화면과 메뉴·권한을 확인했다.
7. 모바일에서 빈 로그 안내가 표 너비 때문에 잘리는 것을 발견해 안내를 가로 스크롤 표 밖으로 옮겼다.
8. 실제 반영 대상은 화면·경로·문서 파일로 한정했다. 임시 테스트 계정·DB·서버 스크립트는 반영 대상에서 제외했다.

### 변경 파일과 역할

| 파일·함수 | 역할 |
| --- | --- |
| `routes/dashboard.py:index` | 표시할 로봇·카메라 슬롯을 구성하고 Jinja 템플릿에 전달 |
| `templates/base.html` | 기존 로그인·관리자 화면이 기본 스타일을 유지하도록 확장 block 추가 |
| `templates/index.html` | 메뉴·지도·로봇 카드·영상·빈 이벤트 표의 의미 있는 HTML 구성 |
| `templates/dashboard/icons.html:icon` | 외부 라이브러리 없는 공통 SVG 아이콘 |
| `static/css/dashboard.css` | 대시보드에만 적용되는 배치·색상·화면 크기 대응 |
| `static/js/dashboard.js:updateClock` | 브라우저 시계의 한국 시간 표시, 실제 장비 수신 시각과 구분 |

### 실행 흐름과 플로우차트 대응

```text
GET /
→ 기존 before_request의 세션·DB 사용자 검사
→ login_required
→ dashboard.index: 로봇·카메라 표시 슬롯 구성
→ index.html + base.html + 아이콘 매크로 렌더링
→ 브라우저에서 CSS 배치·한국 시간 표시
→ 지도 등록 대기·로봇 수신 대기·영상 미연결·빈 이벤트 로그 표시
```

플로우차트의 ‘대시보드 표시’와 ‘빈 이벤트 로그 표시’에 해당한다. ‘최신 로봇 상태 조회’, ‘최근 이벤트 조회’, ‘새 데이터 수신 후 갱신’은 아직 실행하지 않는다. 테이블이나 카드가 보인다고 실제 데이터 API가 연결된 것은 아니다.

### 설계 이유와 표시 원칙

- 알 수 없는 배터리를 0%로 표시하면 실제 방전 상태와 혼동하므로 `— %`로 표시했다. 위치·임무·최근 수신도 `—`다.
- 로봇·카메라 모두 연결 대기 또는 미연결로 표시한다. 연결 검증 없이 ‘시스템 정상’·‘온라인’·‘LIVE’를 표시하지 않는다.
- 지도 도식은 주차장 배치 예시라고 명시한다. 실제 관측점 좌표·경로·안전구역·도크는 6단계에서 연결한다.
- 증거 이미지 열은 감지 로봇(AMR1 또는 AMR2)의 이미지 한 장을 표시할 자리다. 임의 화재 행이나 사진을 생성하지 않았다.
- 현재 작동하는 화면 내 이동과 사용자 관리 링크만 제공했다. 명령·필터·사진 확대 버튼은 해당 기능 단계에서 구현한다.
- 로그인·로그아웃·계정 관리 로직과 DB 스키마는 바꾸지 않았다. 기존 한국어 기능 주석 방식을 유지했다.
- CSS는 대시보드 전용 파일과 클래스 아래에 둬 기존 인증 화면의 배치를 보존했다.
- 좁은 화면에서는 메뉴가 위로, 지도·상태·영상이 세로로 배치된다. 표만 가로 스크롤하고 빈 로그 안내는 화면 폭 안에서 읽힌다.

### 검증 결과

- 작업 사본에서 기존 `python -m unittest discover -s tests -v` 실행: **16개 통과**, 인증 11개·DB 5개.
- 실제 브라우저에서 임시 관리자 로그인→대시보드, 메뉴의 이벤트 로그 위치 이동, 사용자 관리 화면, 로그아웃을 확인했다.
- 임시 조회자로 로그인해 관리자 메뉴 숨김과 `/admin/users` 직접 접근 차단을 확인했다.
- 1440×1050: 지도 왼쪽·로봇 카드와 영상 오른쪽·로그 하단 배치. DOM 측정 페이지 너비 1425px로 뷰포트 1440px 이내.
- 390×844: 로봇·영상 한 열 배치. 페이지 너비 375px로 뷰포트 390px 이내. 이벤트 표 내부 너비는 680px로 내부 가로 스크롤을 사용.
- 영상 카드 네 개, 실제 video·iframe 요소는 없음을 확인했다. 이 단계에서 미구현 스트림을 요청하지 않는다.
- 마지막 HTML 수정 후 임시 서버를 재시작하고 모바일 빈 로그 문구가 잘리지 않는 것을 다시 확인했다.
- 실제 로봇·카메라·이벤트 수신, 여러 PC 부하 검증은 수행하지 않았다.

### 다음 단계와 코드리뷰 반영

다음은 5단계 로봇 상태 수신·검증·저장·표시다. `data-robot-id`와 `data-camera-id`가 붙은 영역을 후속 연결 지점으로 사용할 수 있다. 30분 리뷰 진행안에 현재 대시보드 화면 탐색, 반복 렌더링, 빈 값 처리, 반응형과 인증 유지 설명을 추가했다.

## 10. 5단계 — 로봇 상태 수신·저장·표시 (2026-09-06)

### 목적과 구현 전 상태

4단계의 AMR1·AMR2 카드는 항상 `수신 대기`, `—`를 표시했다. 5단계에서는 ROS 토픽명이 아직 정해지지 않은 조건에서 임시 HTTP 입력을 만들고, 검증한 상태를 SQLite 최신 행과 이력에 저장해 로그인 대시보드에 표시하도록 연결했다.

### 실제 작업 순서

1. 기존 스키마의 `robots`, `robot_latest_status`, `robot_status_history` 필드와 대시보드의 `data-robot-id` 연결 지점을 확인했다.
2. 현재 쓰기 허용 범위 밖인 실제 프로젝트 대신 `/tmp` 작업 사본에서 코드와 테스트를 준비했다. 복사된 instance 파일은 구현·검증·반영에 사용하지 않았다.
3. 앱 설정에 로봇 전용 토큰, 15초 연결 만료, 장치 API의 CSRF 예외 endpoint를 추가했다.
4. route에서 장치 토큰·JSON 형식을 검사하고 service에서 필드·숫자 범위·열거값·UTC 시각을 검증하도록 분리했다.
5. model의 한 트랜잭션 안에서 message_id 재전송, ID 충돌, 최신 시각 순서를 판정하고 이력 INSERT와 최신 행 UPSERT를 실행했다.
6. dashboard route가 DB 최신 값을 초기 HTML에 전달하도록 바꾸고, 로그인 전용 GET API와 JavaScript 2초 조회로 카드·왼쪽 상태를 갱신했다.
7. 기존 16개와 새 로봇 상태 9개 테스트를 함께 실행해 총 25개 통과를 확인했다.

### 변경 파일과 역할

| 파일·함수 | 역할 |
| --- | --- |
| `app/__init__.py:create_app` | 장치 토큰·연결 만료 설정, robots blueprint 등록 |
| `app/security.py:load_user_and_check_csrf` | 브라우저 변경 요청은 CSRF, 지정 장치 endpoint는 별도 토큰으로 분리 |
| `routes/robots.py:receive_status` | `POST /api/robots/status` 인증·응답 코드·DB 오류 처리 |
| `routes/robots.py:list_status` | 로그인된 브라우저의 `GET /api/robots/status` 조회 |
| `services/robot_service.py:validate_status` | 로봇 ID, message_id, 배터리·좌표, 상태값, 시간대 시각 검증·정규화 |
| `services/robot_service.py:dashboard_robots` | DB 행을 한국어 상태·좌표·한국 시각·연결 만료 표시로 변환 |
| `models/robot.py:store_status` | 중복·충돌·오래된 순서 판정, 기본 로봇·이력·최신 상태 원자적 저장 |
| `routes/dashboard.py:index` | DB 최신 상태와 전체 연결 요약을 첫 HTML에 전달 |
| `templates/index.html` | 상태값별 표시 요소와 JavaScript 연결용 data 속성 |
| `static/js/dashboard.js:refreshRobotStatus` | 2초 조회와 AMR1·AMR2 카드·사이드바 갱신 |
| `static/css/dashboard.css` | 온라인·오프라인·수신 대기와 배터리 막대 표현 |
| `tests/test_robot_status.py` | 인증·검증·저장·중복·순서·조회·만료·동시 재전송 검증 |

### 실행 흐름과 플로우차트 대응

```text
로봇/임시 adapter → POST /api/robots/status
→ 서버에 수신 토큰 설정됨? → 아니오: 503
→ X-Robot-Token 일치? → 아니오: 401
→ JSON·필수 필드·값 범위·시각 유효? → 아니오: 400, 저장 안 함
→ BEGIN IMMEDIATE
→ 같은 message_id 존재?
   → 내용도 같음: duplicate 200, 추가 저장 안 함
   → 내용 다름: 409, 롤백
→ 해당 로봇 최신 observed_at보다 새 데이터인가? → 아니오: 409, 롤백
→ robot_status_history INSERT
→ robot_latest_status UPSERT
→ COMMIT → accepted 201
→ 로그인 브라우저 GET /api/robots/status
→ 마지막 수신이 15초를 넘었는가? → 예: 화면 연결 상태 OFFLINE
→ 카드·왼쪽 장비 상태·전체 연결 요약 갱신
```

이 흐름은 플로우차트의 ‘로봇 상태’, ‘메시지 ID·순서 유효?’, ‘최신 상태 DB 갱신’, ‘로봇 상태 이력 저장’, ‘배터리·임무·연결 상태 표시’, ‘대시보드 갱신’에 해당한다. ROS 구독 앞단은 아직 없으며 나중에 `ros_adapter.py`가 동일한 `robot_service.receive_status`를 호출하면 저장 이후 흐름을 재사용할 수 있다.

### 설계 이유와 실패 처리

- 사용자 세션용 CSRF 토큰을 로봇 장치에 요구하지 않는다. 장치 입력 endpoint만 CSRF 대상에서 제외하고 `SYSMON_ROBOT_API_KEY`의 전용 토큰을 비교한다. 조회 API는 로그인 사용자만 접근한다.
- 장치 토큰이 서버에 설정되지 않으면 입력을 열어두지 않고 503으로 닫는다. 토큰 값을 HTML·JavaScript·문서에 저장하지 않는다.
- 수신된 `robot_id`는 실제 발신 로봇인 AMR1 또는 AMR2다. `로봇 ?`를 저장하지 않는다.
- 배터리는 0~100, 좌표는 NaN·무한대가 아닌 숫자, 시각은 시간대가 있는 ISO 8601로 제한한다. 저장 시 UTC 밀리초 형식으로 맞춘다.
- `message_id`와 내용이 모두 같은 재시도는 네트워크 재전송으로 보고 성공 응답하되 이력을 늘리지 않는다. 같은 ID로 내용이 바뀌면 충돌로 거부한다.
- 최신 상태보다 같거나 오래된 다른 메시지는 이력과 최신 상태 모두에 저장하지 않는다. 현재 카드가 과거 메시지로 되돌아가는 것을 막는다.
- 이력 INSERT와 최신 UPSERT는 한 트랜잭션이다. 중간 실패 시 둘 다 롤백한다. SQLite 잠금 등 일시 저장 오류는 503으로 반환해 발신 측이 재시도할 수 있다.
- 연결 상태는 마지막 수신 후 15초가 지나면 화면에서 오프라인으로 계산한다. DB 원본을 바꾸지 않아 이후 새 수신으로 다시 온라인이 될 수 있다.
- 브라우저에는 장치 토큰을 보내지 않는다. JavaScript는 로그인 쿠키로 읽기 API만 호출한다.
- 서버 시작 시 샘플 상태를 자동 입력하지 않는다. 첫 유효 상태를 받을 때 해당 로봇 기본 행을 만든다.

### 실제 검증 결과

작업 사본의 임시 DB에서 `.venv/bin/python -m unittest discover -s tests -v`를 실행했다. 총 **25개 통과**했으며 기존 인증 11개·DB 5개와 새 상태 9개다.

새 테스트에서 다음을 확인했다.

- 토큰 누락·불일치 401, 서버 토큰 미설정 503.
- 유효한 상태의 최신 행과 이력 한 행 저장.
- 더 새 상태가 최신 행을 바꾸고 두 이력을 보존.
- 완전히 같은 재전송은 200이며 한 행만 유지, 같은 ID의 변경 내용은 409.
- 오래된 다른 메시지는 409이며 최신 값과 이력 개수를 바꾸지 않음.
- 잘못된 로봇·배터리·bool·NaN 좌표·frame·임무·연결·시각은 400이며 부분 행 없음.
- 비로그인 조회 차단, 로그인 조회 JSON과 첫 HTML에 배터리·임무·좌표 표시.
- 기준 시각 15초 뒤 오프라인 계산.
- 두 동시 재전송 결과가 201·200 한 번씩이고 이력은 한 행.

임시 5003번 서버와 별도 DB·계정에서 실제 브라우저 로그인 후 AMR1 상태 한 건을 HTTP로 보냈다. 2초 이내 카드가 배터리 82%, 순찰 중, `map (12.40, 8.70)`, 온라인으로 바뀌고 전체 요약이 `로봇 1/2 온라인`으로 바뀌는 것을 확인했다. 새 입력 없이 15초가 지난 뒤 카드가 오프라인, 전체 요약이 `연결된 로봇 없음`으로 바뀌는 것도 확인했다. 화면 너비 662px에서 문서 너비 647px로 페이지 전체 가로 넘침이 없었고 배터리 막대가 표시됐다. 임시 계정·토큰·DB·preview_server.py는 실제 프로젝트 반영 대상에서 제외한다.

실제 프로젝트에는 코드·테스트·문서 파일만 반영하고 기존 instance DB·세션 키를 보존했다. 반영된 폴더에서 `-B` 옵션으로 전체 테스트를 다시 실행해 동일하게 **25개 통과**를 확인했다. 실제 ROS 노드·실제 AMR·장시간 상태 주기·여러 PC 부하는 아직 검증하지 않았다.

### 다음 단계

6단계는 확정된 지도 이미지·좌표계를 기준으로 저장된 `x`, `y`, `frame_id`를 지도 위 로봇 위치로 변환해 표시하는 작업이다. ROS 상태 토픽이 먼저 확정되면 adapter에서 현재 임시 입력 필드를 내부 형식으로 변환한다.

## 11. 6단계 — Nav2 점유 지도·로봇 위치 표시 (2026-09-06)

### 목적과 구현 전 상태

기존 지도 영역은 실제 좌표와 관계없는 배치 예시였다. Nav2 토픽명과 ROS 메시지 연결이 확정되지 않은 상태에서도 웹·DB·좌표 변환을 검증할 수 있도록 OccupancyGrid 핵심 필드와 같은 내부 입력을 정의했다. 시스템 모니터는 지도를 새로 판단하지 않고 Navigation 모듈의 지도와 위치 결과를 표시한다.

### 실제 작업 순서

1. 기존 `robot_latest_status`·`robot_status_history`의 `x`, `y`, `frame_id`와 지도 placeholder를 확인했다.
2. `/tmp` 작업 사본에서 지도 저장 경로와 `maps`, `map_latest` 테이블을 추가했다. 실제 instance DB·세션 키는 작업 사본에 복사하지 않았다.
3. 지도 입력의 크기·해상도·원점·점유값·좌표계·시각을 검증하는 서비스를 만들었다.
4. Python 표준 라이브러리만으로 OccupancyGrid를 PNG로 변환하고 완성 파일만 보이도록 원자적으로 저장했다.
5. 지도 이력과 현재 지도 포인터를 한 트랜잭션으로 저장하고 중복·충돌·오래된 지도를 판정했다.
6. 로그인 전용 지도 JSON·PNG 조회 API와 2초 간격 화면 갱신을 연결했다.
7. 지도 원점·해상도·원점 회전을 적용해 로봇 map 좌표를 이미지 격자 좌표로 바꾸고 최근 120개 상태로 경로를 그렸다.
8. 임시 지도 전송 도구를 추가하고 단위·요청 테스트와 실제 브라우저 표시를 확인했다.

### 변경 파일과 역할

| 파일·함수 | 역할 |
| --- | --- |
| `app/__init__.py:create_app` | 지도 저장 경로·좌표계·격자 제한 설정, maps blueprint 등록 |
| `app/database.py:init_db` | DB·증거 폴더와 함께 `instance/maps` 준비 |
| `app/schema.sql` | `maps`, `map_latest` 테이블과 지도 시각 인덱스 |
| `models/map.py:store_map` | 지도 중복·시각 순서 판정, 이력·현재 지도 포인터 원자적 저장 |
| `models/map.py:recent_positions` | 로봇별 최근 map 좌표 120개 조회 |
| `services/map_service.py:validate_map` | OccupancyGrid 내부 입력의 필드·범위·시각 검증 |
| `services/map_service.py:occupancy_to_png` | 아래쪽 원점 격자를 위쪽 원점 PNG 행으로 변환 |
| `services/map_service.py:dashboard_map` | 원점·해상도·회전을 반영한 로봇 마커·경로 좌표 생성 |
| `routes/maps.py` | 장치 지도 POST, 로그인 지도 JSON·PNG GET |
| `templates/index.html` | 점유 지도·경로·마커를 겹치는 SVG 지도 영역 |
| `static/js/map.js` | 2초 지도 조회, PNG·경로·마커·오류 문구 갱신 |
| `static/css/dashboard.css` | 지도 레이어·로봇·경로·수신 상태 스타일 |
| `tools/send_demo_map.py` | 실제 Nav2 연결 전 수동 시연용 48×64 지도 전송 |
| `tests/test_map.py` | 지도 인증·검증·저장·변환·조회·오류 조건 테스트 |

### 실행 흐름과 플로우차트 대응

```text
Nav2 adapter 또는 임시 송신기 → POST /api/maps/current
→ 장치 토큰 일치? → 아니오: 401 또는 미설정 503
→ frame_id·크기·해상도·origin·data·시각 유효? → 아니오: 400
→ 점유 격자의 Y축을 뒤집어 PNG 생성
→ PNG 임시 파일 완성 후 version 파일명으로 교체
→ BEGIN IMMEDIATE
→ 같은 message_id인가?
   → 같은 내용: duplicate 200
   → 다른 내용: 409, 새 파일 정리
→ 현재 지도보다 새 데이터인가? → 아니오: 409, 새 파일 정리
→ maps 이력 INSERT + map_latest 갱신 → COMMIT, 201
→ 로그인 브라우저 GET /api/maps/current
→ 지도 원점·해상도·yaw로 로봇 좌표 변환
→ frame 불일치·범위 이탈 판단
→ PNG + 최근 경로 + AMR1/AMR2 마커 SVG 표시
```

### 좌표 변환

지도 원점에서 로봇 좌표를 뺀 뒤 원점 yaw의 역회전을 적용하고 resolution으로 나눈다. OccupancyGrid와 PNG의 Y축 방향이 반대이므로 마지막에 지도 높이에서 뺀다.

```text
dx = robot_x - origin_x
dy = robot_y - origin_y
grid_x = (cos(yaw)·dx + sin(yaw)·dy) / resolution
grid_y = (-sin(yaw)·dx + cos(yaw)·dy) / resolution
screen_y = height - grid_y
```

로봇과 지도의 `frame_id`가 다르면 변환 근거가 없으므로 마커를 표시하지 않고 좌표계 불일치 문구를 보여준다. 변환 좌표가 지도 크기를 벗어나도 마커를 숨기고 범위 이탈을 표시한다.

### 설계 이유와 현재 범위

- Nav2의 `/map`은 일반적인 사진이 아니라 `nav_msgs/OccupancyGrid`이므로 점유값과 메타데이터를 받는 내부 형식을 사용했다.
- 점유 격자 원본은 DB에 넣지 않는다. 웹용 PNG는 `instance/maps`에 두고 DB에는 경로와 좌표 기준만 저장한다.
- 브라우저가 큰 격자 JSON을 반복해서 받지 않도록 PNG는 별도 보호 경로에서 제공한다. 지도 JSON에는 메타데이터·위치·경로만 포함한다.
- 이미지 URL에 content hash를 붙여 새 지도가 오면 브라우저 캐시가 이전 파일을 사용하지 않게 한다.
- 지도 입력은 기존 로봇 장치 토큰을 사용하고, 브라우저 조회는 로그인 세션을 사용한다. 장치 토큰은 HTML·JavaScript에 포함하지 않는다.
- 장치 토큰은 HTTP 헤더에 들어가므로 영문·숫자·기호로 구성하며, 시연 도구는 한글 토큰을 실행 전에 거부하고 올바른 예시를 안내한다.
- 실제 지도 없이 자동 샘플을 저장하지 않는다. `tools/send_demo_map.py`는 사용자가 직접 실행하는 시연 도구이며 실제 주차장 지도가 아니라고 문서에 구분했다.
- 동적 장애물은 `/map`만으로 판단할 수 없다. 실제 costmap 토픽 연결 전에는 표시하지 않는다.
- 관측점 P1~P7·도크·안전구역은 실제 좌표가 없으므로 임의로 생성하지 않았다.
- 시스템 모니터는 순찰 시작·복귀 같은 운영 명령을 요청하지 않는다. 지도·로봇 상태와 이후 이벤트를 관제·기록한다.

### 검증 결과

실제 `/home/hun/finalproject/sysmon` 반영 후 임시 테스트 DB에서 전체 테스트 **33개 통과**를 확인했다. 기존 인증 11개·DB 5개·로봇 상태 9개와 지도 8개다. 지도 테스트는 다음 실패를 막는다.

- 지도 장치 토큰 누락·불일치와 서버 토큰 미설정.
- frame, width/height, 최대 격자, resolution, origin, data 길이·점유값, 시간대 오류.
- PNG 서명·크기, 메타데이터 DB 저장, 격자 원본 비저장.
- 동일 메시지 재전송, 같은 ID의 다른 내용, 오래된 지도와 불필요한 파일 정리.
- 비로그인 지도 JSON·PNG 차단.
- 원점·해상도·yaw와 PNG Y축을 반영한 현재 위치·최근 경로.
- 좌표계 불일치와 지도 범위 이탈.

임시 5004번 서버에서 수동 시연 지도를 전송하고 AMR1 위치 두 건과 AMR2 한 건을 보냈다. 실제 브라우저에서 지도 PNG, 로봇 마커 2개, AMR1 경로 1개, 상태 카드가 함께 표시되는 것을 확인했다. 최초 브라우저 검증 지도는 `viewBox 0 0 64 48`이었고 마커 2개, 경로 1개, 문서 너비 1265px/뷰포트 1280px였으며 브라우저 오류 로그는 없었다. 최종 시연 도구는 세로 지도 패널에 맞춘 48×64 격자를 생성한다. 임시 서버·계정·토큰·DB는 실제 프로젝트 반영 대상이 아니다.

### 다음 단계

8단계는 저장된 이벤트의 시각·감지 로봇·좌표·위험도·상태·보호된 증거 이미지를 대시보드 로그와 상세 화면에 표시한다. 실제 Nav2 단계에서는 토픽명·메시지 타입이 정해진 뒤 `ros_adapter.py`가 현재 `map_service.receive_map`을 호출한다. 동적 장애물은 costmap 토픽 규약이 확정된 뒤 지도 위 별도 레이어로 추가한다.

## 12. 7단계 — 화재 이벤트·증거 이미지 수신 (2026-09-06)

### 목적과 입력 규약

인식 모듈이 보낸 화재 메타데이터와 해당 로봇이 촬영한 증거 이미지 한 장을 같은 이벤트로 보존한다. ROS 이벤트 토픽 형식이 확정되기 전에는 `POST /api/events`의 multipart 입력을 사용한다. `metadata`는 JSON 객체이고 `image`는 PNG 또는 JPEG 파일이다.

필수 필드는 `event_id`, `message_id`, `robot_id`, `event_type`, `occurred_at`, `captured_at`, `x`, `y`, `frame_id`, `risk_level`이다. 감지 로봇은 AMR1·AMR2 중 메시지 값으로 결정하며 고정하지 않는다. 7단계의 이벤트 종류는 `FIRE`, 위험도는 `HIGH·MEDIUM·LOW`다. 저장 성공 상태는 `NEW`이며 수신 응답은 다음 행동 명령이 아니다.

### 실제 작업 순서

1. 기존 `events`, `event_evidence`, `robots`의 외래 키·유일성 제약을 확인했다.
2. 상태·지도·이벤트가 같은 장치 토큰 검사를 쓰도록 `security.device_token_is_authorized`로 공통화했다.
3. 이벤트 ID·메시지 ID·로봇·화재 종류·좌표·좌표계·위험도·두 시각을 검증했다.
4. 선언된 확장자 대신 실제 바이트로 PNG/JPEG를 판별하고 최대 5MB로 제한했다.
5. 이미지 해시가 포함된 파일명을 만들고 임시 파일 완성 후 `instance/evidence`로 원자 교체했다.
6. 이벤트 행과 증거 이미지 경로를 한 DB 트랜잭션으로 저장했다.
7. 같은 ID·내용의 재전송과 ID가 같고 내용이 다른 충돌을 구분했다.
8. 로그인한 사용자만 증거 이미지를 조회하게 하고 경로 이탈을 차단했다.
9. 실제 API를 사용하는 `tools/send_demo_event.py`와 이벤트 테스트 7개를 추가했다.

### 변경 파일과 역할

| 파일·함수 | 역할 |
| --- | --- |
| `app/__init__.py:create_app` | 이미지 최대 크기 설정, 이벤트 CSRF 예외와 Blueprint 등록 |
| `app/security.py:device_token_is_authorized` | 상태·지도·이벤트의 공통 ASCII 장치 토큰 비교 |
| `routes/events.py:receive_event` | multipart 규약·인증·HTTP 응답과 오류 코드 |
| `routes/events.py:evidence_image` | 로그인 전용 증거 파일 제공과 경로 보호 |
| `services/event_service.py:validate_event` | 이벤트 ID·로봇·종류·위험도·좌표·시각 검증 |
| `services/event_service.py:validate_evidence` | PNG/JPEG 실제 바이트·빈 파일·5MB 제한 검증 |
| `services/event_service.py:receive_event` | 해시 파일명·원자적 파일 저장·DB 실패 시 새 파일 정리 |
| `models/event.py:store_event` | 이벤트·증거 경로 트랜잭션과 재전송·충돌 판정 |
| `tools/send_demo_event.py` | AMR·위험도를 고르는 수동 화재 이벤트 시연 |
| `tests/test_event.py` | 인증·검증·저장·재전송·파일 보호의 요청 테스트 |

### 실행 흐름과 플로우차트 대응

```text
인식 adapter 또는 임시 송신기 → POST /api/events
→ 장치 토큰 일치? → 아니오: 401 / 미설정: 503
→ multipart이고 metadata JSON + image 한 장인가? → 아니오: 400 또는 415
→ ID·AMR·FIRE·좌표·위험도·시각 유효? → 아니오: 400
→ PNG/JPEG이고 5MB 이하인가? → 아니오: 400
→ 이미지 해시 파일명 생성 → 임시 파일 완성 → evidence 폴더로 교체
→ BEGIN IMMEDIATE
→ 같은 event_id 또는 message_id가 있는가?
   → 모든 내용·이미지가 같음: duplicate 200
   → 내용 또는 이미지가 다름: 409, 이번 요청의 새 파일 삭제
→ robots에 감지 AMR이 없으면 기본 정보 INSERT
→ events INSERT(status=NEW) + event_evidence INSERT → COMMIT, 201
→ 로그인 사용자 GET /api/events/{event_id}/evidence → 보호된 이미지 제공
```

### 설계 이유와 현재 범위

- 이미지 바이너리를 SQLite에 넣지 않아 DB 크기와 조회 부하를 분리했다.
- 이벤트와 증거 경로는 한 트랜잭션으로 저장해 둘 중 하나만 DB에 남지 않게 했다.
- DB 저장이 실패하면 이번 요청이 새로 만든 파일만 지워 기존 증거를 보존한다.
- 파일명은 안전하게 검증된 이벤트 ID와 이미지 SHA-256 일부로 생성한다.
- `event_id`와 `message_id` 어느 쪽이 재사용되어도 기존 내용과 비교해 충돌을 막는다.
- AMR 상태보다 이벤트가 먼저 도착할 수 있어 검증된 AMR 기본 행을 먼저 준비한다.
- 저장 성공 응답은 수신 확인이다. 순찰·복귀·대피 같은 명령 발행은 시스템 모니터 범위가 아니다.
- 7단계 완료 당시 대시보드 이벤트 표는 DB를 조회하지 않았고, 8단계에서 로그·상세·상태 변경을 연결했다.

### 검증 결과

실제 `/home/hun/finalproject/sysmon` 반영 후 임시 테스트 DB에서 전체 테스트 **40개 통과**를 확인했다. 기존 33개와 새 이벤트 요청 테스트 7개다. 새 테스트는 장치 토큰·multipart, 메타데이터·시간대·미래 시각, 이미지 형식·빈 파일·크기, 이벤트와 이미지 경로 저장, 정확한 재전송·ID 충돌, 비로그인 차단과 증거 폴더 밖 경로 차단을 확인한다.

별도 임시 5006번 Flask 서버에서 `tools/send_demo_event.py`를 실행했다. HTTP 201 `accepted`를 받고 `events`에 AMR1·FIRE·HIGH·NEW 행, `event_evidence`에 같은 event_id의 PNG 경로, `instance/evidence`에 실제 PNG 한 장이 저장된 것을 확인했다. 이 데이터와 서버는 임시 작업 사본에만 존재하며 실제 프로젝트 DB에는 복사하지 않는다. 실제 ROS 이벤트·카메라 토픽과 실제 촬영 이미지는 아직 연결하지 않았다.

### 다음 단계

8단계에서 저장된 이벤트를 대시보드 표에 표시하고 행 선택 시 좌표·위험도·증거 이미지 한 장을 확인하게 만들었다. 처리 상태 변경과 메모도 관리자·관제자 권한으로 연결했다.

## 13. 8단계 — 이벤트 로그·상세·처리 기록 (2026-09-06)

### 목적과 구현 범위

7단계에서 저장된 화재 이벤트를 관제자가 대시보드에서 바로 확인하도록 최근 목록·증거 이미지 썸네일·상세 화면을 연결했다. 관리자와 관제자는 `신규 → 확인중 → 작업요청 → 조치완료` 순서로 상태와 메모를 기록하고, 조회자는 읽기만 가능하다. `작업요청`은 외부 조치 요청이 있었다는 관제 기록이며 로봇 명령을 생성하지 않는다.

### 실제 작업 순서

1. 실제 프로젝트 DB에 7단계 시연 이벤트 2건과 증거 파일 2개가 저장됐지만 빈 `<tbody>` 때문에 화면에 나오지 않는 것을 확인했다.
2. 최근 이벤트 50건과 이벤트별 처리 이력을 조회하는 model 함수를 추가했다.
3. DB UTC 시각, 이벤트·위험도·상태 코드를 한국어 표시값으로 바꾸는 service 함수를 추가했다.
4. 로그인 전용 목록·상세 API와 관리자·관제자 전용 상태 변경 API를 추가했다.
5. 상태 변경은 현재 상태 확인, 이벤트 갱신, `event_changes` 감사 이력 INSERT를 한 트랜잭션으로 처리했다.
6. 대시보드 최초 HTML에도 최근 이벤트를 렌더링하고 JavaScript가 3초마다 변경을 조회하도록 연결했다.
7. 표에 화재·AMR·좌표·위험도·상태·이미지 썸네일을 표시했다.
8. 상세 대화상자에 원본 이미지·발생/촬영 시각·이벤트 ID·좌표·처리 이력과 다음 상태 버튼을 배치했다.
9. 권한·CSRF·순차 전이·메모 제한·없는 이벤트 테스트와 실제 브라우저 시연을 수행했다.

### 변경 파일과 역할

| 파일·함수 | 역할 |
| --- | --- |
| `models/event.py:list_recent` | 최근 50건의 이벤트·로봇 이름·증거 경로 조회 |
| `models/event.py:list_changes` | 사용자와 상태·메모 변경 이력 조회 |
| `models/event.py:change_status` | 현재 상태 갱신과 감사 이력의 원자적 저장 |
| `services/event_service.py:recent_events` | DB 값을 한국 시각·한글 라벨·좌표 문자열로 변환 |
| `services/event_service.py:event_detail` | 이벤트 한 건과 처리 이력 상세 구성 |
| `services/event_service.py:change_event_status` | 허용 전이와 메모 500자 제한 검사 |
| `routes/events.py:list_events` | 로그인 전용 최근 이벤트 JSON |
| `routes/events.py:event_detail` | 로그인 전용 이벤트·처리 이력 JSON |
| `routes/events.py:change_status` | 관리자·관제자 전용 상태 변경 JSON API |
| `routes/dashboard.py:index` | 최초 HTML에 최근 이벤트 목록 전달 |
| `templates/index.html` | 이벤트 표·썸네일·상세 dialog·상태 기록 폼 |
| `static/js/events.js` | 3초 목록 갱신·상세 조회·CSRF 상태 변경 |
| `static/css/dashboard.css` | 위험도·상태·썸네일·반응형 상세 화면 스타일 |
| `tests/test_event.py` | 목록·상세·권한·상태 전이·감사 이력 요청 테스트 |

### 실행 흐름과 권한

```text
로그인 GET /
→ dashboard.index → recent_events(50)
→ events + robots + event_evidence JOIN
→ 발생 시각 역순 표 렌더링
→ 브라우저가 3초마다 GET /api/events
→ 새 이벤트 또는 상태가 달라지면 표 갱신
→ 증거 썸네일 선택 → GET /api/events/{event_id}
→ 상세 이미지·좌표·위험도·처리 이력 표시

관리자·관제자가 다음 상태 선택
→ POST /api/events/{event_id}/status + CSRF + memo
→ 현재 상태의 바로 다음 단계인가? → 아니오: 409
→ events.status UPDATE + event_changes INSERT → COMMIT
→ 상세·표 다시 조회

조회자 상태 변경 → 403
운영 명령 생성 → 수행하지 않음
```

### 처리 상태 규칙

| 현재 | 허용하는 다음 상태 | 화면 의미 |
| --- | --- | --- |
| `NEW` | `REVIEWING` | 관제자가 이벤트 확인을 시작함 |
| `REVIEWING` | `WORK_REQUESTED` | 외부 담당자에게 조치를 요청했다고 기록함 |
| `WORK_REQUESTED` | `RESOLVED` | 조치 완료를 확인함 |
| `RESOLVED` | 없음 | 완료된 최종 상태 |

단계를 건너뛰거나 되돌리는 요청은 409로 거부한다. 메모는 선택 입력이며 500자 이하다. 상태 변경 사용자·전후 상태·메모·시각은 `event_changes`에 남는다. `commands` 테이블에는 어떤 행도 생성하지 않는다.

### 검증 결과

실제 `/home/hun/finalproject/sysmon` 반영 후 임시 테스트 DB에서 전체 테스트 **43개 통과**를 확인했다. 기존 40개와 새 이벤트 UI·처리 요청 테스트 3개다. 새 테스트는 목록·상세·보호 이미지 URL·최초 HTML, 조회자의 변경 차단, 관제자의 세 단계 순차 전이와 메모 이력, 명령 미생성, CSRF·잘못된 요청·500자 초과·없는 이벤트 처리를 확인한다.

임시 5007번 서버에서 관제자 계정으로 로그인해 AMR1·AMR2 이벤트 2건, 위험도 상·중, 증거 썸네일과 상세 이미지를 확인했다. AMR2 이벤트를 `신규 → 확인중`으로 변경하고 메모와 사용자·변경 시각이 상세 이력에 표시되는 것도 확인했다. 브라우저 오류 로그는 없었으며 문서 너비 1265px, 뷰포트 1280px로 전체 가로 넘침이 없었다. 임시 계정·이벤트·DB는 실제 프로젝트에 복사하지 않는다.

### 다음 단계

9단계에서 AMR1·AMR2와 고정 웹캠 두 개의 영상 영역을 임시 최신 프레임 입력과 연결한다. 실제 ROS 영상 토픽과 여러 PC 부하 검증은 각각 11·12단계에서 수행한다.

## 14. 9단계 — 네 카메라 최신 영상 (2026-09-06)

### 목적과 범위

AMR1·AMR2와 고정 웹캠 1·2의 영상 자리를 실제 데이터 입력과 연결했다. ROS2 토픽명이 미정이므로 이번 단계의 입력 경계는 HTTP로 만들고, 영상 검증·최신 프레임 교체·화면 상태 계산은 `camera_service`로 분리했다. 영상 전체를 녹화하지 않으며 이벤트 증거 파일과 실시간 표시 프레임의 수명을 구분한다.

### 입력·표시 흐름

```text
임시 영상 송신기 또는 향후 ros_adapter
  → POST /api/cameras/<camera_id>/frame
  → 장치 토큰·카메라 ID·frame_id·촬영 시각·PNG/JPEG·2MB 검사
  → 카메라별 파일 잠금
  → 현재 frame_id 중복/충돌과 촬영 시각 순서 판정
  → instance/live_frames/<camera_id>.frame 원자 교체
  → <camera_id>.json 메타데이터 원자 교체

로그인 브라우저
  → 1초마다 GET /api/cameras
  → 내용 해시가 바뀐 카메라만 GET /api/cameras/<camera_id>/frame
  → 이미지와 LIVE/연결 끊김/수신 대기 표시
```

### 변경 파일과 코드 역할

| 파일 | 역할 |
| --- | --- |
| `app/routes/cameras.py` | 장치 POST, 로그인 상태 목록 GET, 보호된 최신 이미지 GET |
| `app/services/camera_service.py` | 입력 검증, 카메라별 잠금·최신 파일 교체, 중복·순서와 단절 판정 |
| `app/__init__.py` | 영상 경로·크기·단절 설정과 Blueprint·CSRF 예외 endpoint 등록 |
| `app/database.py` | 시작 시 `instance/live_frames` 폴더 생성 |
| `app/routes/dashboard.py` | 첫 HTML에 네 카메라의 현재 상태 전달 |
| `app/templates/index.html` | 최신 이미지, 상태 배지, 수신 시각, 단절 오버레이 구성 |
| `app/static/js/cameras.js` | 1초 상태 갱신과 변경된 이미지 URL만 교체 |
| `app/static/css/dashboard.css` | 영상 비율·LIVE/단절 배지·최근 프레임 안내 스타일 |
| `tools/send_demo_video.py` | 네 소스의 움직이는 가상 PNG를 기본 2 FPS로 반복 전송 |
| `tests/test_camera.py` | 영상 API·파일·화면 상태 요청 테스트 6개 |

### 설계 이유

- 브라우저에 장치 토큰을 넣지 않는다. 송신 POST는 `X-Robot-Token`, 조회 GET은 로그인 세션을 사용한다.
- 카메라별 `.frame` 한 장만 덮어써서 일반 영상을 이력으로 남기지 않는다. 이벤트 증거 이미지는 별도 `instance/evidence`에서 계속 보존한다.
- 임시 API는 `X-Frame-Id`와 시간대가 있는 `X-Captured-At`을 받아 정상 재전송과 충돌·역순 도착을 구분한다.
- 파일 잠금과 임시 파일 후 `os.replace`를 사용해 동시 입력이나 브라우저 조회 중 불완전한 프레임이 보일 가능성을 줄였다.
- 브라우저는 목록을 1초마다 조회하지만 내용 해시가 바뀐 프레임만 다시 받는다. 수신이 5초 넘게 끊겨도 마지막 장면은 사고 확인에 도움이 되므로 화면에 유지하고 단절 표시를 겹친다.
- 현재 방식은 저속 임시 프레임 시연용이다. 실제 FPS·해상도·압축 방식은 ROS 토픽과 네트워크 부하를 측정한 뒤 결정한다.

### 검증 결과와 남은 일

실제 `/home/hun/finalproject/sysmon` 반영 후 임시 테스트 DB에서 전체 테스트 **49개 통과**를 확인했다. 기존 43개와 영상 테스트 6개이며 인증·입력 형식·파일 한 장 덮어쓰기·중복·충돌·오래된 프레임·로그인 보호·네 카메라 목록·5초 단절을 검사한다.

임시 5008번 Flask 서버와 실제 브라우저에서 `send_demo_video.py`로 네 카메라를 2 FPS로 전송했다. 네 영상 카드의 서로 다른 시연 이미지와 `LIVE`, `방금 수신`을 확인했다. 전송 종료 후 5초가 지나면 네 카드 모두 최근 프레임을 유지하면서 `연결 끊김`과 마지막 수신 시각을 표시했다. 시연 데이터·계정은 임시 경로만 사용했다.

11단계에서 실제 `sensor_msgs/Image` 또는 `sensor_msgs/CompressedImage` 타입, 토픽명, QoS, 인코딩을 확정해 adapter에 연결한다. 12단계에서 여러 브라우저가 동시에 네 영상을 볼 때의 네트워크·CPU 사용량과 재연결을 측정한다.

## 15. 10단계 — 통합 이력 검색 (2026-09-06)

### 목적과 구현 범위

DB에 저장된 과거 기록을 관제자가 한 화면에서 조건별로 찾을 수 있게 했다. 별도 통합 테이블에 데이터를 중복 저장하지 않고 `events`, `event_changes`, `robot_status_history`, `patrol_runs`, `handovers`를 공통 결과 열로 조회한다. 시스템 모니터가 생성하지 않는 `commands`와 보존하지 않는 일반 카메라 영상은 결과에서 제외한다.

순찰과 교대는 현재 수신 API가 없으므로 실제 연동 데이터는 아직 들어오지 않는다. 다만 기존 테이블에 행이 생기면 검색 서비스 변경 없이 바로 결과에 포함된다.

### 검색 흐름

```text
로그인 사용자 → GET /history 또는 GET /api/history
→ 기록 종류·로봇·위험도·상태·날짜·검색어 검증
→ 한국 날짜 00:00 범위를 UTC 반개구간으로 변환
→ 선택한 테이블별 WHERE 조건과 매개변수 구성
→ 공통 열 SELECT를 UNION ALL
→ 전체 기록을 recorded_at 역순 정렬
→ COUNT + LIMIT 50 + OFFSET
→ 서비스에서 한국 시각·한글 종류/위험도/상태 라벨 변환
→ HTML 표 또는 JSON 응답
```

### 변경 파일과 역할

| 파일·함수 | 역할 |
| --- | --- |
| `models/history.py:search` | 선택한 기록 SELECT를 합쳐 전체 수와 한 페이지를 조회 |
| `models/history.py:_common_conditions` | 날짜·로봇·검색어 조건을 SQL 매개변수로 구성 |
| `services/history_service.py:validate_filters` | 허용 코드·날짜 순서·검색어 100자·페이지 검증과 UTC 변환 |
| `services/history_service.py:search_history` | DB 행을 한글 표시값으로 변환하고 페이지 수 계산 |
| `routes/history.py:index` | 로그인 전용 `/history` 검색 화면과 이전·다음 URL 구성 |
| `routes/history.py:search_api` | 동일 조건의 로그인 전용 `/api/history` JSON |
| `templates/history.html` | 7개 검색 조건, 8열 결과 표, 빈 결과와 페이지 이동 |
| `static/css/history.css` | 넓은 결과 표와 데스크톱·모바일 검색 폼 배치 |
| `templates/index.html` | 대시보드 메뉴에 통합 이력 검색 링크 추가 |
| `schema.sql` | 전역 처리 이력 시각과 교대 로봇별 검색 인덱스 추가 |
| `tests/test_history.py` | 통합·필터·권한·페이지·HTML 요청 테스트 6개 |

### 검색 규칙

- 날짜 입력은 사용자가 보는 한국 날짜를 기준으로 시작일 00:00 이상, 종료일 다음 날 00:00 미만으로 변환한다. 이 방식으로 종료일 하루 전체가 포함된다.
- `type`, `robot`, `risk`, `status`는 고정 허용 목록만 사용하고 SQL 문자열에 사용자 값을 삽입하지 않는다.
- 검색어의 `%`, `_`, 역슬래시는 LIKE 와일드카드가 아니라 문자로 처리한다.
- 위험도나 이벤트 처리 상태를 선택하면 전체 검색에서도 이벤트와 이벤트 처리 기록만 대상으로 한다. 로봇 상태처럼 다른 종류를 명시하면서 이벤트 필터를 선택하면 결과는 0건이다.
- AMR2 검색에는 AMR2가 출발 또는 도착 로봇인 교대 이력이 모두 포함된다.
- 이벤트 처리 상태 검색은 해당 변경 행의 `new_status`를 사용하고, 사건 행은 현재 `events.status`를 사용한다.
- 순찰 결과에는 연결된 P1~P7 관측점 목록을 표시하며 관측점 이름으로도 검색한다.
- 결과는 한 페이지당 50건이며 데이터가 줄어 페이지가 범위를 벗어나면 마지막 페이지로 보정한다.

### 검증 결과와 남은 일

실제 `/home/hun/finalproject/sysmon` 반영 후 임시 테스트 DB에서 전체 테스트 **55개 통과**를 확인했다. 기존 49개와 통합 이력 테스트 6개다. 새 테스트는 로그인 보호, 다섯 기록 종류의 시간순 UNION, `commands` 제외, 증거 이미지 URL, 로봇·위험도·처리 상태·메모·관측점·한국 날짜 검색, 잘못된 조건, 50건 페이지와 대시보드 메뉴를 확인한다.

임시 5009번 서버와 실제 브라우저에서 전체 다섯 기록의 한글 시각·종류·상태·담당자·증거 링크를 확인했다. 화면에서 기록 종류를 화재 이벤트, 위험도를 상으로 선택해 제출했고 결과가 5건에서 해당 사건 1건으로 줄어드는 것을 확인했다. 임시 계정과 데이터는 실제 프로젝트 DB에 복사하지 않는다.

12단계에서 ROS2 adapter가 실제 상태·지도·영상·이벤트 데이터를 기존 서비스에 전달하도록 연결한다. 순찰·교대 데이터 입력 인터페이스가 확정되면 저장 adapter 또는 API가 필요하며, 검색 쪽은 현재 테이블 구조를 그대로 사용한다. 13단계에서는 실제 데이터량과 여러 PC 접속 조건에서 검색 응답 시간과 SQLite 읽기 경합을 측정한다.

## 16. 11단계 — 누수·장애물·차량 입출차 (2026-09-06)

### 목적과 구현 범위

화재만 허용하던 이상 이벤트에 누수 `LEAK`와 장애물 `OBSTACLE`을 추가했다. 공통 이벤트 검증·증거 이미지·처리 상태·메모 흐름을 재사용한다. 고정 웹캠의 차량 입차·출차는 경고 상태 전이가 필요하지 않아 별도 `vehicle_access_logs` 테이블과 화면으로 구현했다.

### 처리 흐름

```text
화재·누수·장애물 metadata + 이미지 → 장치 토큰·필드·중복 검증
→ events + event_evidence 저장 → 이벤트 표·상세·통합 이력

웹캠 입차·출차 JSON 내역 → 장치 토큰·필드·중복 검증
→ vehicle_access_logs에 웹캠·입차/출차·시각 저장
→ 차량 입출차 표·통합 이력
```

### 변경 파일과 역할

- `services/event_service.py`: `FIRE`, `LEAK`, `OBSTACLE` 허용 및 한글 라벨 제공
- `models/vehicle_access.py`: 입출차 중복·충돌 검사와 원자적 DB 저장
- `services/vehicle_access_service.py`: 웹캠·입차/출차·시각 검증
- `routes/vehicle_access.py`: 장치 JSON 입력과 로그인 목록 API
- `templates/index.html`, `static/js/vehicle_access.js`: 최근 입출차 표와 3초 갱신
- `models/history.py`, `services/history_service.py`: 차량 입출차 UNION 검색과 표시값 변환
- `tools/send_demo_event.py`, `tools/send_demo_vehicle_access.py`: ROS2 연결 전 가상 시연

### 설계 이유와 검증

입출차는 이상 이벤트가 아니므로 위험도와 조치 상태를 넣지 않았다. 차량번호·인식률·차량 이미지는 토픽에서 받지 않으므로 DB와 화면에서도 제외했다. 일반 영상은 최신 프레임만 유지하며 이상 이벤트의 증거 이미지 한 장만 보존한다. 기존 DB는 삭제하지 않으며 초기 이미지형 입출차 테이블이 있으면 핵심 입출차 내역을 보존해 새 구조로 변환한다.

이벤트와 입출차 표에 사용자별 **표시 초기화**를 추가했다. `dashboard_clear_state`에는 삭제 시각이 아니라 최근 목록의 기준 시각을 저장한다. API는 이 시각보다 나중에 수신된 항목만 반환하며 원본 `events`, `vehicle_access_logs`와 통합 이력은 그대로 유지한다. 다른 로그인 사용자의 표시 기준도 변경하지 않는다.

2026-09-06 임시 DB에서 전체 단위·요청 테스트 **63개 통과**. 누수·장애물 라벨, 입차·출차 저장과 조회, 인증, 유효성, 중복·충돌, 사용자별 표시 초기화, 초기화 후 새 항목 재표시, 대시보드 초기 표시와 통합 이력을 검사했다. 실제 ROS2 토픽과 차량 인식 모델은 후속 단계다.

## 대시보드 한 화면 관제 배치 수정 (2026-09-07)

- 목적: 네 카메라를 동시에 충분한 크기로 보면서 최근 이벤트와 차량 입출차도 첫 화면에서 확인한다.
- 변경 파일: `app/templates/index.html`, `app/static/css/dashboard.css`, `app/static/js/dashboard.js`, `app/static/js/events.js`.
- 실행 흐름: 상단 시스템·AMR 상태 요약 → 좌측 Nav2 지도 → 중앙 네 영상 2×2 갱신 → 우측 최근 이벤트·입출차 갱신 → 이벤트 종류 선택 시 기존 상세 창 표시.
- 설계 이유: 영상을 일괄 축소하지 않고 로그를 오른쪽 열로 옮겼다. 우측 이벤트 표는 발생 시각·종류·위험도를 요약하며 로봇·좌표·처리 상태·증거 이미지는 상세 창에서 확인한다. 전체 기록은 통합 이력 검색 화면을 유지한다.
- 반응형: 넓은 화면은 3열, 1390px 이하에서는 로그를 지도·영상 아래 2열로 옮기고, 모바일에서는 단일 열로 전환한다.
- 검증 결과: 전체 단위·요청 테스트 63개 통과. 임시 DB·계정으로 1630×1010 화면을 열어 상단 상태, 지도, 네 영상, 이벤트, 차량 입출차와 통합 이력 바로가기가 한 화면에 표시되는 것을 확인했다. 1264×710에서는 반응형 규칙에 따라 최근 로그가 다음 행으로 이동하는 것을 확인했다.
- 남은 일: 실제 데이터가 채워진 상태에서 현장 모니터 해상도와 브라우저 확대율에 맞춰 열 비율을 최종 조정한다.

## 로그 증가 시 관제 화면 높이 고정 (2026-09-07)

- 목적: 최근 이벤트와 차량 입출차 행이 누적되어도 중앙의 로봇 카메라와 고정 웹캠 높이가 늘어나지 않게 한다.
- 변경 파일: `app/static/css/dashboard.css`.
- 처리 방식: 넓은 화면의 지도·영상·로그 관제 영역을 590px로 고정하고, 내부 그리드 항목에 `min-height: 0`을 적용한다. 이벤트와 차량 입출차 표는 패널 내부에서 각각 세로 스크롤하며 표 머리글은 상단에 고정한다.
- 반응형: 1390px 이하에서는 카메라 영역을 560px로 유지하고 최근 로그 두 패널을 300px 높이의 다음 행에 배치한다. 모바일에서는 다시 내용 기반 높이를 사용한다.
- 검증 결과: 임시 DB에 이벤트 30건과 차량 입출차 30건을 넣어 1630×1010 브라우저에서 확인했다. 관제 영역과 카메라 영역은 590px, 카메라 카드 한 개는 289px로 유지됐으며 이벤트 표는 278px, 차량 입출차 표는 158px 내부 스크롤 영역을 사용했다. 모든 주기 조회 API가 HTTP 200으로 응답했다.
- 테스트 범위: 이번 변경은 CSS 배치만 수정했다. 직전 구조 변경 시 실행한 서버 단위·요청 테스트 63개 통과 결과와 별도로 실제 브라우저의 다량 로그 배치를 검증했다.

## 17. 12단계 — ROS adapter 기본 작업 틀 (2026-09-07)

### 목적과 구현 범위

실제 AMR·비전 퍼블리셔를 받기 전에 ROS 연결부를 교체 가능한 경계로 만든다. 이번 단계는 PC 3의 sysmon만 변경하며 공용 메시지 패키지, AMR·비전 코드, launch·YAML, 기존 DB schema는 수정하지 않는다.

### 처리 흐름

```text
ROS topic → app/ros_adapter.py 등록표·QoS
→ ROS 메시지별 순수 변환 함수
→ 기존 robot_service / map_service / camera_service
→ 기존 SQLite·최신 파일·대시보드
```

웹 서버와 ROS spin은 서로의 lifecycle을 묶지 않고 `run.py`와 `ros_adapter.py` 두 프로세스로 분리했다. 실제 토픽명이 바뀌면 등록표, 필드가 바뀌면 변환 함수에서 조정한다. 기존 HTTP 입력은 시연·회귀시험 경계로 유지한다.

### 변경 파일과 역할

- `app/ros_adapter.py`: 계약 토픽 등록표, 의존성 점검, RobotStatus·OccupancyGrid·CompressedImage 변환, rclpy 구독 callback.
- `ros_adapter.py`: `--check` 점검과 별도 ROS spin 진입점.
- `services/robot_service.py`: 확정 Mission enum의 표시 라벨 추가.
- `tests/test_ros_adapter.py`: ROS 설치나 실제 publisher 없이 등록·변환 경계를 검증.
- `README.md`, `docs/code-review-30min.md`: 실행법·완료 범위·코드 탐색 경로 갱신.

### 12단계 당시 차단과 후속 작업

- 당시 `parking_interfaces`가 설치되지 않아 실제 RobotStatus 구독을 시작하지 않았다. 14단계에서 PC 3 빌드가 완료됐다.
- Stage 12 활성 입력은 RobotStatus 2개, 정적 `/map`, 압축 영상 4개다.
- costmap·DetectionEvent·EvidenceChunk·CameraState·patrol_allowed는 등록표에 후속 항목으로만 두었으며 구독하지 않는다.
- `pose_valid=false`와 NaN battery SOC를 현재 DB에 넣으면 의미가 손실되므로 migration 전에는 명시적으로 거부한다.
- 실제 publisher 연결, QoS 상호운용, 재연결, 처리량, 장비 통합시험은 실행하지 않았다.

### 검증 결과

`tests/test_ros_adapter.py` 6개가 통과했다. 토픽 활성/후속 구분, 의존성 보고, robot1→AMR1 표시 매핑, SOC 변환, pose·enum 거부, OccupancyGrid 원점 yaw·data 변환, 영상 토픽·바이트 변환을 확인했다. 전체 회귀시험은 기존 63개와 신규 6개를 합한 **69개 통과**다.

`requirements.txt`에 PyYAML과 numpy를 선언하고 기존 가상환경에도 설치했다. 이후 `rclpy`, `nav_msgs`, `sensor_msgs` import와 RobotStatus deadline 500 ms를 포함한 QoS 객체 생성을 확인했다. `ros_adapter.py --check`는 `parking_interfaces` 하나만 누락으로 표시하며 예상대로 종료 코드 2를 반환했다. 공용 메시지 패키지 빌드·source, 실제 구독, publisher 송수신, QoS 상호운용 및 장비 통합시험은 **NOT_RUN**이다.

## 18. 13단계 — 부하·다중 접속·SQLite 경합 측정 (2026-09-07)

### 목적과 구현 범위

실제 publisher를 받기 전에 PC 3 sysmon의 route·service·SQLite·파일 저장 경로를 동시 실행해 병목과 실패 응답을 측정한다. 운영 `instance`를 사용하지 않고 실행마다 별도 임시 앱·DB·증적·지도·최신 영상 폴더를 만들며 종료 후 삭제한다. 실제 ROS·다른 PC·네트워크 성능은 범위가 아니다.

### 변경 파일과 역할

- `app/load_test.py`: 부하 설정 검증, 이력 seed, 병렬 writer·reader, write lock 주입, latency·HTTP 상태·자원·DB 무결성 집계.
- `tools/run_load_test.py`: 부하율·시간·조회자·lock·출력 경로를 지정하는 CLI.
- `tests/test_load_test.py`: 임시 저장소 격리, 모든 입력·조회 경로, 설정 거부, lock 해제 후 201 복구 검증.
- `README.md`, `docs/code-review-30min.md`: 실행법, 측정 경계, 현재 검증 결과 갱신.

### 실행 흐름

```text
임시 폴더 → create_app(임시 DB·파일 경로)
→ 이력 seed·임시 VIEWER 생성
→ 상태·지도·영상·이벤트·입출차 writer + 로그인 reader 병렬 실행
→ 선택 시 BEGIN IMMEDIATE lock 주입
→ 요청별 HTTP 상태와 p50·p95·p99 수집
→ integrity_check·foreign_key_check·파일 상태 확인
→ JSON 보고 → 임시 저장소 삭제
```

비밀번호·장치 토큰은 실행마다 임의 생성하며 출력하지 않는다. 결과는 `MEASURED`로 기록하고 TBD-MON-001·003이 결정되기 전에는 성능 PASS로 승격하지 않는다.

### 검증 결과

전체 단위·요청 테스트는 기존 69개와 신규 3개를 합한 **72개 통과**다.

기본 측정은 이력 1,000건, 조회자 4명, 조회자당 3 Hz, 상태 총 4 Hz, 지도 1 Hz, 영상 총 20 Hz, 이벤트·입출차 각 1 Hz를 3초간 실행했다. 상태 12건, 지도 3건, 영상 59건, 이벤트 3건, 입출차 3건과 조회 36건이 모두 HTTP 200·201이었고 예외는 0이었다. 대시보드 p95 54.355 ms, 통합 이력 p95 31.552 ms였다. DB integrity `ok`, 외래 키 오류 0, 잔여 `.tmp` 0을 확인하고 임시 저장소 삭제를 확인했다.

LT-13-06은 5.2초 write lock을 주입했다. 상태 저장 한 건이 SQLite 5초 timeout 뒤 HTTP 503으로 구분됐고 최대 지연은 5,016.058 ms였다. lock 해제 후 자동 상태 저장 probe는 HTTP 201, 30.136 ms였으며 DB integrity와 외래 키는 정상이었다.

기본·lock JSON 보고서는 각각 `/tmp/sysmon-stage13-baseline.json`, `/tmp/sysmon-stage13-lock.json`에 생성했다. 이는 임시 로컬 측정 자료다. 실제 여러 PC 접속, ROS publisher, 네트워크·장비 부하와 최종 합격 수치 검증은 **NOT_RUN**이다.

## 19. 14단계 — 공용 메시지 패키지 구현·PC 3 빌드 (2026-09-07)

### 범위와 책임 경계

사용자가 [CR-001](../../docs/change_requests/CR-001_09-07_11-09_parking_interfaces_v1_구현.md)을 승인한 범위에서 프로젝트 루트에 공용 `parking_interfaces` 패키지를 추가했다. `interfaces.md` 계약 v1.0의 필드·타입·상수·enum 번호는 변경하지 않았다. AMR·비전 생산자 코드, launch·YAML, 실제 장비 배포와 publisher 송수신은 변경하거나 실행하지 않았다.

### 변경 내용

- `parking_interfaces/package.xml`, `CMakeLists.txt`: `ament_cmake`와 `rosidl` 빌드 정의.
- `parking_interfaces/msg/*.msg`: MissionCommand부터 KeepoutStatus까지 계약 메시지 14개.
- `parking_interfaces/README.md`: PC 3 빌드·source·검증 절차와 가상환경 주의사항.
- `docs/interfaces.md`, CR-001, sysmon README·코드리뷰: 구현 상태와 단위별 미반영 범위 갱신.

### 검증 결과

첫 빌드는 로그인 시 자동 활성화된 `/home/hun/venvs/rokey_venv`의 Python이 rosidl 실행기를 가로채 `lark`를 찾지 못해 실패했다. 시스템 `/usr/bin/python3`에는 `python3-lark`가 이미 설치돼 있음을 확인했고, 새 의존성을 설치하지 않고 가상환경을 제외한 뒤 CMake Python 경로를 시스템 Python으로 고정해 재빌드했다.

PC 3 `/home/hun/rokey_ws`에서 `colcon build`가 **1 package finished**로 통과했다. source 후 `ros2 pkg prefix`가 설치 경로를 반환했고, `ros2 interface package parking_interfaces`에 메시지 14개가 표시됐다. Python import 14개와 RobotStatus 대표 상수 값을 확인했으며, sysmon `ros_adapter.py --check`는 `rclpy`, `parking_interfaces`, `nav_msgs`, `sensor_msgs`를 모두 찾아 **ready=true, 종료 코드 0**이었다. 실제 publisher·QoS·PC 간 송수신은 **NOT_RUN**이다.

## 20. 15단계 — 가상 ROS 토픽 로컬 DDS 종단시험 (2026-09-07)

### 목적과 책임 경계

실제 PC 1·2·4 publisher를 받기 전에 PC 3의 실제 ROS subscriber, 변환 callback, 기존 service, SQLite·파일 저장과 화면 조회 API를 한 경로로 검증한다. 운영 `ROS_DOMAIN_ID=6`은 도구에서 거부하고 별도 도메인과 localhost discovery만 사용한다. 운영 `instance`와 기본 ROS 로그 폴더도 사용하지 않는다. 상대 개발 단위 코드와 공용 메시지 계약은 변경하지 않았다.

### 변경 내용

- `app/ros_topic_test.py`: 계약 타입·QoS의 가상 publisher 7개 토픽, 임시 앱·ROS 로그·DB, 실제 DDS spin, 저장·화면·무결성 보고.
- `tools/run_ros_topic_test.py`: 시간·시험 도메인·상태·지도·영상 발행률과 JSON 출력 경로를 지정하는 CLI.
- `tests/test_ros_topic_test.py`: 운영 도메인·잘못된 설정 거부와 실제 로컬 DDS 종단 저장 검증.
- `app/ros_adapter.py`: 실제 `PoseWithCovariance.pose.position` 경로 적용, `map` frame 검사, callback 처리 결과 집계.
- `tests/test_ros_adapter.py`: 실제 계약과 같은 중첩 pose 및 잘못된 frame 거부 검증.

### 검증 결과

도메인 79에서 3초 동안 가상 publisher를 실행했다. 두 RobotStatus 토픽은 각각 13건을 발행해 총 26건이 accepted·저장됐고, `/map` 4건이 accepted·저장됐다. 압축 영상은 네 토픽에서 각 7건을 발행했으며 discovery 전 첫 묶음을 제외한 총 24건이 accepted되고 네 카메라 모두 최신 파일이 생성됐다. VOLATILE 최신 영상은 subscriber 발견 전 데이터를 재전송하지 않으므로 이 차이는 정상이다.

callback rejected·failed는 0건이었다. 최신 로봇은 AMR1·AMR2, DB integrity는 `ok`, 외래 키 오류는 0이었고 상태·지도·카메라 화면 API가 모두 HTTP 200을 반환했다. 시험 종료 후 임시 DB·파일·ROS 로그가 삭제됐다. JSON 결과는 `/tmp/sysmon-stage15-local-dds.json`에 기록했다.

전체 회귀시험은 기존 72개와 신규 2개를 합한 **74개 통과**다. 실제 PC 간 Discovery, 상대 publisher 구현, 네트워크, 실제 주기·timestamp·frame·QoS 상호운용은 **NOT_RUN**이며 이 결과를 실제 통합 PASS로 보고하지 않는다.

## 21. 16단계 — 별도 프로세스 가상 publisher 종단시험 (2026-09-07)

### 목적과 구현 범위

15단계의 한 프로세스 executor 시험을 실제 배치 경계에 가깝게 나눴다. `sysmon` adapter와 가상 publisher를 서로 다른 OS 프로세스로 실행하고 DDS discovery·토픽 매칭·자식 종료 코드·임시 저장 결과를 한 보고서로 확인한다. PC 3 로컬 격리 시험이며 상대 PC의 publisher와 네트워크는 범위가 아니다.

### 변경 파일과 실행 흐름

- `app/ros_process_test.py`: adapter 프로세스를 먼저 준비하고 publisher 프로세스를 실행한 뒤 결과 queue, 종료 코드, 저장소와 API 상태를 집계한다.
- `tools/publish_virtual_ros_topics.py`: 계약 타입·QoS의 가상 publisher만 유한 시간 실행한다.
- `tools/run_ros_process_test.py`: 시험 시간·도메인·발행률과 JSON 출력 경로를 받는다.
- `tests/test_ros_process_test.py`: 일곱 publisher의 subscriber 매칭, 두 자식의 정상 종료와 처리 실패 0을 확인한다.

```text
부모 시험 프로세스
├─ sysmon ROS adapter → 임시 SQLite·지도·영상
└─ 가상 publisher → 격리 DDS domain → adapter
→ 종료 코드·매칭 수·처리 수·API·DB 무결성 집계
```

### 검증 결과

도메인 82의 3초 시험에서 RobotStatus 2개, `/map`, 압축 영상 4개가 각각 subscriber 1개와 매칭됐다. adapter·publisher 종료 코드는 모두 0, callback rejected·failed는 0이었다. AMR1·AMR2 상태, 지도 4건, 네 카메라 최신 프레임, 상태·지도·카메라 API HTTP 200, DB integrity `ok`, 외래 키 오류 0과 임시 저장소 삭제를 확인했다. 실제 상대 publisher와 PC 간 시험은 **NOT_RUN**이다.

## 22. 17단계 — AMR별 global/local costmap 수신·분리 표시 (2026-09-07)

### 목적과 책임 경계

`interfaces.md` v1.0의 두 로봇 global/local costmap 네 토픽을 PC 3 sysmon에서 수신한다. 이 단계는 관제 모니터링용 최신 저장과 표시만 담당하며 AMR Nav2 설정·publisher·장애물 판단·주행 안전 로직은 변경하지 않는다. 정적 `/map`과 costmap의 해상도·원점이 다를 수 있어 근거 없는 합성 대신 별도 미리보기로 표시한다.

### 변경 파일과 처리 흐름

- `app/ros_adapter.py`: 네 costmap 토픽을 활성화하고 RELIABLE·VOLATILE·KEEP_LAST(1) QoS와 source별 callback을 연결했다.
- `app/schema.sql`, `app/database.py`, `app/__init__.py`: `costmap_latest` 네 source 최신 행과 `instance/costmaps` 저장 경로를 추가했다.
- `app/models/costmap.py`: source별 중복·ID 충돌·과거 시각을 검사하고 최신 한 행을 트랜잭션으로 교체한다.
- `app/services/costmap_service.py`: OccupancyGrid 공통 검증·PNG 변환을 재사용하고 DB 교체가 확정된 뒤 이전 PNG를 삭제한다.
- `app/routes/costmaps.py`: 로그인 사용자에게 네 source 상태와 보호된 PNG만 제공한다. 외부 HTTP 입력 경로는 만들지 않았다.
- `app/templates/index.html`, `app/static/css/dashboard.css`, `app/static/js/costmaps.js`: 정적 지도 위에 선택형 독립 미리보기와 2초 갱신을 추가했다.
- `app/ros_topic_test.py`, `app/ros_process_test.py`, 두 CLI: `costmap_hz > 0`일 때 네 가상 costmap과 stage 17 판정을 추가했다.
- `tests/test_costmap.py`, `tests/test_ros_adapter.py`, `tests/test_ros_process_test.py`, `tests/test_database.py`: 저장·교체·보호 조회·11개 토픽·DB 초기화를 검증한다.

```text
AMR1/AMR2 global/local OccupancyGrid 4개
→ ROS adapter source 식별·QoS
→ 공통 격자 검증·PNG 변환
→ costmap_latest source별 UPSERT + 최신 PNG 한 장
→ 로그인 API → 정적 지도와 분리된 선택 미리보기
```

가상 publisher의 타이머 첫 발행과 강제 초기 발행이 같은 밀리초에 겹치면 기존 stage 16 회귀시험에서 간헐적으로 stale가 날 수 있었다. 각 종류가 아직 한 번도 발행되지 않았을 때만 강제 초기 발행하도록 바꿔 시험 순서를 결정적으로 만들었다.

### 검증 결과와 남은 일

도메인 83의 3초 별도 프로세스 시험에서 활성 토픽 11개 모두 subscriber 1개와 매칭됐다. costmap 네 토픽을 각 15건 발행했고 총 44건이 accepted되어 `AMR1:global`, `AMR1:local`, `AMR2:global`, `AMR2:local` 최신 행이 확인됐다. adapter·publisher 종료 코드 0, callback rejected·failed 0, 상태·지도·카메라·costmap API HTTP 200, DB integrity `ok`, 외래 키 오류 0, 임시 저장소 삭제로 `process_pass=true`였다. 결과는 `/tmp/sysmon-stage17-costmap-dds.json`에 기록했다.

전체 회귀시험은 **80개 통과**로 기록한다. 실제 AMR Nav2 publisher, 운영 domain 6, Discovery Server, PC 간 네트워크, 실제 크기·주기·timestamp·frame·QoS 상호운용과 브라우저 실화면 확인은 **NOT_RUN**이다. 다음 18단계는 DetectionEvent·EvidenceChunk이며 AMR 생산자 코드는 상대 개발 단위 범위로 남긴다.

## 23. 18단계 — DetectionEvent·EvidenceChunk·IngestionAck (2026-09-07)

### 목적과 책임 경계

두 AMR이 확정한 사건 메타데이터와 chunk 증적을 PC 3 sysmon이 독립적으로 수신하고 기존 사건 화면·이력에 연결한다. AMR 로컬 bbox 정렬·감지 확정·yaw 제어, 생산자 재전송 구현과 실제 장비는 변경하지 않는다. 관제의 ACK는 저장 결과이며 다음 임무·주행 명령이 아니다.

### 변경 파일과 처리 흐름

- `app/ros_adapter.py`: DetectionEvent 2개와 EvidenceChunk 2개를 활성화하고 RELIABLE·VOLATILE·KEEP_LAST(20) QoS, 계약 enum·ID·pose 변환, 로봇별 IngestionAck publisher를 추가했다.
- `app/services/detection_service.py`: 소문자 UUID v4, event/risk enum, confidence, `map` frame, `location_valid`, media type, 5 MiB 전체 크기와 64 KiB chunk 제한을 검증한다. 모든 chunk가 모이면 전체 크기·SHA-256·실제 이미지 형식을 확인한다.
- `app/models/detection.py`: Detection 보완 메시지 영수증, evidence 조립 상태와 chunk를 저장한다. event/evidence 어느 쪽이 먼저 와도 완료 뒤 연결하며, 완료·거부 후 chunk BLOB은 NULL로 비운다.
- `app/schema.sql`, `app/database.py`: 기존 사건에 confidence·location_valid·evidence_id를 추가하고 `detection_event_messages`, `evidence_ingestions`, `evidence_chunks`를 만든다. 기존 DB는 열·인덱스만 추가하며 이력을 삭제하지 않는다.
- `app/services/event_service.py`: 계약 enum의 LIGHTING과 FACILITY_DAMAGE 표시 라벨을 추가했다.
- `app/ros_topic_test.py`, `app/ros_process_test.py`, 시험 CLI: 역순 chunk 사이에 event를 보내고 ACK 수신·저장·잔여 BLOB을 보고한다.
- `tests/test_detection_ingestion.py`, `tests/test_ros_adapter.py`, `tests/test_ros_process_test.py`, `tests/test_database.py`: 독립 도착, 보완 메시지, 중복·충돌, 무효 위치, 잘못된 hash 거부, 기존 API 표시와 DDS 왕복을 검증한다.

```text
DetectionEvent ───────────────┐
                             ├→ event_id/evidence_id 확인 → event_evidence 연결
EvidenceChunk 0..N → 누락 ACK ┘
→ 전체 크기·SHA-256·PNG/JPEG 검증 → 원자 파일 저장
→ STORED/DUPLICATE/INCOMPLETE/REJECTED IngestionAck
```

같은 event_id에 새 message_id가 오면 기존 처리 상태를 보존하면서 보완 메타데이터를 최신화하고 모든 message_id 영수증은 별도 테이블에 남긴다. `location_valid=false`이면 pose 값이 NaN이어도 좌표를 저장하지 않는다. EVENT_UNKNOWN과 RISK_UNKNOWN은 관제 사건 의미가 확정되지 않은 값이므로 REJECTED ACK 대상이며 임의의 사건·위험도로 바꾸지 않는다.

### 검증 결과와 남은 일

도메인 84의 3초 별도 프로세스 시험에서 활성 입력 15개가 모두 subscriber 1개와 매칭되고 두 IngestionAck publisher도 각각 subscriber 1개와 매칭됐다. DetectionEvent 12건과 완성 증적 12건이 저장·연결됐고, 미완료 증적과 완료 뒤 chunk BLOB은 0건이었다. callback rejected·failed 0, adapter·publisher 종료 코드 0, 상태·지도·카메라·costmap·event API HTTP 200, DB integrity `ok`, 외래 키 오류 0, 임시 저장소 삭제로 `process_pass=true`였다. JSON 결과는 `/tmp/sysmon-stage18-detection-dds.json`에 기록했다.

운영 DB를 직접 변경하지 않고 복사본으로 기존 스키마 migration을 실행해 신규 테이블·열 생성, integrity `ok`, 외래 키 오류 0을 확인했다. 전체 단위·요청·격리 DDS 회귀시험은 **88개 통과**다. 실제 AMR producer, 운영 domain 6, Discovery Server, PC 간 네트워크, 실제 5 MiB 전송 부하·재시작 중 미완료 chunk 복구와 브라우저 실화면은 **NOT_RUN**이다. CR-001의 AMR·비전 공용 패키지 반영 상태는 계속 추적한다.

## 24. 19단계 — CameraState·순찰 허용 조건 수신·표시 (2026-09-07)

### 목적과 책임 경계

PC 4 cam_master가 확정한 CCTV 차량 상태(`CameraState`)와 순찰 허용 조건(`patrol_allowed` Bool)을 PC 3 sysmon이 수신·보존·표시한다. 상태 확정 알고리즘과 threshold는 비전 담당 책임이며 관제는 관측 결과만 기록한다. `patrol_allowed`는 판단 조건이고 주행·정지 명령이 아니므로 관제는 이 값으로 명령을 만들지 않는다.

### 변경 파일과 처리 흐름

- `app/schema.sql`: `cctv_state_events`(원문 `event_id` PK, `camera_id` CHECK gate_cam/center_cam, `state` CHECK ENTERING/PARKED/EXITING/EXITED, confidence 0~1), 순찰 허용 최신 1행 `patrol_permit_latest`, 변경 시점만 남기는 `patrol_permit_history`와 조회 인덱스 2개를 추가했다.
- `app/models/cctv.py`: `event_id` 재전송·충돌 판정과 CameraState 저장, permit 최신 UPSERT와 변경분 이력 INSERT를 한 트랜잭션에서 처리한다.
- `app/services/cctv_service.py`: 계약 enum·카메라·confidence·시각을 검증하고, permit은 Bool 이외 값을 거부한다. 화면용으로 permit 최근 수신 시각과 stale 경고를 계산한다.
- `app/routes/cctv.py`: 로그인 사용자용 `GET /api/cctv/status`만 둔다. 이 경로의 수신은 ROS 전용이라 장치 HTTP 입력 경로를 만들지 않았다.
- `app/routes/dashboard.py`, `app/templates/index.html`, `app/static/js/cctv.js`: 상태 카드에 순찰 허용 조건·permit 최근 수신·최근 CameraState를 표시하고 주기 갱신한다.
- `app/models/history.py`, `app/services/history_service.py`: 통합 이력 검색에 `CCTV_STATE`, `PATROL_PERMIT` 기록 종류와 한글 라벨을 추가했다.
- `app/ros_adapter.py`: `/vision/cctv/gate_event`, `/vision/cctv/center_event`, `/vision/cctv/patrol_allowed` 구독을 활성화해 활성 토픽이 18개가 됐다.
- `app/ros_topic_test.py`, `app/ros_process_test.py`, `tools/publish_virtual_ros_topics.py`, `tools/run_ros_process_test.py`, `tools/run_ros_topic_test.py`: 가상 CCTV 발행(`--cctv-hz`)과 종단시험을 추가했다.
- `tests/test_cctv.py`: 저장·라벨, 재전송·충돌 구분, 계약 위반 거부, permit 반복 수신 시 변경분만 기록, 로그인 보호와 모니터 경계, Bool 아닌 값 거부 6개를 검증한다.

```text
CameraState(gate_cam·center_cam) → enum·카메라·confidence·시각 검증
→ event_id 재전송/충돌 판정 → cctv_state_events 저장 → 상태 카드·통합 이력

Bool patrol_allowed → 최신 1행 UPSERT (반복 수신은 시각만 갱신)
→ 값이 바뀐 시점만 patrol_permit_history 추가 → 순찰 허용 조건 표시
```

### 검증 중 발견해 고친 문제

1. **permit 수신 유실**: `patrol_allowed` 구독 큐가 계약 표기대로 KEEP_LAST(1)이어서, 영상·costmap callback을 처리하는 동안 도착한 Bool이 최신값으로 덮여 변경이 기록되지 않았다. 3초 시험에서 11건을 발행해도 adapter가 처리한 것은 1건이었다. 발행용 프로필은 계약대로 depth 1로 유지하고, 수신 프로필만 depth 10으로 분리했다(`_qos_profiles()`의 `patrol_allowed_writer`/`patrol_allowed`). 큐 깊이는 수신 측 자원 설정이라 발행 계약과 충돌하지 않는다. 같은 조건에서 permit 이력이 1건에서 7건으로 늘었다.
2. **별도 프로세스 시험이 실행 순서에 좌우됨**: `fork`는 부모가 이미 만든 rclpy·DDS 스레드를 자식에서 되살리지 못해, 같은 프로세스에서 `test_ros_topic_test`를 먼저 실행하면 adapter 자식이 준비되지 않았다. rclpy를 쓰지 않은 서버 프로세스에서 자식을 만드는 `forkserver`로 바꾸고 준비 대기를 30초로 늘렸다.
3. **수신 구간이 자식 시작 지연만큼 짧아짐**: adapter가 고정 시간만 spin하면 자식 시작이 늦은 만큼 ACK 왕복 같은 늦은 메시지를 놓쳤다. 부모가 publisher 종료 후 stop 신호를 보내고 adapter는 1초 단위로 확인하며 수신한다. 신호 확인 간격을 0.1초로 잘게 나누면 처리량이 절반으로 떨어져 1초로 두었다.
4. **시험 CLI 인자 비대칭**: `tools/run_ros_topic_test.py`에 `--costmap-hz`, `--detection-hz`, `--cctv-hz`가 없어 로컬 종단시험으로 CCTV를 켤 수 없었다. 별도 프로세스 CLI와 인자를 맞췄다.
5. 별도 프로세스 시험의 관측 창이 1.5~2초로 짧아 발견 지연에 취약해 2.5~3초로 늘렸다.

### 검증 결과와 남은 일

- ROS를 source하지 않은 `.venv`에서 전체 **97개 통과**(ROS 격리시험 5개는 rclpy 없음으로 skip).
- `/opt/ros/jazzy`와 `rokey_ws`를 source한 뒤 전체 **97개 통과를 3회 연속** 확인했다. 이전에는 실행 순서에 따라 4개 오류 또는 1~2개 실패가 났다.
- 로컬 종단시험(domain 78, 3초, cctv 4 Hz): CameraState 7건, permit 변경 이력 7건, costmap 4종, DetectionEvent 12건으로 `local_pass=true`.
- 별도 프로세스 시험(domain 85, 3초, cctv 4 Hz): 활성 입력 18개 매칭, CameraState 양쪽 카메라 수신, permit 최신값·이력 저장, `process_pass=true`를 3회 연속 확인했다.
- **NOT_RUN**: 실제 cam_master 발행, 운영 domain 6, PC 간 네트워크, 브라우저 실화면 확인, permit 1.5초 미수신 경고의 실장비 확인.
- 남은 일: 20단계 PatrolVisit·PatrolReport·Keepout·E-stop 모니터링, `CameraState`의 PARKED·EXITING을 차량 입출차 로그와 어떻게 연결할지 확정(현재 입출차는 HTTP 수신 경로만 사용).

## 25. 이벤트 범위를 화재·누수·장애물 3종으로 제한 (2026-09-07)

- 목적: 관제 화면의 이상 이벤트 범위를 합의대로 화재·누수·장애물로 되돌린다. 18단계에서 계약 enum을 그대로 수용하면서 조명 이상·시설물 파손까지 저장·표시되고 있었다.
- 변경 파일: `app/services/event_service.py`(허용 목록·오류 문구), `app/services/detection_service.py`(허용 목록·거부 문구), `app/ros_topic_test.py`(가상 publisher가 세 종류를 번갈아 발행), `tests/test_detection_ingestion.py`(기존 3곳의 종류·라벨 기대값 수정, 범위 밖 거부 시험 1개 추가).
- 표시 라벨 표에는 조명 이상·시설물 파손을 남겼다. 범위 축소 전에 저장된 이력을 화면과 통합 이력에서 읽을 때 필요하다.
- 계약 문서의 enum 정의·번호는 바꾸지 않았다. 범위 밖 값은 저장하지 않고 `IngestionAck.REJECTED`로 회신한다.
- **미해결**: `interfaces.md` 327행의 재전송 종료 조건은 STORED·DUPLICATE뿐이라 REJECTED만으로는 AMR 재전송이 멈추지 않는다. 처리 방안은 [CR-002](../../docs/change_requests/CR-002_09-07_15-40_관제_이벤트_범위_3종_제한.md)에서 AMR 담당과 확정한다.
- 검증: ROS를 source한 전체 시험 **98개 통과**. 도메인 87의 별도 프로세스 DDS 시험에서 DetectionEvent 12건 저장·거부 0건으로, 가상 publisher가 범위 안 종류만 발행하는 것을 확인했다.
- 남은 일: 범위 축소 전에 실제 DB에 저장된 조명 이상 182건·시설물 파손 182건의 처리(보존 또는 삭제)는 사용자 결정 대기 중이다.

## 26. 20단계 — 순찰 방문·보고와 Keepout·E-stop 모니터링 (2026-09-07)

### 목적과 책임 경계

두 AMR이 보고하는 관측점 방문·순찰 결과와 안전 상태(Keepout 적용, E-stop)를 수신·보존·표시한다. 관제는 관측과 기록만 하며 임무·권한·비상정지를 발행하지 않는다. E-stop 해제는 이동 명령이 아니고, Keepout 변경은 각 로봇 costmap parameter API가 수행한다.

### 변경 파일과 처리 흐름

- `app/schema.sql`, `app/database.py`: 예약 구조였던 `patrol_runs`·`patrol_visits`를 계약 구조로 바꾸고 `keepout_latest`, `estop_latest`, `estop_history`를 추가했다(25개 테이블). 예약 표에 기록이 없을 때만 자동 변환하고, 값이 있으면 변환하지 않고 시작을 중단한다.
- `app/models/patrol.py`: 방문·보고의 재전송·충돌 판정과 저장, 보고가 없는 순찰 조회.
- `app/models/safety.py`: Keepout 로봇별 최신 1행 유지, E-stop 최신 갱신과 활성·해제 변경 시점만 이력화. 늦게 도착한 과거 상태는 무시한다.
- `app/services/patrol_service.py`: UUID v4·시각·enum·waypoint 검증, `map` frame 강제, 실패·취소 보고의 원인 코드·설명 필수 검사, 완료 방문 수 상한 검사, UNREPORTED 계산.
- `app/services/safety_service.py`: Keepout·E-stop 계약 검증과 화면 상태 계산. 미수신·정상·활성을 구분하고 오래된 수신은 `stale`로 표시한다.
- `app/routes/patrol.py`: 로그인 전용 `GET /api/patrol/status`, `GET /api/safety/status`. 수신은 ROS 전용이라 장치 입력 경로를 만들지 않았다.
- `app/ros_adapter.py`: 방문·보고·Keepout 각 2개와 `/control/estop`을 더해 활성 구독이 25개가 됐다. Keepout·E-stop은 TRANSIENT_LOCAL로 받아 늦게 붙어도 마지막 상태를 얻는다. 방문·보고에는 `IngestionAck`을 회신한다.
- `app/models/history.py`, `app/services/history_service.py`, 화면: 통합 이력에 `PATROL_VISIT`·`ESTOP` 기록 종류를 추가하고 순찰 결과 라벨을 계약 enum으로 바꿨다. 상태 요약 줄에 순찰·안전 카드를 추가했다(`static/js/patrol.js`, 2초 갱신).
- `app/ros_topic_test.py`, `app/ros_process_test.py`, 시험 CLI 3개: `--patrol-hz`, `--safety-hz`로 방문·보고·Keepout·E-stop을 발행하고 저장·화면 결과를 판정한다.

```text
PatrolVisit ─→ 검증 → patrol_visits 저장 → IngestionAck(STORED/DUPLICATE/REJECTED)
PatrolReport ─→ 검증 → patrol_runs 저장 → IngestionAck
              보고가 없는 patrol_id는 저장하지 않고 화면에서 UNREPORTED로 계산

KeepoutStatus ─→ 로봇별 최신 1행 (되돌리기 실패는 경고 표시)
EStopState ───→ 최신 1행 + 활성·해제가 바뀐 시점만 이력
```

### 설계 이유

방문은 보고보다 먼저 도착할 수 있어 순찰 실행 행을 참조하지 않는다. 계약대로 결과가 오지 않은 순찰은 관제가 대필하지 않고 방문 기록만으로 UNREPORTED를 계산한다. E-stop은 2 Hz 반복 발행이라 최신 행만 갱신하고 값이 바뀐 시점만 남겨 이력이 무한히 늘지 않게 했다. permit과 같은 구조다.

### 검증 결과와 남은 일

- `.venv` 전체 시험 **107개 통과**(ROS 격리시험 6개 skip). 새 시험 8개는 저장·라벨, UNREPORTED, 재전송·충돌, 계약 위반 거부(잘못된 enum·빈 waypoint·UUID·frame·시간대, 원인 없는 실패 보고, 계획보다 많은 완료 수), Keepout 최신 1행과 되돌리기 실패 경고, E-stop 변경분만 기록, 미수신과 해제 구분, 로그인 보호와 조회 전용 경계를 확인한다.
- ROS를 source한 전체 시험 **107개 통과를 2회 연속** 확인했다.
- 도메인 86의 별도 프로세스 시험에서 활성 입력 21개 매칭, 방문·보고 저장, Keepout 두 로봇 상태, E-stop 최신값과 변경 이력, 화면 API 8종 HTTP 200으로 `process_pass=true`였다. 증적 재조립은 18단계 시험이 담당하도록 이 시험에서는 detection을 끄고 순찰·안전에 집중했다.
- 설계 산출물 `design/db-schema`를 25개 테이블로 다시 만들었고, 행 수는 그릴 때마다 실제 DB에서 읽도록 바꿨다.
- **NOT_RUN**: 실제 AMR·Safety Arbiter 발행, 운영 domain 6, PC 간 네트워크, 브라우저 실화면 확인.
- 남은 일: 21단계 PC 1·2·3·4 통합시험. 그 전에 지도·costmap 셀 수 제한(현재 100만)과 영상 5 Hz 처리 제한 미구현을 정리해야 한다.

## 27. 상태 줄 재배치와 한 화면 밀도 조정 (2026-09-07)

- 목적: 20단계 카드가 늘어나면서 상태 줄이 2열 그리드에 3개가 들어가 로봇 카드가 185px 열로 밀렸고, 글자가 세로로 쪼개지며 오른쪽이 비었다.
- 변경 파일: `app/static/css/dashboard.css`.
- 배치: 상태 줄을 같은 폭 2열로 바꾸고 로봇 카드 묶음에 `grid-column: 1 / -1`과 `order: -1`을 줘서 위 줄 전체를 쓰게 했다. 아래 줄에 시스템 상태와 순찰·안전 카드를 나란히 놓았다.
- 밀도: 제목·상태 카드·로봇 카드의 여백과 글자 크기를 줄이고, 요약 항목을 1400px 이상에서 한 줄(5열)로 배치했다. 본문 높이는 590px에서 505px로 줄였다.
- 검증: 임시 DB·임시 서버(5099)와 실제 브라우저에서 1680×1000 기준 문서 높이 1179px → **1000px로 화면에 정확히 들어가는 것**을 확인했다. 지도 365px, 카메라 176px를 유지하며 카드 안 글자 넘침은 0건이다. 1366×768과 1000×900에서도 가로 스크롤이 없고 좁은 폭에서는 요약 항목이 3열·2열로 줄어든다. 확인용 임시 서버와 임시 DB는 삭제했다.
- 전체 단위·요청 시험 107개 통과를 유지한다.
- 추가 압축(2026-09-07): 요약 항목의 마지막 칸이 한 줄을 다 쓰던 `grid-column: 1 / -1`을 상태 줄에서 해제해 다섯 항목을 한 줄에 넣고, 로봇 카드와 요약 카드의 여백·글자를 더 줄였다. 상태 줄 261px → **201px**, 카메라 화면 176px → **207px**, 지도 365px → **428px**로 바뀌었고 1680×1000에서 문서 높이는 그대로 1000px이다.

## 28. 실제 지도 크기 수용과 표시용 영상 5 Hz 제한 (2026-09-07)

- 목적: 21단계 통합 전에 실제 발행 데이터에서 바로 걸릴 두 지점을 정리한다.
- **지도 크기**: `MAP_MAX_CELLS`가 100만이라 100m×100m·5cm 지도(400만 셀)를 거부했다. 제한을 1600만으로 올리고, 화면용 PNG만 `MAP_MAX_IMAGE_SIDE`(기본 2000) 이하로 솎아 저장한다. `map_service.downsample_grid()`는 한 줄씩 슬라이스로 솎아 큰 격자에서도 처리 시간을 짧게 유지한다. costmap도 같은 함수를 쓴다.
  - 좌표 변환에 쓰는 `resolution`·`width`·`height`·`origin`은 원본 값을 그대로 저장한다. 화면은 원본 크기 viewBox에 이미지를 늘려 그리므로 로봇 마커 위치는 달라지지 않는다.
  - 솎기는 최근접 표본이라 이미지의 얇은 장애물이 일부 빠질 수 있다. 판단용 원본 격자는 로봇 쪽 costmap이며 관제 화면은 관측용이다.
- **표시용 영상 5 Hz**: `interfaces.md` 2.5절의 "sysmon adapter는 표시용으로 최대 5 Hz까지만 처리한다"가 구현돼 있지 않아 오는 대로 파일을 교체했다. adapter의 카메라 callback에 토픽별 최소 간격(`CAMERA_MAX_HZ`, 기본 5 Hz)을 두고 초과분은 `camera_frame_throttled`로만 세고 버린다.
- 변경 파일: `app/__init__.py`(설정 3개), `app/services/map_service.py`, `app/services/costmap_service.py`, `app/ros_adapter.py`, `tests/test_map.py`, `tests/test_ros_process_test.py`.
- 검증: 전체 시험 **108개 통과**(ROS source 후). 새 시험은 40×30 격자를 최대 변 10으로 제한했을 때 DB에는 40×30이 남고 PNG 헤더는 10×8이 되는 것, 솎기 함수의 표본 위치와 제한 이하 격자의 무변경을 확인한다. 별도 프로세스 시험에서는 10 Hz 발행 시 `camera_frame_throttled`가 1건 이상 생기는 것을 확인한다.
- 실측: 도메인 93에서 12 Hz로 3초 발행했을 때 카메라 4대 기준 **저장 48건 / 버림 75건**으로 5 Hz 근처를 유지했다.
- 남은 일: 실제 주차장 지도의 크기·해상도를 AMR 담당에게 확인해 `MAP_MAX_IMAGE_SIDE` 값을 최종 결정한다. 발행 측이 모니터링용 영상을 5 Hz로 낮추기로 하면 adapter 제한은 이중 안전장치로 남는다.

## 29. ROS adapter 기능별 파일 분리 (2026-09-07)

- 목적: `app/ros_adapter.py`가 1,086줄이 되어 AGENTS.md의 "기능을 한 파일에 몰아넣지 않는다" 기준에서 벗어났다. 동작은 그대로 두고 파일만 나눈다.
- 구성:
  - `app/ros/errors.py`(9줄): 공통 예외 두 개
  - `app/ros/registry.py`(220줄): 구독 등록표 25개와 계약 enum·토픽 대응표, `active_subscriptions`, `dependency_report`
  - `app/ros/payloads.py`(363줄): ROS 메시지 → 서비스 입력 변환 함수 11개. ROS 노드 없이 부를 수 있는 순수 함수다
  - `app/ros/qos.py`(78줄): interfaces.md 5절 QoS 계약
  - `app/ros/node.py`(470줄): 구독 배선, callback 12개, IngestionAck 회신, `spin`
  - `app/ros_adapter.py`(65줄): 위 모듈의 이름을 모아 노출하는 진입점
- 기존 코드와 시험은 계속 `app.ros_adapter`에서 같은 이름을 가져다 쓴다. `tools/`, `ros_adapter.py`, `ros_topic_test.py`, `ros_process_test.py`, 시험 파일은 한 줄도 고치지 않았다.
- 옮기면서 상대 import 경로를 `..models`, `..services`로 맞추고 등록표 이름 4개를 `node.py` import에 추가했다. 로직 변경은 없다.
- 검증: `.venv` 전체 시험 108개 통과, ROS를 source한 전체 시험 **108개 통과를 2회 연속** 확인했다. `ros_adapter.py --check`도 활성 25개·대기 0개로 이전과 같다.

## 30. CCTV 상태를 차량 입출차 화면에 연결 (2026-09-07)

- 결정: 차량이 실제로 드나드는 지점은 게이트다. **게이트 CCTV의 진입·출차 완료만 입출차 기록으로 저장**하고, 센터 CCTV의 주차 완료·출차 중은 주차장 안 상태라 `cctv_state_events`에만 보존한다. 네 상태를 모두 입차/출차로 저장하면 차량 한 대가 입차 2건·출차 2건으로 세어진다.
- 화면에서는 둘을 합쳐 보여준다. `vehicle_access_service.recent_accesses()`가 게이트 통과 기록과 센터 상태를 시각순으로 합쳐 같은 열 구조로 돌려주므로, 차량 입출차 목록에 `입차 / 주차 완료 / 출차 중 / 출차`가 모두 나타난다. 사용자별 표시 초기화 기준은 두 원본 모두 수신 시각으로 적용한다.
- 변경 파일: `app/services/cctv_service.py`(게이트 상태 → 입출차 변환과 저장), `app/models/cctv.py`(`list_center_states`), `app/services/vehicle_access_service.py`(목록 합치기), `tests/test_cctv.py`.
- ROS 경로로 들어온 CameraState가 입출차 목록을 채우므로, 시연에서 입출차만 HTTP 도구로 따로 넣지 않아도 된다. HTTP 수신 경로는 그대로 남는다.
- 시험 안정화: 별도 프로세스 시험 사이에 DDS 정리 대기 1.5초를 넣고, 판정 실패 시 보고서 핵심을 그대로 출력하도록 했다. 19·20단계 시험은 증적 재조립을 18단계에 맡기고 detection을 끄며, 표시용 영상 5 Hz 제한은 다른 토픽 부하가 적은 전용 시험으로 옮겼다(부하가 크면 BEST_EFFORT 영상이 DDS 단계에서 먼저 밀려 처리 상한을 관측할 수 없다).
- 검증: `.venv` 112개 통과, ROS를 source한 전체 **112개 통과를 2회 연속** 확인했다.

## 31. 위치 무효 상태 수용과 마지막 유효 위치 표시 (2026-09-07)

- 문제: adapter가 `pose_valid=false`인 RobotStatus를 통째로 거부해 로봇이 위치를 잃으면 배터리·임무·연결 상태까지 들어오지 않았다. 관제 권장안의 "현재 유효 pose와 마지막 유효 pose를 서로 다른 마커로 표시"와도 어긋났다.
- 저장: `robot_latest_status`와 `robot_status_history`에 `pose_valid`, `last_valid_pose_at` 열을 추가했다. 기존 행은 좌표가 유효한 상태로만 저장돼 있어 기본값 1로 채운다(`_migrate_pose_validity`, 열 추가만 하므로 이력을 지우지 않는다).
- 수신: `pose_valid=false`면 좌표를 저장하지 않고(NULL) 배터리·임무·연결 상태와 마지막 유효 시각만 남긴다. 무효 좌표를 현재 위치처럼 표시하지 않는다.
- 표시: 카드의 위치 문구가 `마지막 유효 map (12.00, 8.00)`으로 바뀌고, 지도에서는 마지막 유효 위치를 속이 빈 점선 마커와 다른 문구로 그린다. 좌표 경고에도 "현재 위치가 무효" 문구를 추가했다. 최근 경로 조회는 유효 좌표만 사용하므로 그대로다.
- 변경 파일: `app/schema.sql`, `app/database.py`, `app/models/robot.py`, `app/services/robot_service.py`, `app/services/map_service.py`, `app/ros/payloads.py`, `app/static/js/map.js`, `app/static/css/dashboard.css`, `tests/test_robot_status.py`, `tests/test_ros_adapter.py`.
- 검증: `.venv` 114개 통과, ROS를 source한 전체 **114개 통과**. 새 시험은 무효 위치 수신 시 좌표가 NULL로 남고 배터리·임무는 유지되며 카드가 마지막 유효 위치를 보여주는 것, adapter 변환이 좌표를 비우고 `last_valid_pose_at`을 채우는 것을 확인한다.
- 남은 일: 관제 판단 토픽(`/control/operational_state`·`operational_event`)이 확정되면 STALE·UNREPORTED 판정 주체를 관제로 옮기고 현재 계산은 대체 표시로 남긴다.

## 32. 제품 코드와 시험 코드 폴더 분리 (2026-09-07)

- 목적: 코드리뷰 기준이 "실제 솔루션에 적용될 코드(테스트용 코드 제외)"라, 시험 하네스가 제품 패키지 안에 있으면 범위가 흐려진다.
- 이동: `app/ros_topic_test.py`, `app/ros_process_test.py`, `app/load_test.py` → **`testkit/`**. 가상 ROS publisher, 격리 DDS 종단시험, 부하 측정처럼 실제 서비스 실행에 쓰지 않는 코드만 담는다.
- 이동한 파일의 상대 import를 `app.` 절대 경로로 바꾸고, `tests/` 3개와 `tools/` 4개의 import 경로를 갱신했다. 제품 코드는 `testkit/`을 import하지 않는다.
- 결과 구조: 리뷰 대상은 `run.py`, `ros_adapter.py`, `app/`(routes·services·models·ros·templates·static)이고, `testkit/`·`tests/`·`tools/`는 검증·시연용이다. README에 폴더 구분 표를 추가했다.
- 검증: `.venv` 114개 통과, ROS를 source한 전체 **114개 통과**. 시험 CLI(`tools/run_ros_topic_test.py`)도 `local_pass=true`로 이전과 같이 동작한다.

## 33. 증적 지연·누락 표시와 관제 판단 토픽 요청서 (2026-09-07)

- 배경: 관제 설계 제안(Sysmon 팀 소통사항 3.1~3.7)을 현재 구현과 대조했다. 3.3 STALE·UNREPORTED 분리, 3.6 TRANSIENT_LOCAL 복원, 3.7 Dashboard 제외 목록은 이미 같은 방식이었다.
- **증적 지연·누락(3.5 일부) 반영**: 저장값 `INCOMPLETE`·`STORED`·`REJECTED`는 그대로 두고, 조립이 끝나지 않은 경과 시간으로 화면에서 `DELAYED`(기본 30초)·`MISSING`(기본 300초)을 계산한다. 관제가 없는 결과를 만들어 저장하지 않는다는 원칙을 지키기 위해 파생 표시로만 구분했다.
  - 변경 파일: `app/__init__.py`(임계값 2개), `app/models/event.py`(목록·상세 조회에 조립 상태 join), `app/services/event_service.py`(`evidence_state`, 라벨), `app/static/js/events.js`·`dashboard.css`(주황 표시), `tests/test_detection_ingestion.py`.
- **[CR-003](../../docs/change_requests/CR-003_09-07_18-10_관제_판단_토픽_2종_도입.md) 작성**: `/control/operational_state`·`/control/operational_event` 도입에 동의하되 21단계 이후 반영을 제안했다. 새 메시지 두 개가 계약 v1.1과 네 PC 재빌드를 요구하고, 현재 자체 계산 중인 STALE·UNREPORTED·CCTV timeout과 판단 주체가 겹치기 때문이다. 필드명 `event_id` 충돌과 전환 시점도 확정 대상으로 적었다.
  - 같은 요청서에 PostgreSQL 전환은 13단계 측정치를 근거로 운영 전환 과제로 남기고, durable spool은 계약 3.8절의 생산자 재전송과 중복이라는 검토 결과를 함께 남겼다.
- 검증: `.venv` 115개 통과, ROS를 source한 전체 시험도 통과. 새 시험은 조각이 하나만 도착한 증적이 시간 경과에 따라 `INCOMPLETE → DELAYED → MISSING`으로 바뀌고, 나머지 조각이 도착하면 `STORED`가 되는 것을 확인한다.

## 34. E-stop 계약 EStop 전환과 RobotStatus safety_state 표시 (2026-09-08)

- 배경: main에 병합된 interfaces.md 3.1·4절(2026-09-08 결정)과 관제 요청서 [CR-관제_09-08_15-15_System_monitor_E-stop_UI_운영상태_연계](../../../docs/change_requests/CR-관제_09-08_15-15_System_monitor_E-stop_UI_운영상태_연계.md)를 반영했다. 기존 구독 타입 `EStopState`는 계약 타입 `EStop`과 달라 DDS 매칭 자체가 되지 않는 상태였다.
- **EStop 전환**: `/control/estop`을 `patrol_interfaces/msg/EStop`으로 구독한다. 계약 필드 `target_robot_id`(robot1·robot6·all)·`active`·`reason`(0~6)·`sequence`만 쓰고, 공용 `.msg`에 아직 남은 `latched`는 읽지 않는다. `estop_id`·`message_id`·`manual_reset_required`·`source_id` 의존을 제거했다.
- 저장: `estop_latest`를 대상별 한 행(PK `target_robot_id`)으로, `estop_history`를 활성·해제·대표 원인이 바뀐 시점만 남기는 구조로 바꿨다. 옛 구조 표는 `_migrate_estop_contract`가 기록이 있으면 `_legacy`로 이름을 바꿔 보존하고 없으면 지운다. 옛 열은 새 계약에 대응 값이 없어 옮기지 않는다.
- 표시: `/api/safety/status`의 `estop`은 전체 요약(`active`·`state_label`·대표 원인 라벨)과 `targets`(대상별 수신 여부·활성·stale)를 준다. `all` 활성은 두 로봇 모두 정지 대상이라는 뜻이며, 정지 명령이 있었다는 사실만 보여 준다. 실제 정지 여부는 RobotStatus 쪽에서 따로 표시한다. `manual_reset_required`·`latched`는 응답에서 제거했다.
- **safety_state 표시**: RobotStatus의 `safety_state`(UNKNOWN=0…ERROR=5)·`motion_stopped`·`reason_code`·`reason`을 `robot_latest_status`·`robot_status_history`에 저장한다(`_migrate_safety_state`, 열 추가만). 로봇 카드에 "안전 상태" 줄을 추가해 `E-stop 활성 · 이동 가능 상태 · 원인 702`처럼 safety_state와 실제 정지 확인을 함께 적는다. ESTOPPED만으로 정지를 단정하지 않는다는 계약 문구를 그대로 따른 것이다. 임시 HTTP 입력은 값이 없으면 UNKNOWN이다.
- 통합 이력: ESTOP 검색이 대상·대표 원인 라벨을 요약에 넣고, 로봇 필터(AMR1·AMR2)로 검색하면 해당 로봇과 `all` 대상 기록을 함께 보여 준다.
- 요청서 회신 근거: `MissionCommandAck.msg`·`ControlHeartbeat.msg`·`CommandCheck`·`parameters_json`은 시스템 모니터가 구독·발행하지 않아 코드 변경이 없다. `EStopState.msg`는 이번 전환으로 소비처가 없어졌다. UI 정지·해제 버튼과 `active_reasons`·CONTROL_SHUTDOWN 표시는 PM 결정과 TBD-CTRL-004·IF-011 계약이 없어 착수하지 않았다.
- **공용 `.msg`를 interfaces.md대로 맞췄다.** `EStop.msg`에서 `latched`를 제거하고 `ESTOP_REASON_*`(0~6)·`TARGET_ALL` 상수를 넣었다. `ControlHeartbeat.msg`를 `header`·`control_session_id`·`uint64 sequence`로 바꿨다. `MissionCommand.msg`에서 `parameters_json`을 제거하고 명령별 필수값 표를 주석으로 옮겼다. `CommandCheck.msg`에 `CHECK_*`(0~3), `RobotStatus.msg`에 `SAFETY_*`(0~5) 상수를 추가했다. `MissionCommandAck.msg`·`EStopState.msg`는 삭제했다. `colcon build --packages-select patrol_interfaces` 성공.
- AMR 후속 작업(AMR 담당): `local_safety_supervisor.py`가 `message.latched`를 읽고 `estop_guard.observe()`가 `latched` 인자를 받는다. 새 `EStop`에는 이 필드가 없으므로 수신 콜백에서 AttributeError가 난다. `estop_guard`가 `target_robot_id == 'all'`을 자기 대상으로 처리하지 않는 점도 계약과 다르다. `mission_command_parser.py`는 `getattr(msg, 'parameters_json', '')`이라 빌드·실행은 되지만 내부 지문·저장 열은 정리 대상이다.
- 변경 파일: `app/ros/registry.py`, `app/ros/payloads.py`, `app/ros/node.py`, `app/models/safety.py`, `app/models/robot.py`, `app/models/history.py`, `app/services/safety_service.py`, `app/services/robot_service.py`, `app/schema.sql`, `app/database.py`, `app/templates/index.html`, `app/static/js/dashboard.js`, `app/static/css/dashboard.css`, `tests/test_patrol_safety.py`, `tests/test_ros_adapter.py`, `testkit/ros_topic_test.py`.
- 검증: `.venv` 119개 통과(ROS 7개 skip), ROS를 source한 전체 **119개 통과**. 별도 프로세스 DDS 시험(도메인 격리)에서 `/control/estop`이 `EStop`으로 매칭돼 대상별 최신 행과 변경 이력이 저장되는 것을 확인했다. 이 시험이 첫 구현의 migration 결함(재초기화 때마다 `estop_history`를 legacy로 넘김)을 잡아내 고쳤다.

## 35. v1.0 기준선 병합 확인 (2026-09-08)

- main의 v1.0 확정(interfaces.md, 관제 v1.0 기준선)을 브랜치에 병합했다. System monitor 코드 변경이 필요한 항목은 없다.
  - E-stop 대표 원인 우선순위 `SYSTEM_FAULT → UNKNOWN → OPERATOR → KEEPOUT_FAILURE → COMMUNICATION → OBSTACLE → TOKEN`: 모니터는 수신 reason을 그대로 표시하므로 영향 없음. [요청서 회신](../../../docs/change_requests/CR-관제_09-08_18-24_System_monitor_v1.0_E-stop_우선순위.md)에 `변경 불필요`로 적었다.
  - PatrolReport reason code 203~206 추가: `reason_code`를 정수로 저장·표시하므로 영향 없음.
  - Keepout parameter가 base·center corridor 이중 구조로 확정: 모니터는 `KeepoutStatus` 토픽만 소비하므로 영향 없음. 정식 상태 토픽은 TBD-IF-008.
  - main이 `RobotStatus.msg`에 `SAFETY_*` 상수를 넣어 34번의 것과 중복됐다. 주석 있는 블록 하나만 남겼다.
- main이 `docs/설계기준-차이-정리.md`를 삭제했다(v1.0 정리). 재생성하지 않는다. 34번 항목의 해당 파일 언급은 이력으로 남긴다.
