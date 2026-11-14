"""사용법:
  python3 -m sagak check   <추출.json | ->   검증만 하고 정리된 결과 출력 (Notion에 쓰지 않음)
  python3 -m sagak record  <추출.json | ->   검증 후 Notion에 기록하고 결과 JSON 출력
  python3 -m sagak resolve <상담 링크> same [--customer <고객 링크>] [--event <이벤트 링크>] [--by <확인자>]
  python3 -m sagak resolve <상담 링크> separate [--by <확인자>]
                                           '고객 연결 필요' 상담을 같은 고객/별도 고객으로 연결
  python3 -m sagak transcribe <녹음 파일>     녹음을 구간 시간이 있는 전사로 (lines: "[mm:ss] 화자: 내용")
  python3 -m sagak history <연락처>         그 고객의 이벤트·이전 상담 전체 (기록 전 확인용, Notion에 쓰지 않음)
  python3 -m sagak sweep [--dry-run] [--test] 모든 이벤트를 점검 규칙으로 정리 (기록 때 자동 실행, --test는 테스트 건만)
  python3 -m sagak product-map <상품명|안내 이름> <네이버 지도 링크>
                                           상품의 장소 링크를 노션 '상품'에 넣고 그 상품의 진행 중 이벤트에도 달기
  python3 -m sagak recheck-maps [--dry-run]  모든 이벤트 지도 링크를 네이버로 다시 확인 (확인 안 된 자동 링크는 지움)
  python3 -m sagak cleanup-test [--dry-run]  [테스트] 고객·이벤트·상담을 한꺼번에 휴지통으로
  python3 -m sagak demo-reset [--dry-run]    공개 데모: 리뷰어(상담자 '리뷰어 #…')가 남긴 상담과 그것만으로 생긴 이벤트·고객을 휴지통으로
  python3 -m sagak demo                      키 없이 체험: 가상 상담 6건을 봇과 같은 코드로 처리해 답장·기록을 보여 줌
  python3 -m sagak setup-notion --env <.env> [--dry-run]
                                           그 .env의 노션 키로 고객·이벤트(의뢰)·상담 이력·상품 DB를 찾아 ID 채우기
  python3 -m sagak ping                      Notion 키와 DB 접근 확인
  python3 -m sagak products                  업체 설정의 브랜드·상품명·고객 안내 이름 보기
  python3 -m sagak announce [--to admin|others] [--dry-run] [--env <.env 경로>] [--stdin]
                                           agent/CHANGES.md 새 안내를 텔레그램으로 보내고 [/new] 버튼 띄우기 (개발자 PC에서)
                                           --stdin: 편집한 안내를 표준입력으로 받아 보냄
  python3 -m sagak notify [--to others|admin|all] [--dry-run] < 문구.txt
                                           요청·공지를 그대로 보내기 (머리말·버튼 없음, 변경 안내 기록과 무관)
  python3 -m sagak console [--port 8765]     개발자 PC에서 안내 보내기 화면 띄우기 (미리 보기·편집·보내기)

종료 코드: 0 성공, 2 입력 문제(다시 요청할 것), 1 그 밖의 오류
"""
from __future__ import annotations

import json
import re
import sys

from . import pending
from .announce import AnnounceError, announce
from .notion import NotionError, NotionStore
from .record import InputError, build_record
from .sync import apply, plan, resolve
from .transcribe import TranscribeError, transcribe


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


def _use_places(store) -> None:
    """노션 '상품' DB를 못 읽어도 기록은 계속한다(업체 설정 파일 값으로)."""
    from . import business
    try:
        business.use_places(store.product_places())
    except NotionError:
        pass


def _sweep(store, record: dict) -> dict:
    """기록 뒤 전체 이벤트 점검. 테스트 기록이면 테스트 이벤트만, 아니면 테스트 제외 (D44).
    실패해도 기록 결과는 그대로 돌려준다."""
    from . import sweep
    from .normalize import is_test
    import os
    cust = record["customer"]
    if os.environ.get("SAGAK_DEMO"):  # 공개 데모: 가상 번호뿐이라 테스트 구분 없이 전부 점검
        scope = None
    else:
        scope = "test" if is_test(cust.get("name"), cust.get("phone")) else "real"
    try:
        return sweep.run(store, scope=scope)
    except NotionError as e:
        return {"error": str(e), "changes": [], "warnings": []}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else None
    if cmd not in ("check", "record", "resolve", "transcribe", "ping", "announce", "console", "products",
                   "history", "sweep", "cleanup-test", "recheck-maps", "notify", "product-map", "demo", "setup-notion", "demo-reset") or (
            cmd not in ("demo", "setup-notion", "demo-reset", "ping", "announce", "console", "products", "sweep", "cleanup-test", "recheck-maps", "notify")
            and len(argv) < 2):
        print(__doc__)
        return 1
    try:
        if cmd == "setup-notion":
            from .setup_notion import run as setup_run
            env = _option(argv, "--env")
            if not env:
                raise InputError("USAGE", "setup-notion --env <.env 경로>")
            out = setup_run(env, dry_run="--dry-run" in argv)
            _print({"ok": not out["problems"], **out})
            return 0 if not out["problems"] else 2
        if cmd == "demo":
            from .demo import run as demo_run
            demo_run()
            return 0
        if cmd == "ping":
            _print({"ok": True, "databases": NotionStore.from_env().ping()})
            return 0
        if cmd == "products":
            from . import business
            data = business.load()
            groups = {}
            for g in data["groups"].values():
                groups[g["name"]] = g["choices"]
            _print({"ok": True, "brands": data["brands"], "products": data["guide"],  # 상품명: [고객 안내 이름]
                    "groups": groups, "channels": list(data["channels"].values())})
            return 0
        if cmd == "console":
            from .console import serve
            serve(port=int(_option(argv, "--port") or 8765), env_path=_option(argv, "--env"))
            return 0
        if cmd == "announce":
            text = sys.stdin.read() if "--stdin" in argv else None
            _print({"ok": True, **announce(dry_run="--dry-run" in argv, env_path=_option(argv, "--env"), text=text,
                                             to=_option(argv, "--to") or "all")})
            return 0
        if cmd == "notify":
            from .announce import notify
            _print({"ok": True, **notify(sys.stdin.read(), to=_option(argv, "--to") or "others",
                                         dry_run="--dry-run" in argv, env_path=_option(argv, "--env"))})
            return 0
        if cmd == "transcribe":
            from .transcribe import save_result
            result = transcribe(argv[1])
            _print({"ok": True, **result, **save_result(result, argv[1])})
            return 0
        if cmd == "sweep":
            from . import sweep
            _print({"ok": True, **sweep.run(NotionStore.from_env(), dry_run="--dry-run" in argv,
                                            scope="test" if "--test" in argv else "real")})
            return 0
        if cmd == "recheck-maps":
            from . import naver
            store = NotionStore.from_env()
            _use_places(store)
            _print({"ok": True, "dry_run": "--dry-run" in argv,
                    "events": naver.recheck(store, dry_run="--dry-run" in argv)})
            return 0
        if cmd == "product-map":
            from . import business, naver
            store = NotionStore.from_env()
            places = store.product_places()
            name = argv[1] if argv[1] in places else business.product_of(argv[1])
            if not name:
                raise InputError("UNKNOWN_PRODUCT", "어느 상품인지 알 수 없어요: " + argv[1])
            if len(argv) < 3:
                raise InputError("NO_LINK", "네이버 지도 링크가 없어요.")
            out = naver.apply_product_link(store, name, argv[2])
            if not out["ok"]:
                raise InputError(out["error"], out["message"])
            _print(out)
            return 0
        if cmd == "demo-reset":
            store = NotionStore.from_env()
            found = store.reviewer_pages()
            dry = "--dry-run" in argv
            if not dry:
                for kind in ("consultations", "events", "customers"):
                    for pid in found[kind]:
                        store.trash(pid)
                        if kind == "consultations":
                            pending.delete(pid)
            _print({"ok": True, "dry_run": dry, **{k: list(v.values()) for k, v in found.items()}})
            return 0
        if cmd == "cleanup-test":
            store = NotionStore.from_env()
            found = store.test_pages()
            dry = "--dry-run" in argv
            if not dry:
                for kind in ("consultations", "events", "customers"):
                    for pid in found[kind]:
                        store.trash(pid)
                        if kind == "consultations":
                            pending.delete(pid)
            _print({"ok": True, "dry_run": dry, **{k: list(v.values()) for k, v in found.items()}})
            return 0
        if cmd == "history":
            from .normalize import normalize_phone
            phone = normalize_phone(argv[1])
            if not phone:
                raise InputError("BAD_PHONE", "연락처를 알아볼 수 없습니다.")
            _print({"ok": True, "customers": NotionStore.from_env().history(phone)})
            return 0
        if cmd == "resolve":
            _print({"ok": True, **_resolve(argv[1:])})
            return 0
        store = None
        if cmd == "record":  # 노션 '상품' DB의 지도 링크·장소를 먼저 읽는다 (D54)
            store = NotionStore.from_env()
            _use_places(store)
        record = build_record(_load(argv[1]))
        if cmd == "check":
            _print({"ok": True, "record": record})
            return 0
        from . import clips
        clip_info = clips.attach(record, store)
        from . import naver
        map_status = naver.verify(record)
        p = plan(record, store)
        out = apply(record, p, store)
        if out["review"] == "고객 연결 필요":
            pending.save(out["consultation"]["id"], record, p["candidates"])
            out["pending"] = True
        out["sweep"] = _sweep(store, record)
        out["map_link"] = map_status
        if clip_info.get("clips") or clip_info.get("error"):
            out["audio_clips"] = clip_info
        _print({"ok": True, **out})
        return 0
    except TranscribeError as e:
        _print({"ok": False, "error": e.code, "message": e.message})
        return 1 if e.code in ("STT_FAILED", "NO_KEY") else 2
    except InputError as e:
        _print({"ok": False, "error": e.code, "message": e.message})
        return 2
    except (NotionError, AnnounceError, OSError, ValueError) as e:
        _print({"ok": False, "error": "FAILED", "message": str(e)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
