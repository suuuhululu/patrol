#!/usr/bin/env bash
# 필수 경로가 git 추적에서 통째로 사라지는 것을 막는다.
#
# 2026-09-08 에 tests/ 15개 파일 약 2,900줄이 한 커밋에서 삭제됐다. 파일은
# 디스크에 남아 있어 시험이 계속 돌았고, git 에서만 사라진 것을 며칠 뒤에야
# 발견할 수 있는 상태였다. clone 한 사람에게는 시험이 하나도 없었다.
#
# 파일 단위가 아니라 "디렉터리가 통째로 비었는가"만 본다. 개별 파일 이동·
# 삭제를 막으려는 것이 아니라, 조용한 전멸을 막으려는 것이다.
set -euo pipefail

REQUIRED_PATHS=(
    "tests"
    "src/patrol_amr/patrol_amr"
    "src/patrol_interfaces/msg"
    "docs"
)

status=0
for path in "${REQUIRED_PATHS[@]}"; do
    # 원인을 직접 잡는다. 2026-09-08 사고는 .gitignore 에 '/tests' 한 줄이
    # 들어가서 생겼다. 추적 수가 0 이 되기 전에 이 단계에서 걸린다.
    # --no-index 가 필요하다. 그것 없이는 이미 index 에 있는 경로를 건너뛰어,
    # 규칙이 들어와도 다음 clone 전까지 조용하다.
    if ignored="$(git check-ignore --no-index -v "$path" 2>/dev/null)"; then
        echo "FAIL: '$path' 가 .gitignore 규칙에 걸립니다." >&2
        echo "      $ignored" >&2
        echo "      소스 디렉터리는 산출물이 아닙니다. 규칙을 지우거나 좁히세요." >&2
        status=1
        continue
    fi
    count="$(git ls-files -- "$path" | wc -l)"
    if [ "$count" -eq 0 ]; then
        echo "FAIL: '$path' 에 추적되는 파일이 하나도 없습니다." >&2
        echo "      디스크에 파일이 있어도 git 에서 사라진 상태입니다." >&2
        echo "      되살리려면: git log --diff-filter=D -- $path" >&2
        echo "                  git checkout <그 직전 커밋> -- $path" >&2
        status=1
    else
        printf 'ok: %-32s %s files tracked\n' "$path" "$count"
    fi
done

exit "$status"
