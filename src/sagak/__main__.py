"""사용법:
  python3 -m sagak check  <추출.json | ->   검증만 하고 정리된 결과 출력 (Notion에 쓰지 않음)
  python3 -m sagak record <추출.json | ->   검증 후 Notion에 기록하고 결과 JSON 출력
  python3 -m sagak ping                     Notion 키와 DB 접근 확인

종료 코드: 0 성공, 2 입력 문제(다시 요청할 것), 1 그 밖의 오류
"""
from __future__ import annotations

import json
import sys

from .notion import NotionError, NotionStore
from .record import InputError, build_record
from .sync import apply, plan


def _load(arg: str) -> dict:
    if arg == "-":
        return json.load(sys.stdin)
    with open(arg, encoding="utf-8") as f:
        return json.load(f)


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("check", "record", "ping") or (argv[0] != "ping" and len(argv) < 2):
        print(__doc__)
        return 1
    try:
        if argv[0] == "ping":
            _print({"ok": True, "databases": NotionStore.from_env().ping()})
            return 0
        record = build_record(_load(argv[1]))
        if argv[0] == "check":
            _print({"ok": True, "record": record})
            return 0
        store = NotionStore.from_env()
        _print({"ok": True, **apply(record, plan(record, store), store)})
        return 0
    except InputError as e:
        _print({"ok": False, "error": e.code, "message": e.message})
        return 2
    except (NotionError, OSError, ValueError) as e:
        _print({"ok": False, "error": "FAILED", "message": str(e)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
