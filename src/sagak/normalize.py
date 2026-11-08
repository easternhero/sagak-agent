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


# 숫자 10자리 이상(하이픈·공백 허용) = 계좌·카드번호 후보. 휴대폰 번호(01X, 10~11자리)는 남긴다 (D29).
# 공백은 날짜·시각("2026-11-05 19:46")과 섞이므로 계좌 패턴엔 하이픈만, 카드는 4자리×4 묶음만 따로.
LONG_NUMBER_RE = re.compile(r"(?<![\d-])(?:\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{4}|\d(?:-?\d){9,})(?![\d-])")
MASK = "[번호 가림]"


# 띄어 쓴 계좌번호(예: 302 0591 8134 21). 시각·날짜(콜론·하이픈·점)와 붙은 숫자는 제외
SPACED_NUMBER_RE = re.compile(r"(?<![\d:.\-])\d{2,6}(?: \d{2,6}){1,5}(?![\d:.\-])")
URL_RE = re.compile(r"https?://\S+")


def mask_numbers(text: Optional[str]) -> Optional[str]:
    """계좌번호·카드번호처럼 긴 번호를 가린다. 휴대폰 번호와 링크(URL) 속 숫자는 그대로."""
    if not text:
        return text

    def repl(m):
        digits = re.sub(r"\D", "", m.group(0))
        if re.fullmatch(r"01[016789]\d{7,8}", digits):
            return m.group(0)
        return MASK

    def spaced(m):
        digits = re.sub(r"\D", "", m.group(0))
        return repl(m) if 10 <= len(digits) <= 20 else m.group(0)

    parts, last = [], 0
    for u in URL_RE.finditer(text):
        chunk = text[last:u.start()]
        parts.append(SPACED_NUMBER_RE.sub(spaced, LONG_NUMBER_RE.sub(repl, chunk)))
        parts.append(u.group(0))
        last = u.end()
    parts.append(SPACED_NUMBER_RE.sub(spaced, LONG_NUMBER_RE.sub(repl, text[last:])))
    return "".join(parts)


TITLE_RE = re.compile(r"(님|씨|대표님?|실장님?|팀장님?|과장님?|매니저님?)$")


def match_staff(name: Optional[str], staff: list) -> Optional[str]:
    """상담자 이름을 직원 명단의 이름으로 맞춘다. '서준', '서준님' → '박서준'.

    정확히 같거나, 성을 뺀 이름이 직원 한 명과만 맞으면 그 직원. 아니면 받은 이름 그대로(직원 외 상담자).
    """
    raw = (name or "").strip()
    key = TITLE_RE.sub("", normalize_name(raw))
    if not key:
        return raw or None
    for s in staff:
        if normalize_name(s) == key:
            return s
    hits = [s for s in staff if len(key) >= 2 and normalize_name(s).endswith(key)]
    return hits[0] if len(hits) == 1 else raw


PAREN_RE = re.compile(r"\s*[(（]([^)）]*)[)）]\s*")


def split_name(name: Optional[str]):
    """'김민수(그랜드호텔)' → ('김민수', '그랜드호텔'). 괄호 안은 지역·호텔명·회사명(관리 페이지 표기)."""
    if not name:
        return name, None
    notes = [n.strip() for n in PAREN_RE.findall(name) if n.strip()]
    rest = PAREN_RE.sub(" ", name).strip()
    return (rest or None), (", ".join(notes) or None)


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


# 봇 테스트용 고객 표시 (D44). 이 표시가 있는 기록은 `sagak cleanup-test`로 한꺼번에 휴지통에 넣는다.
TEST_PREFIX = "[테스트]"
TEST_PHONE_PREFIX = "010-0000-"


def is_test(name: Optional[str] = None, phone: Optional[str] = None) -> bool:
    return bool((name or "").strip().startswith(TEST_PREFIX) or (phone or "").startswith(TEST_PHONE_PREFIX))
