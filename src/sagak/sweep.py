"""기록할 때마다 노션의 모든 이벤트를 정해진 규칙으로 점검하고 정리한다 (D41).

규칙
1. 결제 상태가 '예약금 입금'이고 확정 일시가 비어 있으면 희망 일시로 채운다.
2. 결제 상태가 '예약금 입금'인데 이벤트 상태가 상담진행중·추후연락이면 '이벤트진행예정'으로 바꾼다.
3. '이벤트진행예정'인데 확정 일시 날짜가 오늘(한국 시간)보다 앞이면 '이벤트완료'로 바꾼다.
4. 희망 일시가 00:00인데 원문에 시각이 있으면 고치지 않고 알린다.

고친 이벤트는 페이지 본문 '자동 정리'에 무엇을 왜 바꿨는지 남긴다.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

KST = timezone(timedelta(hours=9))
DEPOSIT_PAID = "예약금 입금"
PLANNED = "이벤트진행예정"
DONE = "이벤트완료"
BEFORE_DEPOSIT = ("상담진행중", "추후연락")
CLOSED = ("이벤트취소", "이벤트완료")  # 끝난 이벤트는 점검하지 않는다 (취소 건은 캘린더에서도 뺌, D50)
TIME_RE = re.compile(r"(?:오전|오후|저녁|아침|밤|낮)?\s*\d{1,2}\s*시(?:\s*\d{1,2}\s*분|\s*반)?|\b\d{1,2}:\d{2}\b")


def _parse(value: Optional[str]) -> Optional[datetime]:
    """노션 날짜 문자열 → KST datetime. 날짜만이면 None이 아니라 그날 00:00(시각 없음 표시는 호출 쪽에서)."""
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    text = re.sub(r"\.\d+(?=[+-]\d{2}:\d{2}$|$)", "", text)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def _has_time(value: Optional[str]) -> bool:
    return bool(value) and "T" in value


def _same_value(value: str) -> str:
    """확정 일시에 그대로 옮길 값: 시각이 있으면 KST 분 단위, 날짜만이면 날짜."""
    if not _has_time(value):
        return value[:10]
    return _parse(value).isoformat(timespec="minutes")


def check(event: dict, today) -> tuple:
    """이벤트 하나 → (바꿀 칸, 바꾼 이유 목록, 알림 목록). 아무것도 바꾸지 않으면 빈 값."""
    fields, why, warns = {}, [], []
    pay, status = event.get("payment_status"), event.get("status")
    if status in CLOSED:
        return fields, why, warns
    desired, confirmed = event.get("desired_at"), event.get("confirmed_at")
    if pay == DEPOSIT_PAID and not confirmed and desired:
        confirmed = _same_value(desired)
        fields["confirmed_at"] = confirmed
        why.append("확정 일시를 희망 일시로 채움 (예약금 입금)")
    if pay == DEPOSIT_PAID and status in BEFORE_DEPOSIT:
        status = PLANNED
        fields["status"] = PLANNED
        why.append("이벤트 상태 {} → {} (예약금 입금)".format(event.get("status"), PLANNED))
    when = _parse(confirmed)
    if status == PLANNED and when and when.date() < today:
        fields["status"] = DONE
        why.append("이벤트 상태 {} → {} (확정 일시 {} 지남)".format(PLANNED, DONE, when.strftime("%m/%d")))
    d = _parse(desired)
    raw = event.get("desired_at_text") or ""
    if _has_time(desired) and d and (d.hour, d.minute) == (0, 0):
        m = TIME_RE.search(raw)
        if m:
            warns.append("희망 일시가 00:00인데 원문에 시각이 있어요: '{}'".format(m.group(0).strip()))
    return fields, why, warns


def run(store, now: Optional[datetime] = None, dry_run: bool = False, scope: Optional[str] = None) -> dict:
    """scope: 'test' = 테스트 이벤트만, 'real' = 테스트 제외, None = 전부 (D44)."""
    from .normalize import TEST_PREFIX
    now = (now or datetime.now(KST)).astimezone(KST)
    changes, warnings = [], []
    for e in store.all_events():
        test = TEST_PREFIX in (e.get("title") or "")
        if (scope == "test" and not test) or (scope == "real" and test):
            continue
        fields, why, warns = check(e, now.date())
        item = {"id": e["id"], "url": e.get("url"), "title": e.get("title")}
        if fields:
            if not dry_run:
                store.update_event(e["id"], fields)
                store.append_event_note(e["id"], "자동 정리 ({})".format(now.strftime("%m/%d %H:%M")), why)
            changes.append(dict(item, changes=why))
        for w in warns:
            warnings.append(dict(item, warning=w))
    return {"changes": changes, "warnings": warnings, "dry_run": dry_run, "scope": scope or "all"}
