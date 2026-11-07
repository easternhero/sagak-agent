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

CUSTOMER_PROPS = {
    "name": ("의뢰인", "title"),
    "phone": ("연락처", "phone_number"),
    "email": ("전자메일", "email"),
    "company": ("회사·단체명", "rich_text"),
    "customer_type": ("고객 구분", "select"),
    "marks": ("표시", "multi_select"),  # K 출장 렌탈 · S 스마트스토어 · B 블랙리스트 — 사람이 고른다 (D24)
}
EVENT_PROPS = {
    "title": ("제목", "title"),
    "theme": ("이벤트 테마", "select"),
    "product": ("희망 이벤트", "select"),
    "venue": ("희망 장소", "rich_text"),
    "desired_at": ("희망 일시", "date"),
    "desired_at_text": ("희망 일시(원문)", "rich_text"),
    "budget": ("예상 금액", "number"),
    "deposit": ("예약금액", "number"),  # 친구가 만든 칸
    "map_url": ("지도 링크", "url"),
    "confirmed_at": ("날짜", "date"),      # 확정 일시 (친구가 만든 칸)
    "brand": ("제휴", "select"),            # 접수 브랜드
    "notes": ("특이사항", "rich_text"),     # 현장에서 챙길 것
    "request": ("문의 및 신청사항", "rich_text"),
    "status": ("이벤트 상태", "select"),
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


def to_blocks(sections: list) -> list:
    """[(제목, [줄...])] → Notion 블록. 전사 원문은 문단, 나머지는 글머리 목록."""
    blocks = []
    for heading, lines in sections:
        blocks.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": _rich(heading)}})
        kind = "paragraph" if heading == "전사 원문" else "bulleted_list_item"
        for line in lines:
            if not line.strip():
                continue
            blocks.append({"object": "block", "type": kind, kind: {"rich_text": _rich(line)}})
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
        return self._create("consultations", props, to_blocks(sections))
