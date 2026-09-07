# 브랜치 사용 가이드

`main`과 짧게 유지하는 작업 브랜치로 협업한다. 각 PC는 같은 저장소를 내려받되 담당 작업별 브랜치를 사용한다. AMR1·AMR2 코드의 기준은 하나이며 설정으로 차이를 관리한다.

## 1. 새 작업 시작

저장소 루트에서 작업 상태를 확인한다.

```bash
git status
git branch --show-current
```

커밋하지 않은 변경이 없을 때 다음을 실행한다.

```bash
git switch main
git pull --ff-only origin main
git switch -c docs/add-git-guide
```

브랜치 이름은 실제 작업에 맞춰 바꾼다. `main`이 없거나 pull이 실패하면 원인을 확인한다. 강제 초기화로 해결하지 않는다.

## 2. 이미 수정 중인 파일이 있을 때

현재 브랜치를 확인한 뒤, 현재 체크아웃에서 새 브랜치를 만들면 기존 미커밋 변경을 유지할 수 있다.

```bash
git status
git switch -c docs/update-architecture
```

이 방법은 현재 브랜치의 기존 커밋도 상속한다. 관련 없는 커밋이 있는 브랜치에서 시작했다면 PR 전 비교 범위를 확인하고 작업을 분리한다. 기존 작업 브랜치가 이미 해당 목적이라면 새로 만들 필요가 없다.

로컬 저장, 커밋, 푸시는 각각 별개 단계다. 최초 문서 업로드 이후의 변경은 작업 브랜치와 PR을 통해 반영한다.

## 3. 작업하고 커밋

```bash
git diff
git add docs/development/branch-guide.md
git diff --cached
git commit -m "docs(system): 브랜치 사용 가이드 추가"
```

파일 경로와 메시지는 실제 작업에 맞게 변경한다. 새 파일은 추가 전 직접 확인하고 추가 후 staged diff를 확인한다. 기존에 스테이징된 파일이 있는지도 확인한다.

## 4. 최신 main 반영

작업 브랜치에서 미커밋 변경을 정리한 뒤 실행한다.

```bash
git fetch origin
git merge origin/main
```

공유 브랜치는 기본적으로 merge로 갱신하여 기존 커밋 이력을 다시 쓰지 않는다. 충돌이 생기면 다음과 같이 처리한다.

1. `git status`로 충돌 파일을 확인한다.
2. 양쪽 변경 의도를 확인하여 올바른 최종 내용으로 수정한다.
3. `<<<<<<<`, `=======`, `>>>>>>>` 충돌 표시를 제거한다.
4. 해당 파일을 `git add <파일>`로 추가하고 `git merge --continue`를 실행한다.
5. 영향을 받는 검사와 문서 내용을 다시 확인한다.

해결 방향이 불확실하면 담당자와 조율한다. merge를 취소하려면 `git merge --abort`를 사용한다. merge 전 변경을 정리해 두는 것이 중요하다.

## 5. PR 제출

향후 푸시하기로 결정한 작업에만 실행한다.

```bash
git diff --stat origin/main...HEAD
git log --oneline origin/main..HEAD
git push -u origin docs/add-git-guide
```

푸시할 이름은 현재 작업 브랜치와 일치해야 한다. GitHub에서 대상 `main`으로 PR을 만들고 [PR 가이드](pull-request-guide.md)의 승인 절차를 따른다.

## 6. 병합 후 다음 작업

GitHub에서 PR 병합 완료를 확인하고 로컬 미커밋 변경이 없는 상태에서 실행한다.

```bash
git switch main
git pull --ff-only origin main
git fetch --prune
git branch -d docs/add-git-guide
```

Squash merge에서는 원래 작업 커밋이 `main`에 그대로 포함되지 않으므로 `git branch -d`가 삭제를 거부할 수 있다. 이때는 브랜치를 그대로 두고 PR 병합 여부와 남은 작업을 확인한다. 강제 삭제는 기본 절차에 포함하지 않는다. 다음 작업은 갱신된 `main`에서 새 브랜치를 만든다.

## 협업 주의사항

- 하나의 브랜치는 원칙적으로 한 사람이 담당한다.
- 다른 사람이 작업하는 브랜치를 임의로 갱신하거나 강제 푸시하지 않는다.
- 같은 문서를 동시에 수정할 경우 담당 절과 작업 범위를 먼저 공유한다.
- `main`에 직접 작업·푸시하지 않는다.
- 이미 병합한 브랜치를 다음 작업에 재사용하지 않는다.
- 안전 관련 변경은 자동 검사와 실제 장비 검증 여부를 구분하여 PR에 기록한다.

## 관련 문서

- [버전 관리](version-control.md)
- [PR 가이드](pull-request-guide.md)
- [브랜치 네이밍 규칙](branch-naming.md)
