"""고객·이벤트 연결 규칙과 기록 순서. 저장소(Notion 등)와 무관한 순수 로직.

규칙 (docs/notion-schema.md 연결 규칙):
1. 연락처와 이름이 모두 같은 고객이 있으면 연결. 연락처만 같고 이름이 다르면 연결하지 않고 사람 확인.
2. 연결된 고객의 진행 중 이벤트가 하나면 다음 차수로 추가, 없으면 새 이벤트, 둘 이상이면 사람 확인.
3. 기존 값은 지우거나 덮어쓰지 않는다. 비어 있으면 채우고, 다르면 차이로 표시만 한다.
"""
from __future__ import annotations

from typing import Optional

from .normalize import normalize_name

OPEN_STATUSES = ("상담진행중", "추후연락", "이벤트진행예정")
NEW_EVENT_STATUS = "상담진행중"

# 기록 키 → 사람이 읽는 이름 (차이 표시용)
CUSTOMER_LABELS = {"email": "전자메일", "company": "회사·단체명", "customer_type": "고객 구분"}
EVENT_LABELS = {
    "theme": "이벤트 테마",
    "product": "희망 이벤트",
    "venue": "희망 장소",
    "desired_at": "희망 일시",
    "budget": "예상 금액",
}
# 서술형 항목은 비어 있을 때만 채우고, 다르더라도 차이로 표시하지 않는다 (상담 내역에 이미 남음)
EVENT_FILL_ONLY = {"desired_at_text": "희망 일시(원문)", "request": "문의 및 신청사항"}


def merge(existing: dict, new: dict, labels: dict, target: str):
    """비어 있는 기존 값만 채운다. 다른 값은 차이 목록으로 돌려준다."""
    to_set, diffs = {}, []
    for key, label in labels.items():
        value = new.get(key)
        if value is None:
            continue
        old = existing.get(key)
        if old in (None, ""):
            to_set[key] = value
        elif str(old) != str(value):
            diffs.append({"target": target, "field": label, "existing": old, "new": value})
    return to_set, diffs


def plan(record: dict, store) -> dict:
    cust, ev, co = record["customer"], record["event"], record["consultation"]
    needs_check = list(co["needs_check"])
    result = {"customer": None, "event": None, "diffs": [], "candidates": [], "review": "확인 대기"}

    def need_person(label: str, candidates: list) -> None:
        result["review"] = "고객 확인 필요"
        result["candidates"].extend(candidates)
        if label not in needs_check:
            needs_check.append(label)

    found = store.find_customers(cust["phone"])
    same = [c for c in found if normalize_name(c.get("name")) == normalize_name(cust["name"])]

    if len(same) == 1:
        to_set, diffs = merge(same[0], cust, CUSTOMER_LABELS, "고객")
        result["customer"] = {"action": "link", "id": same[0]["id"], "url": same[0].get("url"), "set": to_set}
        result["diffs"].extend(diffs)
    elif found:
        # 연락처는 같은데 이름이 다르거나, 같은 고객이 여러 명 → 사람이 판단
        need_person("고객 연결", [{"type": "고객", "title": c.get("name"), "url": c.get("url")} for c in found])
    else:
        result["customer"] = {"action": "create", "set": dict(cust)}

    round_no = 1
    if result["customer"] and result["customer"]["action"] == "link":
        events = store.open_events(result["customer"]["id"])
        if len(events) == 1:
            e = events[0]
            to_set, diffs = merge(e, ev, EVENT_LABELS, "이벤트")
            fill, _ = merge(e, ev, EVENT_FILL_ONLY, "이벤트")
            to_set.update(fill)
            result["event"] = {"action": "link", "id": e["id"], "url": e.get("url"), "set": to_set}
            result["diffs"].extend(diffs)
            round_no = int(e.get("consult_count") or 0) + 1
        elif len(events) > 1:
            need_person("이벤트 연결", [{"type": "이벤트", "title": e.get("title"), "url": e.get("url")} for e in events])
        else:
            result["event"] = {"action": "create", "set": _new_event(ev, co)}
    elif result["customer"]:
        result["event"] = {"action": "create", "set": _new_event(ev, co)}

    if result["diffs"] and "기존 정보와 다름" not in needs_check:
        needs_check.append("기존 정보와 다름")

    result["consultation"] = {"round": round_no if result["event"] else None, "needs_check": needs_check}
    return result


def _new_event(ev: dict, co: dict) -> dict:
    fields = {k: v for k, v in ev.items() if v is not None}
    fields["status"] = NEW_EVENT_STATUS
    fields["requested_on"] = co["consulted_at"][:10]
    return fields


def event_title(name: str, ev: dict) -> str:
    when = ev.get("desired_at")
    when = "{}/{}".format(int(when[5:7]), int(when[8:10])) if when else (ev.get("desired_at_text") or "일정 미정")
    return "{} · {} · {}".format(name, ev.get("theme") or "테마 미정", when)


def consultation_title(name: str, consulted_at: str, round_no: Optional[int]) -> str:
    day = "{}/{}".format(consulted_at[5:7], consulted_at[8:10])
    tail = "{}차 상담".format(round_no) if round_no else "연결 확인 필요"
    return "{} {} · {}".format(day, name, tail)


def apply(record: dict, p: dict, store) -> dict:
    """plan 결과대로 저장소에 쓴다. 쓰는 순서: 고객 → 이벤트 → 상담 이력."""
    cust, co = record["customer"], record["consultation"]
    out = {"review": p["review"], "needs_check": p["consultation"]["needs_check"], "diffs": p["diffs"],
           "candidates": p["candidates"], "customer": None, "event": None}

    customer_id = None
    if p["customer"]:
        if p["customer"]["action"] == "create":
            ref = store.create_customer(p["customer"]["set"])
        else:
            ref = {"id": p["customer"]["id"], "url": p["customer"]["url"]}
            if p["customer"]["set"]:
                store.update_customer(ref["id"], p["customer"]["set"])
        customer_id = ref["id"]
        out["customer"] = {"action": p["customer"]["action"], "url": ref.get("url")}

    event_id = None
    if p["event"]:
        if p["event"]["action"] == "create":
            fields = dict(p["event"]["set"])
            fields["title"] = event_title(cust["name"], fields)
            ref = store.create_event(fields, customer_id)
        else:
            ref = {"id": p["event"]["id"], "url": p["event"]["url"]}
            if p["event"]["set"]:
                store.update_event(ref["id"], p["event"]["set"])
        event_id = ref["id"]
        out["event"] = {"action": p["event"]["action"], "url": ref.get("url")}

    round_no = p["consultation"]["round"]
    fields = dict(co)
    fields["needs_check"] = p["consultation"]["needs_check"]
    fields["round"] = round_no
    fields["review"] = p["review"]
    fields["title"] = consultation_title(cust["name"], co["consulted_at"], round_no)
    ref = store.create_consultation(fields, event_id, body_sections(record, p))
    out["consultation"] = {"url": ref.get("url"), "round": round_no, "title": fields["title"]}
    return out


def body_sections(record: dict, p: dict) -> list:
    """상담 이력 페이지 본문: [(제목, [줄, ...]), ...]"""
    sections = []
    if record["evidence"]:
        lines = []
        for e in record["evidence"]:
            time = " ({})".format(e["time"]) if e.get("time") else ""
            lines.append("{} — “{}”{}".format(e["field"] or "근거", e["quote"], time))
        sections.append(("근거", lines))
    if p["diffs"]:
        sections.append(("기존 정보와 다른 내용 (덮어쓰지 않음)", [
            "{} {}: 기존 “{}” / 이번 “{}”".format(d["target"], d["field"], d["existing"], d["new"]) for d in p["diffs"]]))
    if p["candidates"]:
        sections.append(("연결 후보 (사람 확인 필요)", [
            "{}: {} {}".format(c["type"], c.get("title") or "", c.get("url") or "").strip() for c in p["candidates"]]))
    if record["consultation"]["questions"]:
        sections.append(("고객에게 물어볼 것", record["consultation"]["questions"]))
    if record["transcript"]:
        sections.append(("전사 원문", record["transcript"].splitlines()))
    return sections
