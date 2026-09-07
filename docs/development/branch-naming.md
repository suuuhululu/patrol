# 브랜치 네이밍 규칙

## 형식

```text
<type>/<scope>/<description>
<type>/<scope>/<issue-number>-<description>
```

이슈 번호는 선택 사항이다. 관련 GitHub 이슈가 실제로 있을 때 번호를 사용하며 `#`는 붙이지 않는다.

## type

| 값 | 용도 |
| --- | --- |
| `feat` | 기능 추가 |
| `fix` | 오류 수정 |
| `docs` | 문서 작성·수정 |
| `refactor` | 외부 동작을 유지하는 코드 구조 개선 |
| `test` | 테스트 추가·수정 |
| `chore` | 의존성·개발 도구·CI·설정 유지보수 |

## scope

| 값 | 영역 |
| --- | --- |
| `amr` | AMR1·AMR2 공통 로봇 코드 |
| `control` | 통합 관제·명령·주행 권한·교대 |
| `vision` | 영상 분석·탐지 이벤트 |
| `sysmon` | 상태 모니터링·기록·대시보드 |
| `interfaces` | 공통 메시지·서비스·액션 |
| `bringup` | 실행 구성·로봇별 설정·지도 |
| `system` | 전체 시스템·공통 협업 문서·저장소 운영 |

## description

- 영문 소문자와 숫자를 사용하고 단어 사이는 하이픈(`-`)으로 연결한다.
- 공백·한글·밑줄은 사용하지 않는다.
- 작업 목적을 짧고 구체적으로 표현한다.
- 사람 이름이나 PC 이름만으로 목적을 대신하지 않는다.
- AMR별 설정 변경은 설명에 `amr1` 또는 `amr2`를 포함할 수 있다.
- 여러 영역을 변경하면 주된 영역을 선택한다. 시스템 전반 작업은 `system`을 사용한다.

## 예시

```text
docs/system/update-architecture
docs/system/add-git-guide
feat/amr/battery-handover
fix/control/token-timeout
feat/vision/gate-event
feat/sysmon/status-dashboard
feat/interfaces/42-add-robot-status
chore/bringup/update-amr2-config
test/control/handover-recovery
```

피할 이름: `my-work`, `AMR1`, `pm`, `feature/new`, `docs/system/final-final`.

## 공통 기준

- 기본 브랜치는 `main`이며 작업 브랜치 규칙의 예외다.
- 초기 운영에서는 별도 `develop`이나 PC별 영구 브랜치를 만들지 않는다.
- 같은 목적의 코드와 문서 변경은 같은 브랜치에서 처리할 수 있다.
- 다른 목적의 작업은 새 브랜치로 분리한다.
- 도구가 필수 접두사를 요구하는 경우 해당 제약을 따르되 작업 목적이 드러나는 이름을 유지하고 PR에 설명한다.

## 관련 문서

- [버전 관리](version-control.md)
- [PR 가이드](pull-request-guide.md)
- [브랜치 사용 가이드](branch-guide.md)
