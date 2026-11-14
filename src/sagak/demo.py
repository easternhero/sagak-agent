"""키 없이 해 보는 체험: `python3 -m sagak demo`

가상 업체·가상 고객 상담 6건을 봇과 같은 코드로 처리하고, 봇 답장과 노션에 들어갈 기록을 화면에 보여 준다.
노션·텔레그램·OpenAI 키가 필요 없다(기록은 메모리에만). 대화에서 내용을 뽑는 단계(대화 모델)는
미리 뽑아 둔 결과(tests/fixtures/extractions)를 쓰고, 그 뒤의 검증·고객 연결·기록·점검은 실제 봇과 같다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(ROOT, "tests", "fixtures")


def _load(name: str) -> dict:
    with open(os.path.join(FIXTURES, "extractions", name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def _won(n) -> str:
    return "{:,}원".format(n) if isinstance(n, (int, float)) else "-"


def _sent(data: dict) -> list:
    lines = ["캡션: " + (data.get("caption") or "(없음)")]
    text = (data.get("transcript") or "").strip().splitlines()
    for t in text[:3]:
        lines.append(t)
    if len(text) > 3:
        lines.append("  … ({}줄 더)".format(len(text) - 3))
    return lines


def _reply(out: dict, record: dict) -> list:
    co = out["consultation"]
    if out["review"] == "고객 연결 필요":
        lines = ["⚠️ 같은 연락처의 다른 고객이 있어요. 같은 사람인가요? (답을 받기 전에는 연결하지 않아요)"]
        lines += ["   후보 — {}: {}".format(c["type"], c.get("title")) for c in out.get("candidates") or []]
    else:
        what = []
        what.append("새 고객" if out["customer"]["action"] == "create" else "기존 고객")
        what.append("새 이벤트" if out["event"]["action"] == "create" else "기존 이벤트")
        what.append("{}차 상담".format(co["round"]))
        lines = ["✅ 기록했어요: {} ({})".format(co["title"], ", ".join(what))]
    if out.get("needs_check"):
        lines.append("   확인 필요: " + ", ".join(out["needs_check"]))
    for d in out.get("diffs") or []:
        lines.append("   기존 정보와 다름 — {} {}: 기존 “{}” / 이번 “{}” (덮어쓰지 않음)".format(
            d["target"], d["field"], d["existing"], d["new"]))
    for q in record["consultation"]["questions"]:
        lines.append("   고객에게 물어볼 것: " + q)
    sw = out.get("sweep") or {}
    for c in sw.get("changes") or []:
        lines.append("   🔄 자동 점검 — {}: {}".format(c["title"], "; ".join(c["changes"])))
    for w in sw.get("warnings") or []:
        lines.append("   🔔 {}: {}".format(w["title"], w["warning"]))
    return lines


def _board(store) -> list:
    lines = ["", "━━ 노션에 들어간 기록 (메모리) ━━", "", "[고객]"]
    for c in store.customers.values():
        lines.append("  {} · {} · {}{}".format(c["name"], c["phone"], c.get("customer_type") or "-",
                                               " · " + c["company"] if c.get("company") else ""))
    lines.append("[이벤트]")
    for e in store.events.values():
        lines.append("  {} | 상태 {} | 희망 {} | 확정 {} | 결제 {} | 장소 {} | 예산 {}".format(
            e.get("title"), e.get("status"), e.get("desired_at") or "-", e.get("confirmed_at") or "-",
            e.get("payment_status") or "-", e.get("venue") or "-", _won(e.get("budget"))))
    lines.append("[상담 이력]")
    for c in store.consultations.values():
        lines.append("  {} | {} | 확인 필요: {}".format(
            c.get("title"), c.get("review"), ", ".join(c.get("needs_check") or []) or "-"))
    return lines


def run(echo=print) -> dict:
    os.environ.setdefault("SAGAK_BUSINESS_FILE", os.path.join(FIXTURES, "business.json"))
    os.environ.pop("SAGAK_DEMO", None)  # 키 없이 체험은 공개 데모 봇 규칙(가상 번호·리뷰어 표시)과 무관
    from .memstore import MemoryStore
    from .record import InputError, build_record
    from . import sweep
    from .sync import apply, plan, resolve

    store = MemoryStore()
    now = datetime.fromisoformat("2026-11-14T10:00:00+09:00")
    results = []

    def record_one(title: str, data: dict, note: str = ""):
        echo("")
        echo("━━ {} ━━".format(title))
        if note:
            echo(note)
        echo("직원이 봇에 보낸 것:")
        for line in _sent(data):
            echo("  " + line)
        echo("봇 답장:")
        try:
            record = build_record(data)
        except InputError as e:
            echo("  ✋ " + e.message + " 노션에는 아무것도 쓰지 않았어요.")
            results.append({"title": title, "refused": e.code})
            return None, None
        p = plan(record, store)
        out = apply(record, p, store)
        out["sweep"] = sweep.run(store, now=now)
        for line in _reply(out, record):
            echo("  " + line)
        results.append({"title": title, "review": out["review"]})
        return record, out

    echo("사각사각 체험 — 가상 업체·가상 고객, 키 없이 메모리에 기록합니다.")
    echo("(대화에서 내용을 뽑는 단계는 미리 뽑아 둔 결과를 쓰고, 그 뒤 검증·연결·기록·점검은 실제 봇과 같은 코드입니다.)")

    record_one("1/6 새 고객의 첫 상담 (녹음)", _load("s01"))
    record_one("2/6 같은 고객의 2차 상담 — 다음 차수로 잇고, 바뀐 장소는 덮어쓰지 않음", _load("s02"))

    d = _load("s02")
    d["caption"] = "김민지 / 010-1000-1111"
    rec, out = record_one("3/6 같은 연락처, 다른 이름 — 사람에게 확인", d)
    if out and out["review"] == "고객 연결 필요":
        cand = next(c for c in out["candidates"] if c["type"] == "고객")
        echo("  (직원 답: “같은 사람이에요” → 그때 연결)")
        done = resolve(rec, out["consultation"]["id"], "same", store, customer_id=cand["id"], by="직원")
        echo("  ✅ 연결했어요: 기존 고객 ‘{}’의 {}차 상담".format(cand.get("title"), done["consultation"]["round"]))

    record_one("4/6 정보가 빠진 상담 — 추측하지 않고 물어볼 것으로", _load("s04"))

    rec, out = record_one("5/6 기업 고객 상담 — 예약금이 들어오면 일정·상태 자동 정리", _load("s03"))
    if out:
        eid = next(i for i, e in store.events.items() if (e.get("title") or "").startswith("이지은"))
        store.events[eid]["payment_status"] = "예약금 입금"
        sw = sweep.run(store, now=now)
        echo("  (직원이 노션에서 결제 상태를 ‘예약금 입금’으로 바꾼 뒤, 다음 기록 때 자동 점검)")
        for c in sw["changes"]:
            echo("  🔄 자동 점검 — {}: {}".format(c["title"], "; ".join(c["changes"])))

    record_one("6/6 상담과 관계없는 녹음, 고객 정보 없음", _load("s05"))

    for line in _board(store):
        echo(line)
    echo("")
    echo("실제 봇에서는 이 내용이 노션 고객 보드에 들어가고, 업무와 상관없는 요청(날씨·검색 등)은 한 문장으로 거절합니다.")
    return {"results": results, "customers": len(store.customers), "events": len(store.events),
            "consultations": len(store.consultations)}
