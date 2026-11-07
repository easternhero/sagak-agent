"""LLM이 만든 추출 JSON을 검사해 기록할 수 있는 형태로 정리한다.

추측하지 않는다: 값이 없거나 형식이 틀리면 비워 두고 '확인 필요'에 올린다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from .normalize import normalize_phone, parse_caption

KST = timezone(timedelta(hours=9))

THEMES = ("프로포즈", "생일/기념일", "기타")
PRODUCTS = ("호텔패키지", "갤러리패키지", "레스토랑패키지", "소극장패키지")
CUSTOMER_TYPES = ("개인", "기업")
INPUT_TYPES = ("녹음", "전사 텍스트")
# Notion '확인 필요' 태그로 쓰는 고정 목록. 그 밖의 항목은 '추가 질문'으로 옮긴다 (태그가 끝없이 늘지 않게).
CHECK_LABELS = ("희망 일시", "희망 장소", "예산", "이벤트 테마", "다음 연락 시점", "고객 연결", "이벤트 연결", "기존 정보와 다름")


class InputError(Exception):
    """기록할 수 없는 입력. code는 에이전트가 사용자에게 무엇을 다시 요청할지 정한다."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = str(value).replace(",", "").strip()
    return int(digits) if digits.isdigit() else None


def _iso(value: Any) -> Optional[str]:
    """ISO 날짜/일시만 받는다. 시간대가 없으면 한국 시간으로 본다."""
    text = _text(value)
    if not text:
        return None
    try:
        if len(text) == 10:
            return date.fromisoformat(text).isoformat()
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.isoformat()


def _choice(value: Any, allowed: tuple) -> Optional[str]:
    text = _text(value)
    return text if text in allowed else None


def build_record(data: dict, now: Optional[datetime] = None) -> dict:
    """추출 JSON → 기록용 dict. 고객 이름·연락처가 없으면 InputError."""
    now = now or datetime.now(KST)
    caption = parse_caption(data.get("caption"))
    cust_in = data.get("customer") or {}
    name = _text(cust_in.get("name")) or caption["name"]
    phone = normalize_phone(cust_in.get("phone")) or caption["phone"]
    if not name or not phone:
        missing = [label for label, v in (("성함", name), ("연락처", phone)) if not v]
        raise InputError("MISSING_CUSTOMER", "고객 " + ", ".join(missing) + " 정보가 없습니다.")

    company = _text(cust_in.get("company")) or caption["company"]
    ctype = _choice(cust_in.get("customer_type"), CUSTOMER_TYPES) or ("기업" if company else None)
    customer = {
        "name": name,
        "phone": phone,
        "email": _text(cust_in.get("email")) or caption["email"],
        "company": company,
        "customer_type": ctype,
    }

    ev = data.get("event") or {}
    co = data.get("consultation") or {}
    questions = [q for q in (co.get("questions") or []) if _text(q)]
    needs_check = []
    for item in co.get("needs_check") or []:
        label = _text(item)
        if not label:
            continue
        if label in CHECK_LABELS:
            if label not in needs_check:
                needs_check.append(label)
        elif not any(label in q for q in questions):
            questions.append(label + " 확인 필요")

    def flag(label: str) -> None:
        if label not in needs_check:
            needs_check.append(label)

    theme = _choice(ev.get("theme"), THEMES)
    if theme is None:
        flag("이벤트 테마")
    event = {
        "theme": theme,
        "product": _choice(ev.get("product"), PRODUCTS),
        "venue": _text(ev.get("venue")),
        "desired_at": _iso(ev.get("desired_at")),
        "desired_at_text": _text(ev.get("desired_at_text")),
        "budget": _int(ev.get("budget")),
        "request": _text(ev.get("request")),
    }
    if event["desired_at"] is None:
        flag("희망 일시")
    if event["budget"] is None:
        flag("예산")
    if event["venue"] is None:
        flag("희망 장소")

    consultation = {
        "summary": _text(co.get("summary")),
        "options": _text(co.get("options")),
        "option_price": _int(co.get("option_price")),
        "follow_up": _text(co.get("follow_up")),
        "next_contact": _text(co.get("next_contact")) or "미정",
        "questions": questions,
        "consultant": _text(data.get("consultant")),
        "consulted_at": _iso(data.get("consulted_at")) or now.replace(microsecond=0).isoformat(),
        "input_type": _choice(data.get("input_type"), INPUT_TYPES) or "전사 텍스트",
        "needs_check": needs_check,
    }
    if not consultation["summary"]:
        raise InputError("EMPTY_CONSULTATION", "상담 내용이 비어 있습니다.")

    evidence = []
    for item in data.get("evidence") or []:
        if isinstance(item, dict) and _text(item.get("quote")):
            evidence.append({
                "field": _text(item.get("field")) or "",
                "quote": _text(item.get("quote")),
                "time": _text(item.get("time")),
            })

    return {
        "customer": customer,
        "event": event,
        "consultation": consultation,
        "evidence": evidence,
        "transcript": _text(data.get("transcript")),
    }
