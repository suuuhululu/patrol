# 브랜치 네이밍 규칙

## 형식

```text
<category>/<description>
<category>/<issue-number>-<description>
```

기존 type과 scope를 하나의 **작업분류(category)**로 통합한다. 작업분류는 무엇을 수정하는지, 작업설명(description)은 어떤 변경을 하는지를 나타낸다. 기능 추가·오류 수정·테스트 여부는 설명에 `add`, `fix`, `test` 등을 사용해 표현한다.

이슈 번호는 선택 사항이다. 실제 관련 GitHub 이슈가 있을 때만 번호를 사용하며 `#`는 붙이지 않는다.

## 작업분류

| 값 | 선택 기준 |
| --- | --- |
| `amr` | AMR1·AMR2 공통 로봇 코드와 해당 테스트 |
| `control` | 통합 관제·명령·주행 권한·교대 코드와 해당 테스트 |
| `vision` | 영상 분석·탐지 이벤트 코드와 해당 테스트 |
| `sysmon` | 상태 모니터링·기록·대시보드 코드와 해당 테스트 |
| `interfaces` | 공통 메시지·서비스·액션 정의와 호환성 테스트 |
| `bringup` | 실행 구성·로봇별 설정·지도 |
| `docs` | 문서만 작성하거나 수정하는 작업 |
| `chore` | 저장소 구조·공통 개발 도구·CI·공통 의존성 관리 |

### 선택 순서

1. 문서만 변경하면 `docs`를 사용한다. 문서 주제가 AMR이어도 동일하다.
2. 코드·설정·테스트를 변경하면 주된 담당 영역을 사용한다. 관련 문서를 함께 수정해도 같은 브랜치에 포함한다.
3. 특정 기능 영역에 속하지 않는 저장소·공통 개발 환경 작업은 `chore`를 사용한다.
4. 여러 기능 영역을 함께 수정해야 하면 주된 변경 영역을 선택하고 PR에 영향 영역을 기록한다. 목적이 다른 작업은 분리한다.

## 작업설명

- 영문 소문자와 숫자를 사용하고 단어 사이는 하이픈(`-`)으로 연결한다.
- 공백·한글·밑줄은 사용하지 않는다.
- `add-battery-handover`, `fix-token-timeout`, `test-handover-recovery`처럼 변경 목적을 짧고 구체적으로 쓴다.
- 사람 이름이나 PC 이름만으로 목적을 대신하지 않는다.
- AMR별 설정 변경은 설명에 `amr1` 또는 `amr2`를 포함할 수 있다.

## 예시

```text
docs/update-architecture
docs/add-git-guide
amr/add-battery-handover
control/fix-token-timeout
vision/add-gate-event
sysmon/add-status-dashboard
interfaces/42-add-robot-status
bringup/update-amr2-config
control/test-handover-recovery
chore/update-ci
```

피할 이름: `my-work`, `AMR1`, `pm`, `docs/final-final`.

## 공통 기준

- 기본 브랜치는 `main`이며 작업 브랜치 규칙의 예외다.
- 초기 운영에서는 별도 `develop`이나 PC별 영구 브랜치를 만들지 않는다.
- 새 작업 브랜치부터 이 규칙을 적용한다. 이미 공유된 브랜치는 해당 PR을 마칠 때까지 유지할 수 있다.
- 도구가 필수 접두사를 요구하는 경우 해당 제약을 따르되 작업 목적이 드러나는 이름을 유지하고 PR에 설명한다.

## 관련 문서

- [버전 관리](version-control.md)
- [PR 가이드](pull-request-guide.md)
- [브랜치 사용 가이드](branch-guide.md)
- [GitHub 인증 저장 가이드 — 반복 로그인 줄이기](git-authentication.md)
