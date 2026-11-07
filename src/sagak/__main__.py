"""사용법:
  python3 -m sagak check   <추출.json | ->   검증만 하고 정리된 결과 출력 (Notion에 쓰지 않음)
  python3 -m sagak record  <추출.json | ->   검증 후 Notion에 기록하고 결과 JSON 출력
  python3 -m sagak resolve <상담 링크> same [--customer <고객 링크>] [--event <이벤트 링크>] [--by <확인자>]
  python3 -m sagak resolve <상담 링크> separate [--by <확인자>]
                                           '고객 확인 필요' 상담을 같은 고객/별도 고객으로 연결
  python3 -m sagak ping                      Notion 키와 DB 접근 확인

종료 코드: 0 성공, 2 입력 문제(다시 요청할 것), 1 그 밖의 오류
"""
from __future__ import annotations

import json
import re
import sys

from . import pending
from .notion import NotionError, NotionStore
from .record import InputError, build_record
from .sync import apply, plan, resolve


def _load(arg: str) -> dict:
    if arg == "-":
        return json.load(sys.stdin)
    with open(arg, encoding="utf-8") as f:
        return json.load(f)


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def page_id(text: str) -> str:
    """Notion 링크나 ID에서 32자리 페이지 ID를 꺼낸다."""
    m = re.search(r"([0-9a-f]{32})(?:\?|$)", text.replace("-", "")) or re.search(r"([0-9a-f]{32})", text.replace("-", ""))
    if not m:
        raise InputError("BAD_LINK", "Notion 링크에서 페이지 ID를 찾지 못했습니다: " + text)
    return m.group(1)


def _option(args: list, name: str):
    if name in args:
        i = args.index(name)
        return args[i + 1] if i + 1 < len(args) else None
    return None


def _resolve(args: list) -> dict:
    if len(args) < 2:
        raise InputError("USAGE", "resolve <상담 링크> same|separate")
    cid, decision = page_id(args[0]), args[1]
    saved = pending.load(cid)
    if not saved:
        raise InputError("NO_PENDING", "이 상담의 보류 정보가 없습니다. 이미 처리됐거나 이전 버전에서 기록된 상담입니다. Notion에서 직접 연결해 주세요.")
    customer = _option(args, "--customer")
    event = _option(args, "--event")
    customer_id = page_id(customer) if customer else None
    if decision == "same" and not customer_id:
        cands = [c for c in saved["candidates"] if c.get("type") == "고객"]
        if len(cands) != 1:
            raise InputError("NEED_CUSTOMER", "연결할 고객을 골라 주세요: " + ", ".join(c.get("title") or "" for c in cands))
        customer_id = cands[0]["id"]
    store = NotionStore.from_env()
    out = resolve(saved["record"], cid, decision, store, customer_id=customer_id,
                  event_id=page_id(event) if event else None, by=_option(args, "--by"))
    pending.delete(cid)
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else None
    if cmd not in ("check", "record", "resolve", "ping") or (cmd != "ping" and len(argv) < 2):
        print(__doc__)
        return 1
    try:
        if cmd == "ping":
            _print({"ok": True, "databases": NotionStore.from_env().ping()})
            return 0
        if cmd == "resolve":
            _print({"ok": True, **_resolve(argv[1:])})
            return 0
        record = build_record(_load(argv[1]))
        if cmd == "check":
            _print({"ok": True, "record": record})
            return 0
        store = NotionStore.from_env()
        p = plan(record, store)
        out = apply(record, p, store)
        if out["review"] == "고객 확인 필요":
            pending.save(out["consultation"]["id"], record, p["candidates"])
            out["pending"] = True
        _print({"ok": True, **out})
        return 0
    except InputError as e:
        _print({"ok": False, "error": e.code, "message": e.message})
        return 2
    except (NotionError, OSError, ValueError) as e:
        _print({"ok": False, "error": "FAILED", "message": str(e)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
