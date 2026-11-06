"""캡션(고객 정보 텍스트) 파싱과 값 정규화."""
from __future__ import annotations

import re
from typing import Optional

PHONE_RE = re.compile(r"(01[016789])[\s.\-]?(\d{3,4})[\s.\-]?(\d{4})")
EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")


def normalize_phone(text: Optional[str]) -> Optional[str]:
    """휴대폰 번호를 010-0000-0000 형식으로. 없으면 None."""
    if not text:
        return None
    m = PHONE_RE.search(text)
    if not m:
        return None
    return "-".join(m.groups())


def normalize_name(name: Optional[str]) -> str:
    """이름 비교용: 공백 제거."""
    return re.sub(r"\s+", "", name or "")


def parse_caption(caption: Optional[str]) -> dict:
    """'김민수 / 010-1234-5678 / a@b.com / 회사' 형태에서 고객 정보를 꺼낸다.

    구분자는 / , 줄바꿈. '성함:' 같은 라벨은 떼어 낸다.
    전화번호·이메일이 아닌 첫 항목이 이름, 그 뒤 항목은 회사·단체명으로 본다.
    """
    result = {"name": None, "phone": None, "email": None, "company": None}
    if not caption:
        return result
    parts = [p.strip() for p in re.split(r"[/\n,]", caption) if p.strip()]
    others = []
    for part in parts:
        value = re.sub(r"^(성함|이름|연락처|전화|전화번호|이메일|메일|회사|회사명|단체)\s*[:：]\s*", "", part)
        if result["phone"] is None and PHONE_RE.search(value):
            result["phone"] = normalize_phone(value)
        elif result["email"] is None and EMAIL_RE.search(value):
            result["email"] = EMAIL_RE.search(value).group(0)
        elif value:
            others.append(value)
    if others:
        result["name"] = others[0]
    if len(others) > 1:
        result["company"] = " ".join(others[1:])
    return result
