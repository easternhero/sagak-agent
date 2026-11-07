"""공개 레포 검사: 금지어(.sagak-denylist, 커밋 안 함)가 커밋 내용이나 메시지에 있으면 막는다.

    python3 scripts/check_public.py staged            # 스테이징된 변경의 추가 줄 검사 (pre-commit)
    python3 scripts/check_public.py message <파일>     # 커밋 메시지 검사 (commit-msg)
    python3 scripts/check_public.py tree               # 지금 레포 파일 전체 검사
금지어 파일 위치: SAGAK_DENYLIST 또는 <레포>/.sagak-denylist. 한 줄에 하나, #으로 시작하면 주석.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def denylist() -> list:
    path = os.environ.get("SAGAK_DENYLIST") or os.path.join(ROOT, ".sagak-denylist")
    try:
        with open(path, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]
    except OSError:
        return []


def find(text: str, words: list) -> list:
    low = text.lower()
    return sorted({w for w in words if w.lower() in low})


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def staged_text() -> str:
    diff = _git("diff", "--cached", "--no-color", "-U0", "--", ".", ":(exclude).sagak-denylist")
    return "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))


def tree_hits(words: list) -> list:
    hits = []
    for path in _git("ls-files").splitlines():
        try:
            with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                found = find(f.read(), words)
        except (OSError, UnicodeDecodeError):
            continue
        if found:
            hits.append((path, found))
    return hits


def main(argv: list) -> int:
    words = denylist()
    if not words:
        print("check_public: 금지어 목록(.sagak-denylist)이 없어 검사하지 않습니다.", file=sys.stderr)
        return 0
    mode = argv[0] if argv else "staged"
    if mode == "tree":
        hits = tree_hits(words)
        for path, found in hits:
            print("{}: {}".format(path, ", ".join(found)))
        return 1 if hits else 0
    if mode == "message":
        with open(argv[1], encoding="utf-8") as f:
            found = find(f.read(), words)
        where = "커밋 메시지"
    else:
        found = find(staged_text(), words)
        where = "커밋할 내용"
    if found:
        print("공개 레포 검사: {}에 남기면 안 되는 말이 있습니다 → {}".format(where, ", ".join(found)), file=sys.stderr)
        print("가상 값으로 바꾼 뒤 다시 커밋하세요 (CLAUDE.md '공개 레포 규칙').", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
