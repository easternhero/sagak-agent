"""LLM이 만든 추출 JSON을 검사해 기록할 수 있는 형태로 정리한다.

추측하지 않는다: 값이 없거나 형식이 틀리면 비워 두고 '확인 필요'에 올린다.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from . import business
from .normalize import mask_numbers, normalize_phone, parse_caption, split_name

KST = timezone(timedelta(hours=9))
REFUND_DONE = "환불 완료"
TRANSCRIPT_EXT = (".txt", ".srt", ".vtt", ".md", ".csv")
TRANSCRIPT_MAX = 3 * 1024 * 1024


def read_transcript(path: Any) -> Optional[str]:
    """받은 전사·채팅 파일을 모델을 거치지 않고 그대로 읽는다 (D42). 읽을 수 없으면 InputError."""
    import os
    path = _text(path)
    if not path:
        return None
    if os.path.splitext(path)[1].lower() not in TRANSCRIPT_EXT:
        raise InputError("BAD_TRANSCRIPT_FILE", "전사 파일은 txt·srt·vtt만 읽을 수 있습니다: " + os.path.basename(path))
    if not os.path.isfile(path):
        raise InputError("BAD_TRANSCRIPT_FILE", "전사 파일을 찾지 못했습니다: " + os.path.basename(path))
    if os.path.getsize(path) > TRANSCRIPT_MAX:
        raise InputError("BAD_TRANSCRIPT_FILE", "전사 파일이 너무 큽니다(3MB 초과).")
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc).replace("\r\n", "\n").strip()
        except UnicodeDecodeError:
            continue
    raise InputError("BAD_TRANSCRIPT_FILE", "전사 파일의 글자 인코딩을 알아볼 수 없습니다.")

THEMES = ("프로포즈", "생일/기념일", "기타")
# 접수 브랜드(노션 '제휴')와 상품명('희망 이벤트')은 업체별 설정 agent/business.json에서 읽는다 (business.py).
CUSTOMER_TYPES = ("개인", "기업")
INPUT_TYPES = ("녹음", "전사 텍스트", "대화")  # 대화 = 카톡·채팅 내보내기, 직원 메모
# Notion '확인 필요' 태그로 쓰는 고정 목록. 그 밖의 항목은 '추가 질문'으로 옮긴다 (태그가 끝없이 늘지 않게).
CHECK_LABELS = ("희망 일시", "희망 장소", "예산", "예약금", "이벤트 테마", "희망 상품", "다음 연락 시점", "고객 연결", "이벤트 연결", "기존 정보와 다름")


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
    """ISO 날짜/일시만 받는다. 시간대가 없으면 한국 시간으로 본다. 시각은 분까지만."""
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
    return dt.replace(second=0, microsecond=0).isoformat(timespec="minutes")


def nearest_future(desired_at: Optional[str], said: Optional[str], consulted_at: str) -> Optional[str]:
    """연도를 말하지 않았는데 상담일보다 과거로 잡혔으면, 가장 가까운 미래 연도로 옮긴다."""
    if not desired_at or (said and re.search(r"\d{4}|년", said)):
        return desired_at
    base = consulted_at[:10]
    value = desired_at
    while value[:10] < base:
        value = str(int(value[:4]) + 1) + value[4:]
    return value


def _choice(value: Any, allowed: tuple) -> Optional[str]:
    text = _text(value)
    return text if text in allowed else None


NAVER_MAP_RE = re.compile(r"^https://(map\.naver\.com|naver\.me|(m\.)?place\.naver\.com|m\.map\.naver\.com)/\S+$")


def naver_map_url(value: Any) -> Optional[str]:
    """직원이 보낸 네이버 지도 링크만 받는다. 다른 주소나 지어낸 값은 버린다."""
    text = _text(value)
    return text if text and NAVER_MAP_RE.match(text) else None


def naver_search_url(place: str) -> str:
    from urllib.parse import quote
    return "https://map.naver.com/p/search/" + quote(place)


def _join(parts: list) -> Optional[str]:
    text = " / ".join(p for p in parts if p)
    return text or None


def product_of(value: Any) -> Optional[str]:
    """상품명 또는 안내 이름 → 관리 페이지 상품명 (업체 설정 기준). 모르면 None."""
    return business.product_of(_text(value))

def build_record(data: dict, now: Optional[datetime] = None) -> dict:
    """추출 JSON → 기록용 dict. 고객 이름·연락처가 없으면 InputError."""
    now = now or datetime.now(KST)
    caption = parse_caption(data.get("caption"))
    cust_in = data.get("customer") or {}
    name, name_note = split_name(_text(cust_in.get("name")) or caption["name"])
    phone = normalize_phone(cust_in.get("phone")) or caption["phone"]
    if not name or not phone:
        missing = [label for label, v in (("성함", name), ("연락처", phone)) if not v]
        raise InputError("MISSING_CUSTOMER", "고객 " + ", ".join(missing) + " 정보가 없습니다.")

    company = _text(cust_in.get("company")) or caption["company"]
    # 기본은 개인. 회사·단체 정보가 있으면 기업.
    ctype = "기업" if company else (_choice(cust_in.get("customer_type"), CUSTOMER_TYPES) or "개인")
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

    # 장소는 장소명·주소만. 괄호 속 메모는 고객에게 물을 것으로 옮긴다
    venue, venue_note = split_name(_text(ev.get("venue")))
    if venue_note:
        questions.append("희망 장소 확인: " + venue_note)
        flag("희망 장소")

    # 상품이 정해지면 테마는 업체 설정의 상품 테마를 따른다 (D36)
    product = product_of(ev.get("product"))
    group = None if product else business.group_of(_text(ev.get("product")))
    if group:  # 종류를 말하지 않은 상품 묶음: 비워 두고 묻는다 (D45)
        flag("희망 상품")
        questions.append("{} 중 어느 상품인가요? ({})".format(group["name"], "·".join(group["choices"])))
    theme = business.theme_of(product) or (group or {}).get("theme") or _choice(ev.get("theme"), THEMES)
    if theme is None:
        flag("이벤트 테마")
    event = {
        "theme": theme,
        "product": product,
        "venue": venue,
        "desired_at": _iso(ev.get("desired_at")),
        "desired_at_text": _text(ev.get("desired_at_text")),
        "budget": _int(ev.get("budget")),
        "deposit": _int(ev.get("deposit")),
        # 상담자가 환불 완료를 분명히 말했을 때만 (D51). 그 밖의 결제 칸은 사람이
        "payment_status": REFUND_DONE if ev.get("refund_done") is True else None,
        "refund_amount": _int(ev.get("refund_amount")) if ev.get("refund_done") is True else None,
        "confirmed_at": _iso(ev.get("confirmed_at")),  # 통화에서 확정한 일시만 (노션 '확정 일시')
        "brand": business.brand_of(_text(ev.get("brand"))),
        "notes": mask_numbers(_join([_text(n) for n in (ev.get("notes") or []) if _text(n)]) if isinstance(
            ev.get("notes"), list) else _text(ev.get("notes"))),
        "request": _join(["접수 표기(괄호): " + name_note if name_note else None, _text(ev.get("request"))]),
    }
    consulted_at = _iso(data.get("consulted_at")) or now.replace(second=0, microsecond=0).isoformat(timespec="minutes")
    # 날짜만 말하고 시각이 없으면 00:00으로 두고 확인 필요 (D30)
    desired_date = _iso(ev.get("desired_date"))
    if event["desired_at"] is None and desired_date and len(desired_date) == 10:
        event["desired_at"] = desired_date + "T00:00+09:00"
        flag("희망 일시")
    event["desired_at"] = nearest_future(event["desired_at"], event["desired_at_text"], consulted_at)
    if event["desired_at"] is None:
        flag("희망 일시")
    # 고객이 예산을 말하지 않는 경우가 대부분이라 빠졌다고 표시하지 않는다 (D35)
    if event["venue"] is None:
        flag("희망 장소")
    if event["deposit"] is not None:
        flag("예약금")  # 안내한 금액일 뿐 입금 확인이 아님
    # 지도 링크 후보: 직원이 보낸 네이버 지도 링크 > 확인된 장소의 검색 링크 (D30).
    # 기록 직전에 naver.verify가 실제로 확인하고, 확실하지 않으면 비운다 (D48)
    staff_url = naver_map_url(ev.get("venue_url"))
    if staff_url:
        event["map_url"] = staff_url
    elif event["venue"] and ev.get("venue_exact") is True and "희망 장소" not in needs_check:
        event["map_url"] = naver_search_url(event["venue"])
    else:
        event["map_url"] = None

    consultation = {
        "summary": _text(co.get("summary")),
        "options": _text(co.get("options")),
        "option_price": _int(co.get("option_price")),
        "follow_up": _text(co.get("follow_up")),
        "next_contact": _text(co.get("next_contact")) or "미정",
        "questions": questions,
        "consultant": _text(data.get("consultant")),
        "consulted_at": consulted_at,
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

    # 결제 대화는 남기되 계좌·카드번호만 가린다 (D29)
    for key in ("summary", "options", "follow_up", "next_contact"):
        consultation[key] = mask_numbers(consultation.get(key))
    consultation["questions"] = [mask_numbers(q) for q in consultation.get("questions") or []]
    event["request"] = mask_numbers(event.get("request"))
    for e in evidence:
        e["quote"] = mask_numbers(e["quote"])

    out = {
        "customer": customer,
        "event": event,
        "consultation": consultation,
        "evidence": evidence,
        # 파일이 있으면 파일 원문 그대로, 없을 때만 모델이 옮긴 원문 (D42)
        "transcript": mask_numbers(read_transcript(data.get("transcript_file")) or _text(data.get("transcript"))),
        "transcript_file": _text(data.get("transcript_file")),
        "channel": None,
        "audio_file": _text(data.get("audio_file")),
    }
    out["channel"] = channel_of(data, out["transcript"])
    return out


def channel_of(data: dict, transcript: Optional[str]) -> Optional[str]:
    """접수 경로 표시 (D46). 모델이 고른 값이 업체 설정에 있으면 그것, 없으면 분명한 경우만 자동:
    녹음 → 전화, 채널 상담 내보내기 파일('OO 님과의 상담' / '저장한 날짜') → 카카오채널."""
    ch = business.channels()
    picked = _text((data.get("customer") or {}).get("channel"))
    if picked and picked in ch.values():
        return picked
    if data.get("input_type") == "녹음" and ch.get("phone"):
        return ch["phone"]
    head = [l.strip() for l in (transcript or "").splitlines() if l.strip()][:3]
    if len(head) >= 2 and head[0].endswith("님과의 상담") and head[1].startswith("저장한 날짜") and ch.get("kakao"):
        return ch["kakao"]
    return None
