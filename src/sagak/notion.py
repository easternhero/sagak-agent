"""Notion REST API 저장소 (표준 라이브러리 urllib만 사용)."""
from __future__ import annotations

import json
import re
import os
import urllib.error
import urllib.request
from typing import Optional

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"
TEXT_LIMIT = 2000      # rich_text 한 덩어리 최대 글자 수
BLOCK_LIMIT = 95       # 페이지 생성 시 children 최대 100개, 여유를 둠
APPEND_BATCH = 100     # 블록 덧붙이기 한 번에 최대 100개
PARA_CHARS = 1800      # 전사 원문은 여러 줄을 한 문단으로 묶는다(블록 수 줄이기)
TRANSCRIPT = "전사 원문"

CUSTOMER_PROPS = {
    "name": ("의뢰인", "title"),
    "phone": ("연락처", "phone_number"),
    "email": ("전자메일", "email"),
    "company": ("회사·단체명", "rich_text"),
    "customer_type": ("고객 구분", "select"),
    "marks": ("표시", "multi_select"),  # 업체 표기(예: B 블랙리스트) — 사람이 고른다 (D24)
}
EVENT_PROPS = {
    "title": ("제목", "title"),
    "theme": ("이벤트 테마", "select"),
    "product": ("희망 이벤트", "select"),
    "venue": ("희망 장소", "rich_text"),
    "desired_at": ("희망 일시", "date"),
    "desired_at_text": ("희망 일시(원문)", "rich_text"),
    "budget": ("고객 예산", "number"),  # 고객이 말한 예산 (사람이 넣는 '확정 금액'과 구분)
    "deposit": ("예약금액", "number"),  # 고객사가 만든 칸
    "map_url": ("지도 링크", "url"),
    "confirmed_at": ("확정 일시", "date"),  # 예약이 확정된 일시 (캘린더 기준)
    "brand": ("제휴", "select"),            # 접수 브랜드
    "notes": ("특이사항", "rich_text"),     # 현장에서 챙길 것
    "request": ("문의 및 신청사항", "rich_text"),
    "status": ("이벤트 상태", "select"),
    "payment_status": ("결제 상태", "select"),  # 사람이 입력. 봇은 '환불 완료'만 (대화에 분명할 때, D51)
    "refund_amount": ("환불 금액", "number"),
    "requested_on": ("의뢰일", "date"),
}
CONSULT_PROPS = {
    "title": ("제목", "title"),
    "round": ("상담 차수", "number"),
    "consultant": ("상담자", "select"),  # 직원 이름 선택지. 없는 이름이면 Notion이 선택지를 새로 만든다
    "consulted_at": ("상담 일시", "date"),
    "summary": ("상담 내역", "rich_text"),
    "options": ("옵션 내역", "rich_text"),
    "option_price": ("옵션 가격", "number"),
    "follow_up": ("후속 업무", "rich_text"),
    "next_contact": ("다음 연락 시점", "rich_text"),
    "needs_check": ("확인 필요", "multi_select"),
    "questions": ("추가 질문", "rich_text"),
    "review": ("검토 상태", "select"),
    "input_type": ("입력 방식", "select"),
}


class NotionError(Exception):
    pass


def _chunks(text: str):
    return [text[i:i + TEXT_LIMIT] for i in range(0, len(text), TEXT_LIMIT)] or [""]


def _rich(text: str) -> list:
    return [{"type": "text", "text": {"content": c}} for c in _chunks(text)]


def to_property(kind: str, value):
    if kind == "title":
        return {"title": _rich(str(value))}
    if kind == "rich_text":
        if isinstance(value, list):
            value = "\n".join(str(v) for v in value)
        return {"rich_text": _rich(str(value))}
    if kind == "phone_number":
        return {"phone_number": value}
    if kind == "email":
        return {"email": value}
    if kind == "select":
        return {"select": {"name": value}}
    if kind == "multi_select":
        return {"multi_select": [{"name": v} for v in value]}
    if kind == "number":
        return {"number": value}
    if kind == "date":  # 분까지만 다루지만 Notion에는 초를 0으로 채워 표준 형식으로 보낸다
        return {"date": {"start": re.sub(r"(T\d{2}:\d{2})(?=[+-]\d{2}:\d{2}$|Z$|$)", r"\1:00", str(value))}}
    if kind == "relation":
        return {"relation": [{"id": i} for i in value]}
    if kind == "url":
        return {"url": value}
    raise ValueError(kind)


def to_properties(fields: dict, mapping: dict) -> dict:
    """None·빈 목록은 보내지 않는다 (기존 값을 지우지 않기 위해)."""
    props = {}
    for key, (name, kind) in mapping.items():
        value = fields.get(key)
        if value is None or value == [] or value == "":
            continue
        props[name] = to_property(kind, value)
    return props


def from_property(prop: dict):
    kind = prop.get("type")
    value = prop.get(kind)
    if kind in ("title", "rich_text"):
        return "".join(t.get("plain_text") or t.get("text", {}).get("content", "") for t in value or []) or None
    if kind == "select":
        return value["name"] if value else None
    if kind == "multi_select":
        return [v["name"] for v in value or []]
    if kind == "date":
        return value["start"] if value else None
    if kind == "relation":
        return [r["id"] for r in value or []]
    return value


def from_properties(page: dict, mapping: dict) -> dict:
    props = page.get("properties", {})
    out = {"id": page["id"], "url": page.get("url")}
    for key, (name, _kind) in mapping.items():
        if name in props:
            out[key] = from_property(props[name])
    return out


def audio_block(upload_id: str) -> dict:
    return {"object": "block", "type": "audio", "audio": {"type": "file_upload", "file_upload": {"id": upload_id}}}


def pack_lines(lines: list, limit: int = PARA_CHARS) -> list:
    """전사 줄을 줄바꿈으로 이어 붙인 문단들로. 한 줄이 너무 길면 그 줄만 따로."""
    out, cur = [], ""
    for line in lines:
        line = line.rstrip()
        if not line.strip():
            continue
        if cur and len(cur) + 1 + len(line) > limit:
            out.append(cur)
            cur = ""
        cur = line if not cur else cur + "\n" + line
    if cur:
        out.append(cur)
    return out


def transcript_blocks(lines: list) -> list:
    return [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich(p)}} for p in pack_lines(lines)]


def to_blocks(sections: list) -> list:
    """[(제목, [줄...])] → Notion 블록. 줄이 (글, 파일 업로드 id)면 그 글머리 밑에 녹음 클립 (D43).
    전사 원문은 create_consultation이 접기 목록으로 따로 붙인다 (D42)."""
    blocks = []
    for heading, lines in sections:
        if heading == TRANSCRIPT:
            continue
        blocks.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": _rich(heading)}})
        for line in lines:
            clip = None
            if isinstance(line, (tuple, list)):
                line, clip = line[0], line[1]
            if not line.strip():
                continue
            item = {"rich_text": _rich(line)}
            if clip:
                item["children"] = [audio_block(clip)]
            blocks.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": item})
    if len(blocks) > BLOCK_LIMIT:
        blocks = blocks[:BLOCK_LIMIT - 1] + [{"object": "block", "type": "paragraph", "paragraph": {
            "rich_text": _rich("(분량이 많아 이하 생략)")}}]
    return blocks


class NotionStore:
    def __init__(self, token: str, customers_db: str, events_db: str, consultations_db: str, opener=None):
        self.token = token
        self.dbs = {"customers": customers_db, "events": events_db, "consultations": consultations_db}
        self._open = opener or urllib.request.urlopen

    @classmethod
    def from_env(cls) -> "NotionStore":
        names = ["NOTION_API_KEY", "SAGAK_NOTION_CUSTOMERS_DB", "SAGAK_NOTION_EVENTS_DB", "SAGAK_NOTION_CONSULTATIONS_DB"]
        missing = [n for n in names if not os.environ.get(n)]
        if missing:
            raise NotionError("환경변수 없음: " + ", ".join(missing))
        return cls(*(os.environ[n] for n in names))

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        req = urllib.request.Request(
            API + path, method=method,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={"Authorization": "Bearer " + self.token, "Notion-Version": VERSION,
                     "Content-Type": "application/json"})
        try:
            with self._open(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise NotionError("Notion {} {} 실패 ({}): {}".format(method, path, e.code, detail)) from None
        except urllib.error.URLError as e:
            raise NotionError("Notion 연결 실패: {}".format(e.reason)) from None

    def _query(self, db: str, flt: dict) -> list:
        return self._request("POST", "/databases/{}/query".format(self.dbs[db]), {"filter": flt}).get("results", [])

    def _create(self, db: str, props: dict, children: Optional[list] = None) -> dict:
        body = {"parent": {"database_id": self.dbs[db]}, "properties": props}
        if children:
            body["children"] = children
        page = self._request("POST", "/pages", body)
        return {"id": page["id"], "url": page.get("url")}

    def _update(self, page_id: str, props: dict) -> None:
        if props:
            self._request("PATCH", "/pages/{}".format(page_id), {"properties": props})

    # --- sync.py가 쓰는 저장소 인터페이스 ---
    def ping(self) -> dict:
        return {k: self._request("GET", "/databases/{}".format(v))["id"] for k, v in self.dbs.items()}

    def staff(self) -> list:
        """상담 이력 DB '상담자' 선택지 = 직원 명단 (Notion에서 관리)."""
        db = self._request("GET", "/databases/{}".format(self.dbs["consultations"]))
        prop = db.get("properties", {}).get("상담자", {})
        return [o["name"] for o in (prop.get("select") or {}).get("options", [])]

    def find_customers(self, phone: str) -> list:
        pages = self._query("customers", {"property": "연락처", "phone_number": {"equals": phone}})
        return [from_properties(p, CUSTOMER_PROPS) for p in pages]

    def open_events(self, customer_id: str) -> list:
        from .sync import OPEN_STATUSES
        flt = {"and": [
            {"property": "고객", "relation": {"contains": customer_id}},
            {"or": [{"property": "이벤트 상태", "select": {"equals": s}} for s in OPEN_STATUSES]},
        ]}
        out = []
        for page in self._query("events", flt):
            e = from_properties(page, EVENT_PROPS)
            rel = page.get("properties", {}).get("상담 이력", {})
            e["consult_count"] = len(rel.get("relation") or [])
            out.append(e)
        return out

    def all_events(self) -> list:
        """점검용: 모든 이벤트 (페이지 넘김)."""
        out, cursor = [], None
        while True:
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            res = self._request("POST", "/databases/{}/query".format(self.dbs["events"]), body)
            out += [from_properties(p, EVENT_PROPS) for p in res.get("results", [])]
            if not res.get("has_more"):
                return out
            cursor = res.get("next_cursor")

    def product_places(self) -> dict:
        """노션 '상품' DB(SAGAK_NOTION_PRODUCTS_DB)의 상품명 → 네이버 지도 링크·장소. DB가 없으면 빈 값 (D54)."""
        db = os.environ.get("SAGAK_NOTION_PRODUCTS_DB")
        if not db:
            return {}
        out = {}
        res = self._request("POST", "/databases/{}/query".format(db), {"page_size": 100})
        for page in res.get("results", []):
            props = page.get("properties", {})
            name = from_property(props.get("상품명", {"type": "title", "title": []}))
            if not name:
                continue
            out[name] = {"map_url": from_property(props["네이버 지도"]) if "네이버 지도" in props else None,
                         "venue": from_property(props["장소"]) if "장소" in props else None}
        return out

    def set_product_map(self, product: str, url: str) -> Optional[str]:
        """노션 '상품' DB에서 상품명이 같은 줄의 '네이버 지도'를 바꾼다. 바꾼 페이지 URL, 없으면 None (D55)."""
        db = os.environ.get("SAGAK_NOTION_PRODUCTS_DB")
        if not db:
            raise NotionError("환경변수 없음: SAGAK_NOTION_PRODUCTS_DB")
        res = self._request("POST", "/databases/{}/query".format(db),
                            {"filter": {"property": "상품명", "title": {"equals": product}}})
        pages = res.get("results", [])
        if not pages:
            return None
        self._request("PATCH", "/pages/{}".format(pages[0]["id"]), {"properties": {"네이버 지도": {"url": url}}})
        return pages[0].get("url")

    def set_map_url(self, page_id: str, url: Optional[str]) -> None:
        """지도 링크를 바꾸거나 비운다(None)."""
        self._request("PATCH", "/pages/{}".format(page_id), {"properties": {"지도 링크": {"url": url}}})

    def append_event_note(self, page_id: str, heading: str, lines: list) -> None:
        self._request("PATCH", "/blocks/{}/children".format(page_id), {"children": to_blocks([(heading, lines)])})

    def history(self, phone: str) -> list:
        """그 연락처 고객의 모든 이벤트와 상담 이력(오래된 순)."""
        out = []
        for c in self.find_customers(phone):
            events = []
            for page in self._query("events", {"property": "고객", "relation": {"contains": c["id"]}}):
                e = from_properties(page, EVENT_PROPS)
                cons = self._request("POST", "/databases/{}/query".format(self.dbs["consultations"]), {
                    "filter": {"property": "이벤트", "relation": {"contains": e["id"]}},
                    "sorts": [{"property": "상담 일시", "direction": "ascending"}]}).get("results", [])
                e["consultations"] = [from_properties(p, CONSULT_PROPS) for p in cons]
                events.append(e)
            out.append(dict(c, events=events))
        return out

    def _query_all(self, db: str, flt: dict) -> list:
        out, cursor = [], None
        while True:
            body = {"filter": flt, "page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            res = self._request("POST", "/databases/{}/query".format(self.dbs[db]), body)
            out += res.get("results", [])
            if not res.get("has_more"):
                return out
            cursor = res.get("next_cursor")

    def test_pages(self) -> dict:
        """[테스트] 표시 고객과 그 이벤트·상담, 제목에 [테스트]가 붙은 이벤트·상담 (D44)."""
        from .normalize import TEST_PHONE_PREFIX, TEST_PREFIX
        title = lambda p: from_property(next(v for v in p["properties"].values() if v.get("type") == "title"))
        found = {"customers": {}, "events": {}, "consultations": {}}
        for p in self._query_all("customers", {"or": [
                {"property": "의뢰인", "title": {"starts_with": TEST_PREFIX}},
                {"property": "연락처", "phone_number": {"starts_with": TEST_PHONE_PREFIX}}]}):
            found["customers"][p["id"]] = title(p)
        ev_filters = [{"property": "제목", "title": {"contains": TEST_PREFIX}}]
        ev_filters += [{"property": "고객", "relation": {"contains": cid}} for cid in found["customers"]]
        for i in range(0, len(ev_filters), 90):
            for p in self._query_all("events", {"or": ev_filters[i:i + 90]}):
                found["events"][p["id"]] = title(p)
        co_filters = [{"property": "제목", "title": {"contains": TEST_PREFIX}}]
        co_filters += [{"property": "이벤트", "relation": {"contains": eid}} for eid in found["events"]]
        for i in range(0, len(co_filters), 90):
            for p in self._query_all("consultations", {"or": co_filters[i:i + 90]}):
                found["consultations"][p["id"]] = title(p)
        return found

    def reviewer_pages(self) -> dict:
        """공개 데모 정리용 (D60): 상담자가 '리뷰어 #…'인 상담, 그 상담만 있는 이벤트, 그런 이벤트만 있는 고객.
        처음 넣어 둔 기본 예시(직원이 상담자인 기록)는 남는다."""
        from .demo_mode import is_reviewer_label

        def page(pid):
            return self._request("GET", "/pages/{}".format(pid))

        return reviewer_cleanup_plan(
            self._query_all("consultations", {"property": "상담자", "select": {"is_not_empty": True}}),
            page, is_reviewer_label)

    def trash(self, page_id: str) -> None:
        self._request("PATCH", "/pages/{}".format(page_id), {"archived": True})

    def create_customer(self, fields: dict) -> dict:
        return self._create("customers", to_properties(fields, CUSTOMER_PROPS))

    def update_customer(self, page_id: str, fields: dict) -> None:
        self._update(page_id, to_properties(fields, CUSTOMER_PROPS))

    def create_event(self, fields: dict, customer_id: Optional[str]) -> dict:
        props = to_properties(fields, EVENT_PROPS)
        if customer_id:
            props["고객"] = to_property("relation", [customer_id])
        return self._create("events", props)

    def update_event(self, page_id: str, fields: dict) -> None:
        self._update(page_id, to_properties(fields, EVENT_PROPS))

    def get_customer(self, page_id: str) -> dict:
        return from_properties(self._request("GET", "/pages/{}".format(page_id)), CUSTOMER_PROPS)

    def get_event(self, page_id: str) -> dict:
        page = self._request("GET", "/pages/{}".format(page_id))
        e = from_properties(page, EVENT_PROPS)
        e["consult_count"] = len(page.get("properties", {}).get("상담 이력", {}).get("relation") or [])
        return e

    def update_consultation(self, page_id: str, fields: dict, event_id: Optional[str], sections: list) -> None:
        props = to_properties(fields, CONSULT_PROPS)
        props["확인 필요"] = to_property("multi_select", fields.get("needs_check") or [])  # 빈 목록도 반영
        if event_id:
            props["이벤트"] = to_property("relation", [event_id])
        self._update(page_id, props)
        if sections:
            self._request("PATCH", "/blocks/{}/children".format(page_id), {"children": to_blocks(sections)})

    def create_consultation(self, fields: dict, event_id: Optional[str], sections: list) -> dict:
        props = to_properties(fields, CONSULT_PROPS)
        if event_id:
            props["이벤트"] = to_property("relation", [event_id])
        ref = self._create("consultations", props, to_blocks(sections))
        for heading, lines in sections:
            if heading == TRANSCRIPT and lines:
                self.append_transcript(ref["id"], lines)
        return ref

    def append_transcript(self, page_id: str, lines: list) -> None:
        """전사 원문 전체를 접기 제목 아래에 100블록씩 나눠 끝까지 붙인다 (D42)."""
        n = sum(1 for l in lines if str(l).strip())
        head = {"object": "block", "type": "heading_3", "heading_3": {
            "rich_text": _rich("{} ({}줄)".format(TRANSCRIPT, n)), "is_toggleable": True}}
        res = self._request("PATCH", "/blocks/{}/children".format(page_id), {"children": [head]})
        toggle = res["results"][0]["id"]
        body = transcript_blocks(lines)
        for i in range(0, len(body), APPEND_BATCH):
            self._request("PATCH", "/blocks/{}/children".format(toggle), {"children": body[i:i + APPEND_BATCH]})

    def upload_file(self, filename: str, data: bytes, content_type: str) -> str:
        """작은 파일(20MB 이하)을 Notion에 올리고 파일 업로드 id를 돌려준다 (녹음 클립, D43)."""
        import uuid
        up = self._request("POST", "/file_uploads", {"filename": filename, "content_type": content_type})
        boundary = "----sagak" + uuid.uuid4().hex
        body = ("--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{f}\"\r\n"
                "Content-Type: {t}\r\n\r\n").format(b=boundary, f=filename, t=content_type).encode() + data + \
            "\r\n--{}--\r\n".format(boundary).encode()
        req = urllib.request.Request(API + "/file_uploads/{}/send".format(up["id"]), data=body, method="POST", headers={
            "Authorization": "Bearer " + self.token, "Notion-Version": VERSION,
            "Content-Type": "multipart/form-data; boundary=" + boundary})
        try:
            with self._open(req, timeout=60) as resp:
                json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise NotionError("Notion 파일 업로드 실패 ({}): {}".format(e.code, e.read().decode("utf-8", "replace")[:300])) from None
        except urllib.error.URLError as e:
            raise NotionError("Notion 연결 실패: {}".format(e.reason)) from None
        return up["id"]


def reviewer_cleanup_plan(consultations: list, get_page, is_reviewer) -> dict:
    """노션 페이지(JSON)로 지울 목록 계산. get_page(id) → 페이지. 테스트에서 가짜 페이지로 쓴다."""
    def rel(p, name):
        return [r["id"] for r in (p.get("properties", {}).get(name, {}).get("relation") or [])]

    def title(p):
        return from_property(next(v for v in p["properties"].values() if v.get("type") == "title"))

    found = {"customers": {}, "events": {}, "consultations": {}}
    for p in consultations:
        if is_reviewer(((p["properties"].get("상담자") or {}).get("select") or {}).get("name")):
            found["consultations"][p["id"]] = title(p)
    gone = set(found["consultations"])
    events = {}
    for cid in gone:
        for eid in rel(get_page(cid), "이벤트"):
            events.setdefault(eid, get_page(eid))
    for eid, ev in events.items():
        if set(rel(ev, "상담 이력")) <= gone:  # 리뷰어 상담만 있는 이벤트
            found["events"][eid] = title(ev)
    customers = {}
    for eid in found["events"]:
        for cust in rel(events[eid], "고객"):
            customers.setdefault(cust, get_page(cust))
    for cust, c in customers.items():
        if set(rel(c, "이벤트")) <= set(found["events"]):  # 지울 이벤트만 있는 고객
            found["customers"][cust] = title(c)
    return found
