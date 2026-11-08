"""고객·이벤트 연결 규칙과 기록 순서. 저장소(Notion 등)와 무관한 순수 로직.

규칙 (docs/notion-schema.md 연결 규칙):
1. 연락처와 이름이 모두 같은 고객이 있으면 연결. 연락처만 같고 이름이 다르면 연결하지 않고 사람 확인.
2. 연결된 고객의 진행 중 이벤트가 하나면 다음 차수로 추가, 없으면 새 이벤트, 둘 이상이면 사람 확인.
3. 기존 값은 지우거나 덮어쓰지 않는다. 비어 있으면 채우고, 다르면 차이로 표시만 한다.
"""
from __future__ import annotations

from typing import Optional

from .normalize import match_staff, normalize_name

OPEN_STATUSES = ("상담진행중", "추후연락", "이벤트진행예정")
NEW_EVENT_STATUS = "상담진행중"
BLACKLIST = "B 블랙리스트"
NEED_LINK = "고객 연결 필요"  # 같은 고객인지 사람이 골라야 하는 상담의 검토 상태

# 기록 키 → 사람이 읽는 이름 (차이 표시용)
CUSTOMER_LABELS = {"email": "전자메일", "company": "회사·단체명", "customer_type": "고객 구분"}
EVENT_LABELS = {
    "theme": "이벤트 테마",
    "product": "희망 이벤트",
    "venue": "희망 장소",
    "desired_at": "희망 일시",
    "budget": "고객 예산",
    "deposit": "예약금액",
    "confirmed_at": "확정 일시",
    "brand": "제휴",
}
# 서술형 항목은 비어 있을 때만 채우고, 다르더라도 차이로 표시하지 않는다 (상담 내역에 이미 남음)
EVENT_FILL_ONLY = {"desired_at_text": "희망 일시(원문)", "request": "문의 및 신청사항", "map_url": "지도 링크"}
SEARCH_PREFIX = "https://map.naver.com/p/search/"
# 확인 필요 항목 → 이벤트 칸. 이번 상담에 없어도 기존 이벤트에 값이 있으면 표시하지 않는다
FILLED_BY = {"희망 일시": "desired_at", "희망 장소": "venue", "이벤트 테마": "theme", "희망 상품": "product"}


def _same(old, new) -> bool:
    """같은 값인지. 노션이 돌려주는 일시(밀리초·Z 표기)와 우리가 보낸 일시를 같은 시각으로 본다."""
    if str(old) == str(new):
        return True
    from datetime import datetime
    try:
        a = datetime.fromisoformat(str(old).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(new).replace("Z", "+00:00"))
        if (a.tzinfo is None) != (b.tzinfo is None):
            return False
        return a.replace(second=0, microsecond=0) == b.replace(second=0, microsecond=0)  # 분까지만 비교
    except ValueError:
        return False


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
        elif not _same(old, value):
            diffs.append({"target": target, "field": label, "existing": old, "new": value})
    return to_set, diffs


def plan(record: dict, store) -> dict:
    cust, ev, co = record["customer"], record["event"], record["consultation"]
    needs_check = list(co["needs_check"])
    result = {"customer": None, "event": None, "diffs": [], "candidates": [], "review": "확인 대기"}

    def need_person(label: str, candidates: list) -> None:
        result["review"] = NEED_LINK
        result["candidates"].extend(candidates)
        if label not in needs_check:
            needs_check.append(label)

    found = store.find_customers(cust["phone"])
    same = [c for c in found if normalize_name(c.get("name")) == normalize_name(cust["name"])]
    result["warnings"] = warnings_for(found)

    channel = record.get("channel")
    if len(same) == 1:
        to_set, diffs = merge(same[0], cust, CUSTOMER_LABELS, "고객")
        marks = list(same[0].get("marks") or [])
        if channel and channel not in marks:  # 접수 경로는 덧붙이기만 (D46)
            to_set["marks"] = marks + [channel]
        result["customer"] = {"action": "link", "id": same[0]["id"], "url": same[0].get("url"), "set": to_set}
        result["diffs"].extend(diffs)
    elif found:
        # 연락처는 같은데 이름이 다르거나, 같은 고객이 여러 명 → 사람이 판단
        need_person("고객 연결", [{"type": "고객", "id": c["id"], "title": c.get("name"), "url": c.get("url")} for c in found])
    else:
        result["customer"] = {"action": "create", "set": dict(cust, marks=[channel] if channel else None)}

    round_no = 1
    if result["customer"] and result["customer"]["action"] == "link":
        choice = choose_event(record, store.open_events(result["customer"]["id"]))
        if choice["candidates"]:
            need_person("이벤트 연결", choice["candidates"])
        else:
            result["event"] = choice["event"]
            result["diffs"].extend(choice["diffs"])
            round_no = choice["round"]
            # 이번에 말하지 않았지만 기존 이벤트에 이미 있는 칸은 '확인 필요'에서 뺀다
            needs_check[:] = [l for l in needs_check if l not in choice.get("satisfied", [])]
    elif result["customer"]:
        result["event"] = {"action": "create", "set": _new_event(ev, co)}

    if result["diffs"] and "기존 정보와 다름" not in needs_check:
        needs_check.append("기존 정보와 다름")

    result["consultation"] = {"round": round_no if result["event"] else None, "needs_check": needs_check}
    return result


def warnings_for(customers: list) -> list:
    """사람이 붙인 표시 중 상담자에게 알려야 할 것 (블랙리스트)."""
    return ["블랙리스트 고객: {} (표시 B)".format(c.get("name") or "")
            for c in customers if BLACKLIST in (c.get("marks") or [])]


def choose_event(record: dict, events: list) -> dict:
    """연결된 고객의 진행 중 이벤트 중에서 이번 상담을 붙일 곳을 고른다.

    테마가 같거나 어느 한쪽 테마가 미정인 이벤트만 후보. 후보가 하나면 다음 차수로 연결,
    없으면 새 이벤트, 둘 이상이면 사람이 고른다(candidates).
    """
    ev, co = record["event"], record["consultation"]
    theme = ev.get("theme")
    matching = [e for e in events if theme is None or e.get("theme") in (None, "", theme)]
    if len(matching) == 1:
        e = matching[0]
        to_set, diffs = merge(e, ev, EVENT_LABELS, "이벤트")
        fill, _ = merge(e, ev, EVENT_FILL_ONLY, "이벤트")
        to_set.update(fill)
        # 특이사항은 덮어쓰지 않고 새 내용만 날짜와 함께 덧붙인다
        if ev.get("notes"):
            old = e.get("notes") or ""
            if not old:
                to_set["notes"] = ev["notes"]
            elif ev["notes"] not in old:
                day = record["consultation"]["consulted_at"][5:10].replace("-", "/")
                to_set["notes"] = old + "\n[" + day + "] " + ev["notes"]
        # 자동 검색 링크만 있던 곳에 직원이 보낸 정확한 링크가 오면 바꾼다 (사람이 넣은 링크는 그대로)
        new_url, old_url = ev.get("map_url"), e.get("map_url") or ""
        if new_url and old_url.startswith(SEARCH_PREFIX) and not new_url.startswith(SEARCH_PREFIX):
            to_set["map_url"] = new_url
        satisfied = [label for label, key in FILLED_BY.items() if ev.get(key) in (None, "") and e.get(key)]
        return {"event": {"action": "link", "id": e["id"], "url": e.get("url"), "set": to_set},
                "diffs": diffs, "round": int(e.get("consult_count") or 0) + 1, "candidates": [],
                "satisfied": satisfied}
    if len(matching) > 1:
        return {"event": None, "diffs": [], "round": None, "candidates": [
            {"type": "이벤트", "id": e["id"], "title": e.get("title"), "url": e.get("url")} for e in matching]}
    return {"event": {"action": "create", "set": _new_event(ev, co)}, "diffs": [], "round": 1, "candidates": []}


def _new_event(ev: dict, co: dict) -> dict:
    fields = {k: v for k, v in ev.items() if v is not None}
    fields["status"] = NEW_EVENT_STATUS
    fields["requested_on"] = co["consulted_at"][:10]
    return fields


def event_title(name: str, ev: dict) -> str:
    when = ev.get("desired_at")
    if when:
        when = "{}/{}".format(int(when[5:7]), int(when[8:10]))
    else:  # 짧은 원문만 제목에 쓰고, 긴 원문은 '희망 일시(원문)'에만 남긴다
        text = (ev.get("desired_at_text") or "").strip()
        when = text if text and len(text) <= 12 else "일정 미정"
    return "{} · {} · {}".format(name, ev.get("theme") or "테마 미정", when)


def consultation_title(name: str, consulted_at: str, round_no: Optional[int]) -> str:
    day = "{}/{}".format(consulted_at[5:7], consulted_at[8:10])
    tail = "{}차 상담".format(round_no) if round_no else "연결 확인 필요"
    return "{} {} · {}".format(day, name, tail)


def apply(record: dict, p: dict, store) -> dict:
    """plan 결과대로 저장소에 쓴다. 쓰는 순서: 고객 → 이벤트 → 상담 이력."""
    cust, co = record["customer"], record["consultation"]
    out = {"review": p["review"], "needs_check": p["consultation"]["needs_check"], "diffs": p["diffs"],
           "candidates": p["candidates"], "warnings": p.get("warnings", []), "customer": None, "event": None}

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
    if fields.get("consultant") and hasattr(store, "staff"):
        fields["consultant"] = match_staff(fields["consultant"], store.staff())
    fields["needs_check"] = p["consultation"]["needs_check"]
    fields["round"] = round_no
    fields["review"] = p["review"]
    fields["title"] = consultation_title(cust["name"], co["consulted_at"], round_no)
    ref = store.create_consultation(fields, event_id, body_sections(record, p))
    out["consultation"] = {"id": ref["id"], "url": ref.get("url"), "round": round_no, "title": fields["title"]}
    return out


def _write_event(event_plan: dict, name: str, store, customer_id: str) -> dict:
    if event_plan["action"] == "create":
        fields = dict(event_plan["set"])
        fields["title"] = event_title(name, fields)
        return store.create_event(fields, customer_id)
    ref = {"id": event_plan["id"], "url": event_plan.get("url")}
    if event_plan["set"]:
        store.update_event(ref["id"], event_plan["set"])
    return ref


def resolve(record: dict, consultation_id: str, decision: str, store, customer_id: Optional[str] = None,
            event_id: Optional[str] = None, by: Optional[str] = None) -> dict:
    """'고객 연결 필요'로 남은 상담을 사람의 답에 따라 연결한다.

    decision: same(기존 고객과 같은 사람) | separate(별도 고객).
    고객 이름은 바꾸지 않는다(같은 고객이면 기존 이름 유지, 접수명은 기록에만 남김).
    """
    from .record import InputError
    cust, co = record["customer"], record["consultation"]
    needs = [x for x in co["needs_check"] if x not in ("고객 연결", "이벤트 연결")]
    diffs = []

    if decision == "separate":
        ref = store.create_customer(dict(cust))
        cid, name, events = ref["id"], cust["name"], []
        out_customer = {"action": "create", "url": ref.get("url")}
        warnings = []
        note = "별도 고객으로 등록"
    elif decision == "same":
        if not customer_id:
            raise InputError("NEED_CUSTOMER", "연결할 기존 고객을 지정해 주세요.")
        c = store.get_customer(customer_id)
        cid, name = c["id"], c.get("name") or cust["name"]
        to_set, d = merge(c, cust, CUSTOMER_LABELS, "고객")
        diffs += d
        if to_set:
            store.update_customer(cid, to_set)
        events = store.open_events(cid)
        out_customer = {"action": "link", "url": c.get("url")}
        warnings = warnings_for([c])
        note = "기존 고객 ‘{}’과 같은 사람으로 연결 (접수명 ‘{}’)".format(name, cust["name"])
    else:
        raise InputError("BAD_DECISION", "same 또는 separate만 가능합니다.")

    if event_id:
        e = store.get_event(event_id)
        choice = choose_event(record, [dict(e, theme=None)])  # 사람이 고른 이벤트는 테마와 관계없이 연결
    else:
        choice = choose_event(record, events)
    if choice["candidates"]:
        raise InputError("NEED_EVENT", "진행 중인 이벤트가 여러 개입니다. 연결할 이벤트를 골라 주세요: " +
                         ", ".join(c.get("title") or "" for c in choice["candidates"]))
    diffs += choice["diffs"]
    ref = _write_event(choice["event"], name, store, cid)
    if diffs and "기존 정보와 다름" not in needs:
        needs.append("기존 정보와 다름")

    round_no = choice["round"]
    fields = {"title": consultation_title(name, co["consulted_at"], round_no), "round": round_no,
              "review": "확인 대기", "needs_check": needs}
    lines = [note + (" · 확인: {}".format(by) if by else "")]
    lines += ["{} {}: 기존 “{}” / 이번 “{}” (덮어쓰지 않음)".format(d["target"], d["field"], d["existing"], d["new"])
              for d in diffs]
    store.update_consultation(consultation_id, fields, ref["id"], [("연결 확인 결과", lines)])
    return {"review": "확인 대기", "needs_check": needs, "diffs": diffs, "warnings": warnings, "customer": out_customer,
            "event": {"action": choice["event"]["action"], "url": ref.get("url")},
            "consultation": {"id": consultation_id, "round": round_no, "title": fields["title"]}}


def body_sections(record: dict, p: dict) -> list:
    """상담 이력 페이지 본문: [(제목, [줄, ...]), ...]"""
    sections = []
    if p.get("warnings"):
        sections.append(("주의", p["warnings"]))
    if record["evidence"]:
        lines = []
        for e in record["evidence"]:
            time = " ({})".format(e["time"]) if e.get("time") else ""
            text = "{} — “{}”{}".format(e["field"] or "근거", e["quote"], time)
            lines.append((text, e["clip"]) if e.get("clip") else text)  # 녹음 클립은 그 줄 밑에 (D43)
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
