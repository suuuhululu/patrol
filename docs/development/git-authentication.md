# GitHub PAT 인증 저장 가이드 — 처음 시작하는 사람용

이 가이드는 **PAT를 한 번 입력하고, 이후 Git 작업에서는 PC가 기억하게 만드는 방법**이다. Ubuntu 24.04를 기준으로 설명하고 macOS 방법도 함께 제공한다.

PAT는 Personal Access Token의 줄임말로, **개인용 액세스 토큰**이라는 뜻이다. GitHub가 만들어 주는 긴 임시 비밀번호라고 생각하면 된다. SSH 개인키와는 다른 인증 수단이다. 이 문서에서는 SSH 키를 만들지 않는다.

## 0. 먼저 알아둘 것

| 이름 | 쉬운 설명 |
| --- | --- |
| GitHub | 팀의 파일을 보관하는 온라인 공간 |
| Git | 내 PC와 GitHub 사이에서 파일 이력을 관리하는 도구 |
| 저장소(repository) | 프로젝트 파일을 모아 둔 공간. 우리 저장소는 `suuuhululu/patrol`이다. |
| 터미널 | 명령어를 입력하는 창 |
| PAT | GitHub 계정 비밀번호 대신 Git에 입력하는 인증 문자열 |
| 키링·키체인 | PC가 비밀번호를 보관하는 잠금장치가 있는 저장 공간 |

준비물은 본인 GitHub 계정, `patrol` 협업 초대 수락, 인터넷 연결이다. **각자 자기 계정에서 토큰을 만든다. PM이나 다른 팀원의 토큰을 함께 쓰지 않는다.**

아래 회색 상자의 명령어를 한 줄씩 복사하고 Enter를 누른다. `#`로 시작하는 줄은 설명이므로 입력하지 않아도 된다. 실제 토큰은 명령어에 끼워 넣지 않고, 나중에 나오는 `Password` 입력란에만 붙여 넣는다.

이 문서는 따라 하는 방법을 설명한다. 문서가 GitHub에 올라왔다고 PC 설정이 자동으로 바뀌지는 않는다.

## 1. GitHub에서 PAT 만들기

### 협업자로 참여한 팀원: Tokens (classic)

현재 `patrol`은 개인 계정 소유의 비공개 저장소다. 다른 계정의 협업자로 참여하는 경우 fine-grained PAT 사용에 제한이 있어, 팀원은 classic PAT로 진행한다. Classic의 `repo` 권한은 이 저장소만이 아니라 본인이 접근할 수 있는 다른 비공개 저장소에도 적용될 수 있다. 만료일을 정하고 필요한 권한만 선택한다. 이 제한은 바뀔 수 있으므로 [GitHub PAT 공식 안내](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)를 기준으로 한다.

1. 브라우저에서 GitHub에 **본인 계정으로** 로그인한다.
2. 오른쪽 위 프로필 사진 → **Settings**를 누른다. 저장소의 Settings가 아니라 개인 계정 설정이다.
3. 왼쪽 메뉴 아래의 **Developer settings**를 누른다.
4. **Personal access tokens → Tokens (classic)**을 누른다.
5. **Generate new token → Generate new token (classic)**을 누른다. 본인 확인 화면이 나오면 완료한다.
6. **Note**에 `patrol-ubuntu-my-pc`처럼 용도를 적고, **Expiration**은 우선 `30 days`로 정한다.
7. **Select scopes**에서 `repo`를 선택한다. `.github/workflows/` 파일도 수정할 담당자는 `workflow`도 선택한다. 문서·일반 코드 작업만 하는 사람은 추가하지 않는다.
8. **Generate token**을 누른다. 표시된 긴 문자열을 복사해 본인의 비밀번호 관리자에 보관한다. 전체 문자열은 다시 볼 수 없으므로 잃어버리면 새로 발급한다.

### 저장소 소유자: Fine-grained token 선택 가능

저장소 소유자 `suuuhululu`는 **Personal access tokens → Fine-grained tokens → Generate new token**에서 만든다. 만료일은 30일, Resource owner는 본인, Repository access는 **Only select repositories → patrol**로 정한다. Repository permissions에서 **Contents: Read and write**를 선택한다. 워크플로 파일 변경 담당인 경우에만 **Workflows: Read and write**도 선택한다. PR은 브라우저에서 작성할 수 있다.

토큰을 만들었다면 아래 PC 설정을 계속 진행한다. 토큰은 기존 계정의 접근 권한을 넘어서 권한을 주지 않으므로, 협업 초대를 먼저 수락해야 한다.

## 2. 터미널에서 patrol 폴더 열기

**Ubuntu:** 파일 앱에서 `patrol` 폴더를 열고 빈 곳을 마우스 오른쪽 버튼으로 눌러 ‘터미널에서 열기’를 선택한다. 해당 메뉴가 없으면 터미널을 열고 `cd` 뒤에 실제 폴더 경로를 입력한다.

**현재 PM의 macOS:** 터미널에서 아래 명령으로 이동할 수 있다. 다른 사람은 자신의 경로를 사용한다.

```bash
cd /Users/suhyun/Downloads/patrol
```

위 경로는 이 문서를 작성한 PC의 예시이며 공용 경로가 아니다.

```bash
git status
git remote -v
```

`not a git repository`가 나오면 프로젝트 폴더를 잘못 연 것이다. `.git`이 들어 있는 실제 `patrol` 폴더로 이동한다. 이 오류를 해결하려고 무작정 `git init`을 실행하지 않는다.

아래 명령은 이 프로젝트의 GitHub 연결 주소를 HTTPS로 맞춘다.

```bash
git remote set-url origin https://github.com/suuuhululu/patrol.git
```

아직 프로젝트가 없는 사람은 먼저 다음 3단계에서 Git과 저장 도구를 준비한 뒤, 원하는 상위 폴더에서 `git clone https://github.com/suuuhululu/patrol.git`으로 내려받고 `cd patrol`로 들어온다. clone 중 인증을 물으면 4단계의 설명대로 입력한다. 이후 저장 설정을 마치면 된다.

## 3. PC가 토큰을 기억하도록 설정하기

**자신의 운영체제 한 가지만 선택한다.** 저장 도구는 한 번 준비하면 되고, 아래 Git 설정은 `patrol` 저장소 안에서 실행한다. `--local`은 이 프로젝트에만 적용한다는 뜻이다.

### Ubuntu 24.04 데스크톱

Ubuntu의 비밀번호 보관함을 사용하는 `libsecret` 도구를 준비한다. 바탕화면에 로그인한 터미널에서 진행한다. 화면 없는 서버나 원격 터미널만 사용하는 환경은 아래 별도 설명을 참고한다.

먼저 필요한 프로그램을 설치한다.

```bash
sudo apt update
sudo apt install git build-essential pkg-config libsecret-1-dev gnome-keyring seahorse
```

`sudo`가 묻는 비밀번호는 **Ubuntu 로그인 비밀번호**다. PAT를 입력하는 곳이 아니다. 입력해도 글자나 별표가 나타나지 않는 것은 정상이다.

다음은 Git에 포함된 저장 도구 소스를 개인 폴더로 복사해 실행 파일로 만드는 과정이다. 어느 폴더에서 실행해도 된다.

```bash
mkdir -p ~/.local/share/git-credential-libsecret
cp /usr/share/doc/git/contrib/credential/libsecret/Makefile ~/.local/share/git-credential-libsecret/
cp /usr/share/doc/git/contrib/credential/libsecret/git-credential-libsecret.c ~/.local/share/git-credential-libsecret/
make -C ~/.local/share/git-credential-libsecret
```

파일을 찾을 수 없거나 `make`가 오류로 끝나면 다음 설정을 진행하지 말고 오류를 확인한다. Ubuntu 패키지 구성에 따라 소스가 다를 수 있다. [Git 공식 libsecret 소스](https://github.com/git/git/tree/master/contrib/credential/libsecret)와 패키지 설치 상태를 담당자와 확인한다.

다시 `patrol` 폴더의 터미널에서 실행한다.

```bash
git config --local --replace-all credential.https://github.com.helper ""
git config --local --add credential.https://github.com.helper "$HOME/.local/share/git-credential-libsecret/git-credential-libsecret"
git config --local credential.https://github.com.useHttpPath true
```

첫 줄은 이 저장소에서 이전 GitHub 인증 도구 대신 새 도구를 사용하도록 목록을 초기화한다. 기존에 저장된 비밀번호 자체를 지우는 명령은 아니다. 마지막 줄은 저장소 경로까지 구분하여 토큰을 기억하게 한다.

인증할 때 보관함 잠금 해제 창이 나오면 Ubuntu 로그인 비밀번호를 입력한다. ‘암호 및 키(Passwords and Keys)’ 앱에서 로그인 보관함을 확인할 수 있다. **보관함 비밀번호를 빈 값으로 바꾸지는 않는다.**

### macOS

macOS에서는 기본 키체인 저장 도구를 사용한다. `patrol` 폴더 안에서 실행한다.

```bash
git config --local --replace-all credential.https://github.com.helper ""
git config --local --add credential.https://github.com.helper osxkeychain
git config --local credential.https://github.com.useHttpPath true
```

키체인 접근 허용 창이 나오면 Git이 저장한 인증을 사용하도록 허용한다. 이때 macOS 로그인 비밀번호를 물을 수 있다. Ubuntu 설정 명령과 섞어서 실행하지 않는다.

[Git 공식 저장 도구 설명](https://git-scm.com/doc/credential-helpers)에서 Linux의 libsecret과 macOS의 osxkeychain을 확인할 수 있다.

### 화면 없는 Ubuntu 서버라면

데스크톱 비밀번호 보관함을 사용할 수 없는 환경에서는 **메모리에만 잠시 저장**하는 방법을 사용할 수 있다. 영구 저장이 아니며, 재부팅하거나 8시간이 지나면 다시 PAT를 입력해야 한다.

```bash
git config --local --replace-all credential.https://github.com.helper ""
git config --local --add credential.https://github.com.helper 'cache --timeout=28800'
git config --local credential.https://github.com.useHttpPath true
```

데스크톱 설정이 정상 동작하면 이 명령은 실행하지 않는다. [Git 자격 증명 저장 설명](https://git-scm.com/book/en/v2/Git-Tools-Credential-Storage)

## 4. PAT를 딱 한 번 입력하기

`patrol` 폴더에서 아래 명령을 실행한다. 파일을 수정하거나 업로드하지 않고 GitHub에 접근되는지만 확인한다.

```bash
git ls-remote origin HEAD
```

다음과 같은 질문이 나오면 입력한다.

```text
Username for 'https://github.com': 본인의 GitHub 로그인 아이디
Password for 'https://...': 1단계에서 복사한 PAT
```

위 상자는 명령어가 아니라 화면 예시다. `Username`에는 표시 이름이나 이메일 대신 로그인 아이디를 입력한다. 예를 들어 통합 관리자는 `jonnykoh2008-ship-it`이다. **Password에는 GitHub 계정 비밀번호가 아닌 PAT를 붙여 넣는다.**

Ubuntu 터미널에서는 `Ctrl + Shift + V`, macOS에서는 `Command + V`로 붙여 넣는다. 글자가 보이지 않아도 한 번 붙여 넣고 Enter를 누른다. 토큰을 여러 번 중복으로 붙여 넣지 않는다.

성공하면 긴 영문·숫자와 `HEAD`가 표시된다. 이 프로젝트에는 이미 커밋이 있으므로 결과가 나온다. 인증 질문이 없고 성공했다면 이미 유효한 인증이 저장되어 있을 수 있다.

## 5. 정말 기억하는지 확인하기

새 터미널을 열고 `patrol` 폴더로 이동한 다음 같은 명령을 다시 실행한다.

```bash
git ls-remote origin HEAD
```

추가 입력 없이 결과가 나오면 설정이 완료된 것이다. 이후 `git pull`과 `git push`도 저장된 PAT를 사용한다. 단, 키링이 잠겼거나 PAT가 만료·취소되면 다시 인증해야 한다. 브랜치 보호나 리뷰 승인은 이 설정으로 생략되지 않는다.

## 6. 막혔을 때 확인할 것

| 화면 또는 상황 | 뜻과 해결 방법 |
| --- | --- |
| `Authentication failed` | PAT가 틀렸거나 만료됐을 수 있다. GitHub 계정 비밀번호를 넣지 않았는지 확인한다. |
| `Repository not found` 또는 `403` | 주소, 협업 초대 수락, 토큰 권한, 로그인 계정을 확인한다. |
| 계속 Username·Password를 물음 | 저장 도구 설치 성공 여부와 키링 잠금 상태를 확인한다. |
| `workflow` 권한이 없다고 나옴 | `.github/workflows/` 수정 권한이 부족하다. 해당 작업 담당자만 권한을 추가한다. |
| `could not read Username` | 입력을 받을 수 없는 실행 환경이다. 자동화 창 대신 직접 터미널에서 인증한다. |
| `sudo`가 비밀번호를 물음 | GitHub 문제가 아니다. OS 로그인 비밀번호를 입력한다. |
| 로그인을 했는데 커밋 작성자 설정 오류가 남 | 로그인과 작성자 표시는 별개다. 본인의 `user.name`·`user.email`을 설정한다. |

PAT를 잘못 저장했거나 새 토큰으로 교체할 때는 먼저 새 PAT를 준비한다. 아래 코드는 **이 프로젝트의 GitHub 인증 저장 항목을 제거**하여 다음 접속에서 다시 입력하게 한다.

```bash
printf 'protocol=https\nhost=github.com\npath=suuuhululu/patrol.git\n\n' | git credential reject
git ls-remote origin HEAD
```

인증은 성공하지만 **쓰기 권한**이 있는지도 확인해야 한다. 이를 시험하려고 `main`에 임의 커밋을 만들지 말고, 실제 작업 브랜치의 정상 푸시 과정에서 확인한다.

## 7. 꼭 기억할 세 가지

1. PAT는 비밀번호처럼 다룬다. 채팅, README, 소스 코드, 스크린샷에 넣지 않는다.
2. `https://토큰@github.com/...`처럼 주소에 넣거나 `credential.helper store`로 일반 텍스트 파일에 저장하지 않는다.
3. 토큰을 다른 사람에게 보여 줬다면 GitHub의 토큰 설정에서 해당 토큰을 삭제하고 새로 만든다.

## 관련 문서

- [메인 문서의 Git 협업 가이드](../README.md#git-협업-가이드)
- [버전 관리](version-control.md)
- [PR 가이드](pull-request-guide.md)
- [브랜치 네이밍](branch-naming.md)
- [브랜치 사용](branch-guide.md)
