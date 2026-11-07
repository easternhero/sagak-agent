#!/bin/sh
# 커밋 전 공개 레포 검사 설치 (한 번만). 금지어 목록은 레포 루트의 .sagak-denylist (커밋 안 함).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS="$(git -C "$ROOT" rev-parse --git-path hooks)"
case "$HOOKS" in /*) ;; *) HOOKS="$ROOT/$HOOKS" ;; esac
mkdir -p "$HOOKS"
printf '#!/bin/sh\nexec python3 "$(git rev-parse --show-toplevel)/scripts/check_public.py" staged\n' > "$HOOKS/pre-commit"
printf '#!/bin/sh\nexec python3 "$(git rev-parse --show-toplevel)/scripts/check_public.py" message "$1"\n' > "$HOOKS/commit-msg"
chmod +x "$HOOKS/pre-commit" "$HOOKS/commit-msg"
echo "설치됨: $HOOKS/pre-commit, commit-msg"
