# 한 작업 트리를 여러 에이전트가 쓸 때의 규칙

작성일: 2026-09-08 · 계기: `tests/` 15개 파일 약 2,900줄이 한 커밋에서 조용히 사라진 사고

## 1. 왜 이 문서가 있나

이 저장소는 Claude Code 세션과 Codex(GPT) 세션이 **같은 디렉터리 `/home/mu-01/patrol`** 에서 동시에 작업한다. 브랜치가 같든 다르든 체크아웃이 하나이므로 git 이 서로를 보호해 주지 않는다.

worktree 를 분리하는 방법도 있으나 **쓰지 않기로 했다.** 두 에이전트가 같은 브랜치에서 같은 목표를 향해 작업하는 동안에는 작업이 선형으로 쌓인다. 분리하면 매 교대마다 병합이 생기고, 그 병합이야말로 이 사고가 일으킬 뻔한 종류의 손실을 만든다. 분리는 목표가 갈릴 때 다시 검토한다.

대신 아래 세 가지로 막는다.

## 2. 규칙

### 2.1 필수 경로 전멸 방지 (자동)

[`scripts/check_tracked_paths.sh`](../../scripts/check_tracked_paths.sh) 가 `tests`, `src/patrol_amr/patrol_amr`, `src/patrol_interfaces/msg`, `docs` 에 추적 파일이 하나라도 있는지 본다. 하나도 없으면 커밋이 막힌다.

파일 단위가 아니라 **디렉터리가 통째로 비었는가**만 본다. 개별 파일 이동·삭제를 막으려는 것이 아니라 조용한 전멸을 막으려는 것이다.

설치는 사람마다 한 번이다. `.git/hooks` 는 git 이 공유하지 않으므로 추적되는 디렉터리를 가리킨다.

```bash
git config core.hooksPath .githooks
```

새 컴퓨터에서 clone 한 뒤에도 이 한 줄을 실행해야 훅이 산다.

### 2.2 시험 파일은 관심사별로 나눈다

`unittest` discovery 가 `test_*.py` 를 전부 줍기 때문에 파일을 나눠도 실행은 같다. 나누면 두 에이전트가 서로 다른 파일을 건드리게 되어 덮어쓰기와 병합 충돌이 줄어든다.

```
test_robot_status_state.py            상태 축·pose
test_robot_status_state_odometry.py   odometry·motion_stopped
```

한 파일에 계속 덧붙이는 대신, 새 기능은 새 파일로 시작한다.

### 2.3 지운 것은 다시 쓰지 말고 되살린다

이번 사고에서 잃은 2,900줄은 한 줄로 돌아왔다. 커밋 이력에 남아 있기 때문이다.

```bash
git log --diff-filter=D -- tests/        # 언제 지워졌는지
git checkout <그 직전 커밋> -- tests/     # 되살리기
```

다시 작성하면 미묘하게 달라진 판정이 섞여 들어간다. **되살린 뒤 실패하는 시험은 복구가 틀린 것이 아니라, 그 사이 검증 없이 바뀐 소스가 드러난 것이다.**

## 3. 사고 경위 (2026-09-08)

| 커밋 | 내용 |
|---|---|
| `a271bf3` | 14단계. `test_robot_status_state.py` 341줄, odometry 시험 15건 포함 |
| `db4898c` | 17단계. 342줄, 아직 온전 |
| `683f240` | **`tests/` 15개 파일 삭제.** 약 2,900줄 |
| — | 디스크에는 14단계 이전 203줄 버전이 추적 없이 남음 |

시험이 계속 돌았기 때문에 아무도 알아채지 못했다. `git ls-files tests/` 가 0 이었고, clone 한 사람에게는 시험이 하나도 없는 상태였다.

복구 시 `git checkout db4898c -- tests/` 는 그 시점에 존재한 14개만 되살리므로, 이후 추가된 35개 시험 파일은 건드리지 않는다. 그 사이 새로 넣은 검사(예: Q-02 발행 주기)는 복구본에 다시 얹어야 한다.

## 4. 패키지 분리 (2026-09-08)

위 규칙만으로는 부족했다. 진짜 문제는 `.gitignore` 한 줄이 아니라 **한 디렉터리의 파일 48개를 두 사람이 동시에 고치는 것**이었고, 손실이 난 순간은 성현님 코드를 이 트리로 끌어온 커밋(`3c79ef7`)이었다.

git worktree 로 나누는 방법은 쓰지 않았다. ROS 워크스페이스에서는 `install/` 까지 갈려서 두 번 빌드하고 overlay 두 개를 source 해야 하며, 노드를 같이 띄울 수 없다.

대신 **ROS 패키지를 소유자 경계로 나눴다.** 한 워크스페이스에서 같이 빌드·실행되면서 파일은 겹치지 않는다.

| 패키지 | 소유 | 내용 |
|---|---|---|
| `patrol_amr` | 박성현 | mission·nav2·docking·report·scenarios (41개) |
| `patrol_amr_safety` | 조정묵 | battery_monitor, drive_token_guard, estop_guard, motion_guard, local_safety_supervisor, robot_status_state, status_reporter, command_gateway |

경계는 인수인계 1절의 "AMR Python 파일 7개, ROS 노드 3개" 범위 그대로다(+ 19단계 `command_gateway`).

### 왜 이 경계가 성립하나

옮기기 전에 교차 import 를 확인했다.

- 조정묵 모듈 → 박성현 모듈: **0건**
- 박성현 모듈 → 조정묵 모듈: **2건** (`mission_drive_token.py` → `drive_token_guard`, `status_mission_bridge.py` → `robot_status_state`)

두 줄만 `patrol_amr_safety` 로 바꾸면 됐다. 나머지 46개는 손대지 않았다. 경계가 이미 코드에 있었고 디렉터리만 그것을 반영하지 않고 있었다.

### 함께 옮긴 것

- 시험 8개의 `sys.path`·모듈 경로
- entry point 4개 → `patrol_amr_safety/setup.py`. `patrol_amr` 에는 `mission_supervisor` 만 남는다
- `launch/amr_safety_status.launch.py` 의 `package=` 3곳
- 스모크 2개의 `ros2 run` 대상

### 옮긴 뒤 반드시 할 것

구 install 을 지우지 않으면 `ros2 run patrol_amr status_reporter` 가 **옮기기 전 사본**을 실행한다. 빌드는 성공하고 노드도 뜨기 때문에 조용하다.

```bash
rm -rf build/patrol_amr install/patrol_amr
colcon build --packages-select patrol_amr patrol_amr_safety
ros2 pkg executables patrol_amr        # mission_supervisor 하나만 나와야 한다
```

### 성현님 쪽에 필요한 것

`main` 브랜치에도 같은 분리가 가도록 병합할 때, 위 2건의 import 를 함께 반영해야 한다. 그 전에는 `main` 에서 `from patrol_amr import drive_token_guard` 가 계속 동작하므로 충돌이 나지 않고 조용히 갈린다.
