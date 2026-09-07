# GitHub 인증 저장 가이드

매번 `git pull`·`git push`할 때 인증 정보를 입력하지 않도록 설정하는 방법이다. Ubuntu 24.04 개발 PC와 macOS에서 사용한다. 이 문서는 설정 절차이며, 문서 추가만으로 PC의 인증 설정이 바뀌지는 않는다.

## 어떤 비밀번호인가요?

- GitHub HTTPS 인증: GitHub 계정 비밀번호 대신 브라우저 로그인 또는 토큰을 사용한다.
- SSH 키 암호(passphrase): 개인키 보호용 암호이며 GitHub 계정 비밀번호와 다르다.
- `sudo` 비밀번호: OS 관리자 인증이다. 이 가이드는 이를 없애지 않는다.
- 웹 브라우저 로그인과 터미널 Git 인증은 별개다.

각 개발자는 각 PC의 본인 OS 계정에서 본인의 GitHub 계정을 사용한다. 팀원의 토큰이나 개인키를 복사해 공유하지 않는다.

## 권장 방법: HTTPS + GitHub CLI

현재 저장소의 HTTPS 주소를 유지할 수 있다. OS의 안전한 자격 증명 저장소를 사용할 수 있는 데스크톱 환경에 적합하다.

### 1. 설치

```bash
# Ubuntu 24.04: Ubuntu 패키지 저장소의 GitHub CLI 설치
sudo apt update
sudo apt install gh

gh --version
```

패키지를 찾지 못하거나 최신 CLI가 필요하면 [공식 Linux 설치 안내](https://github.com/cli/cli/blob/trunk/docs/install_linux.md)를 따른다.

macOS에서는 Homebrew가 이미 설치되어 있다면 `brew install gh`를 사용한다. 그 외에는 [GitHub CLI 공식 설치 페이지](https://cli.github.com/)를 따른다.

### 2. 최초 로그인과 Git 연결

```bash
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git --hostname github.com
gh auth status --hostname github.com
```

출력된 안내에 따라 브라우저에서 본인 계정으로 인증한다. Git 인증 연결 질문이 나오면 동의한다. `setup-git`은 Git이 CLI에 저장된 인증을 사용하도록 연결한다.

CLI는 OS의 자격 증명 저장소 사용을 시도한다. 사용할 수 없으면 평문 파일로 저장될 수 있으므로 로그인 결과와 `gh auth status`의 저장 위치를 확인한다. 평문 저장 경고가 나오면 계속 사용하는 대신 OS 키링을 설정하거나 아래 SSH 방법을 선택한다. Ubuntu에서는 로그인한 데스크톱 세션의 키링이 잠겨 있지 않아야 한다. macOS에서는 Keychain을 사용한다. `--insecure-storage`는 사용하지 않는다. [CLI 로그인 안내](https://cli.github.com/manual/gh_auth_login)

### 3. 저장소 접근 확인

터미널에서 본인 PC의 `patrol` 폴더로 이동한 뒤 실행한다.

```bash
git remote -v
git ls-remote origin HEAD
```

이 절차의 원격 주소는 `https://github.com/suuuhululu/patrol.git`이다. 기존 주소가 다르면 용도를 확인한 뒤 이 저장소에서만 아래 명령을 실행한다.

```bash
git remote set-url origin https://github.com/suuuhululu/patrol.git
```

이후 새 터미널에서도 `git ls-remote origin HEAD`가 추가 로그인 없이 성공하는지 확인한다. 이 명령은 파일이나 원격 브랜치를 변경하지 않는다. 키링 잠금·토큰 만료·인증 취소·조직 정책 변경 시에는 다시 인증할 수 있다.

## 대안: SSH 키 + ssh-agent

키링을 사용할 수 없는 원격 Ubuntu 세션 등에서는 SSH를 선택할 수 있다. 이 경우 저장소 주소도 SSH로 바꾼다. 암호를 없애는 대신 agent가 잠금 해제된 키를 기억하게 한다.

### 1. 키 생성

기존 키를 먼저 확인한다. 아래 파일이 이미 있으면 덮어쓰지 말고 기존 키를 사용하거나 다른 이름을 정한다.

```bash
ls -l ~/.ssh/id_ed25519_patrol*
ssh-keygen -t ed25519 -C "your-github-email@example.com" -f ~/.ssh/id_ed25519_patrol
```

이메일 예시는 본인 값으로 바꾼다. 생성 과정에서 키 암호를 설정한다. 개인키 `id_ed25519_patrol`은 PC에 보관하고, GitHub에는 다음 공개키만 등록한다.

```bash
cat ~/.ssh/id_ed25519_patrol.pub
```

GitHub의 Settings → SSH and GPG keys → New SSH key에서 Authentication Key로 등록한다. 이름에는 본인 PC를 구분할 수 있는 값을 사용한다. [SSH 키 생성 안내](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent)

### 2. Ubuntu에서 agent에 등록

```bash
ssh-add -l
```

agent에 연결할 수 없다는 오류가 나오면 현재 셸에서 한 번 실행한다. 이미 agent가 있으면 새로 만들지 않는다.

```bash
eval "$(ssh-agent -s)"
```

키를 추가하고 암호를 한 번 입력한다.

```bash
ssh-add ~/.ssh/id_ed25519_patrol
```

같은 agent를 사용하는 동안 매번 암호를 입력하지 않는다. 새로 시작한 agent나 재부팅 후에는 다시 입력할 수 있다. 위 `eval`을 셸 시작 파일에 무조건 넣으면 터미널마다 agent가 생길 수 있다. 세션을 넘겨 유지하려면 데스크톱 키링 연동을 사용한다.

### 3. SSH 설정

`~/.ssh/config`의 기존 내용을 유지하면서 아래 항목을 추가한다. 이미 `Host github.com` 설정이 있으면 중복 생성하지 말고 해당 항목을 검토하여 반영한다.

```sshconfig
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_patrol
    IdentitiesOnly yes
    AddKeysToAgent yes
```

여러 GitHub 계정을 사용하는 PC는 Host 별칭을 분리해야 하므로 이 단일 계정 예시를 그대로 적용하지 않는다.

macOS에서는 위 항목에 `UseKeychain yes`를 추가하고 Apple 기본 명령으로 등록한다. Ubuntu 설정에는 `UseKeychain`을 넣지 않는다.

```bash
/usr/bin/ssh-add --apple-use-keychain ~/.ssh/id_ed25519_patrol
```

### 4. 접속 확인과 원격 주소 변경

```bash
ssh -T git@github.com
```

최초 연결 시 호스트 지문을 [GitHub 공식 SSH 지문](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)과 비교한 뒤 신뢰 여부를 결정한다. 본인 계정 이름과 인증 성공 메시지를 확인한다. GitHub는 셸 접속을 제공하지 않아 인증에 성공해도 이 명령의 종료 코드는 1일 수 있다.

`patrol` 저장소 안에서 실행한다.

```bash
git remote set-url origin git@github.com:suuuhululu/patrol.git
git ls-remote origin HEAD
```

## 자주 발생하는 문제

| 현상 | 확인 방법 |
| --- | --- |
| HTTPS에서 계속 인증을 요구함 | `gh auth status`와 `gh auth setup-git --hostname github.com` 확인. 키링 잠금 여부 확인. |
| 잘못된 GitHub 계정으로 연결됨 | CLI 또는 SSH 인증 결과의 계정 확인. 각 계정의 저장소 접근 권한 확인. |
| SSH에서 키 암호를 계속 요구함 | `ssh-add -l`과 현재 agent 연결 상태 확인. |
| 저장소를 찾지 못하거나 접근이 거부됨 | Collaborator 초대 수락 여부, 본인 계정과 원격 주소 확인. |
| workflow 권한 부족으로 푸시 거부됨 | 인증 저장과 권한은 별개다. 워크플로 변경에 필요한 권한만 별도로 검토한다. |

`git config user.name`과 `user.email`은 커밋 작성자 표시이며 로그인 설정이 아니다. 토큰을 원격 URL에 넣거나 `credential.helper store`로 평문 저장하지 않는다. 토큰·개인키·키 암호는 저장소나 채팅에 기록하지 않는다.

## 공식 참고 자료

- [GitHub 인증 캐싱](https://docs.github.com/en/get-started/git-basics/caching-your-github-credentials-in-git)
- [GitHub CLI의 Git 연결](https://cli.github.com/manual/gh_auth_setup-git)
- [SSH 연결 테스트](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/testing-your-ssh-connection)

## 관련 문서

- [버전 관리](version-control.md)
- [PR 가이드](pull-request-guide.md)
- [브랜치 네이밍](branch-naming.md)
- [브랜치 사용](branch-guide.md)
