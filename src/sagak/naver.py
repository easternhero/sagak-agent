"""네이버 지도 링크를 실제로 확인한 뒤에만 단다 (D48).

- 직원이 보낸 링크: 열어 보고(리디렉션 따라감) 네이버 장소 페이지로 이어질 때만.
- 자동 링크: 네이버 검색 API(지역)로 장소를 찾아 이름이 맞는 곳이 딱 하나일 때만, 그 장소 이름·주소로 만든 검색 링크.
  키(SAGAK_NAVER_CLIENT_ID / SAGAK_NAVER_CLIENT_SECRET)가 없으면 자동 링크는 달지 않는다.
  검색 API는 2026-07-31부터 네이버 클라우드 NAVER API HUB에서 발급한다(기본). 예전 개발자센터 키는
  SAGAK_NAVER_LOCAL_URL을 openapi.naver.com 주소로 주면 그 방식(헤더)으로 부른다.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

LOCAL_API = "https://naverapihub.apigw.ntruss.com/search/v1/local"  # NAVER API HUB 지역 검색
LEGACY_HOST = "openapi.naver.com"
PLACE_RE = re.compile(r"^https://((m\.)?map\.naver\.com/.*(place|entry)/\d+|(m\.|pcmap\.)?place\.naver\.com/\w+/\d+)")
ADDRESS_RE = re.compile(r"(로|길)\s*\d")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"


def _key(text: str) -> str:
    text = re.sub(r"</?b>", "", text or "")
    return re.sub(r"[\s·&/()\-,.]", "", text.lower())


ROAD_BASE_RE = re.compile(r"^(.+?(?:로|길)\s*\d+(?:-\d+)?)(?=\s|$)")
LOT_BASE_RE = re.compile(r"^(.+?(?:동|리|가)\s*\d+(?:-\d+)?)(?=\s|$)")


def base_address(item: dict) -> str:
    """'서울 용산구 소월로 322 로비층' → '서울 용산구 소월로 322' (층·건물명 떼고 건물 번호까지)."""
    road = (item.get("roadAddress") or "").strip()
    m = ROAD_BASE_RE.match(road)
    if m:
        return m.group(1)
    lot = (item.get("address") or "").strip()
    m = LOT_BASE_RE.match(lot)
    return m.group(1) if m else (road or lot)


def staff_link_ok(url: str, opener=None) -> bool:
    """링크를 열어 네이버 장소 페이지(…/place/12345)에 닿으면 True."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=10) as resp:
            final = resp.geturl() if hasattr(resp, "geturl") else url
            return getattr(resp, "status", 200) == 200 and bool(PLACE_RE.match(final))
    except (urllib.error.URLError, ValueError, OSError):
        return False


def search_places(query: str, opener=None, env=None) -> Optional[list]:
    """네이버 검색 API(지역). 키가 없거나 실패하면 None."""
    env = env if env is not None else os.environ
    cid, secret = env.get("SAGAK_NAVER_CLIENT_ID"), env.get("SAGAK_NAVER_CLIENT_SECRET")
    if not (cid and secret):
        return None
    base = env.get("SAGAK_NAVER_LOCAL_URL") or LOCAL_API
    url = base + "?" + urllib.parse.urlencode({"query": query, "display": 5})
    if LEGACY_HOST in base:
        headers = {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret}
    else:
        headers = {"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": secret}
    req = urllib.request.Request(url, headers=headers)
    try:
        with (opener or urllib.request.urlopen)(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8")).get("items") or []
    except (urllib.error.URLError, ValueError, OSError):
        return None


def confirmed_search_link(venue: str, opener=None, env=None) -> Optional[str]:
    """'이름 · 주소'처럼 함께 적혔으면 나눠서 이름 → 주소 순으로 확인한다."""
    parts = [p.strip() for p in re.split(r"\s+·\s+|\s*/\s*", venue or "") if p.strip()]
    for cand in ([venue] if len(parts) < 2 else parts):
        link = _confirmed_one(cand, opener, env)
        if link:
            return link
    return None


def _confirmed_one(venue: str, opener=None, env=None) -> Optional[str]:
    """장소명이면 이름이 맞는 곳이 딱 하나일 때, 주소면 그 주소의 장소가 있을 때만 검색 링크."""
    from .record import naver_search_url
    items = search_places(venue, opener, env)
    if not items:
        return None
    v = _key(venue)
    if ADDRESS_RE.search(venue):
        hit = any(v in _key(i.get("roadAddress")) or v in _key(i.get("address")) for i in items)
        return naver_search_url(venue) if hit else None
    same = [i for i in items if _key(i.get("title")) == v]
    if not same:
        same = [i for i in items if v in _key(i.get("title")) or (len(_key(i.get("title"))) >= 2 and _key(i.get("title")) in v)]
    if len(same) > 1:
        # 이름 후보가 여럿이어도 모두 같은 건물(같은 도로명 주소)이면 위치는 확실하다 (예: 호텔 안 식당들)
        addrs = {_key(base_address(i)) for i in same}
        if len(addrs) == 1 and "" not in addrs:
            return naver_search_url("{} {}".format(venue, base_address(same[0])).strip())
        return None
    if not same:
        return None
    place = same[0]
    title = re.sub(r"</?b>", "", place.get("title") or "")
    return naver_search_url("{} {}".format(title, base_address(place)).strip())


def verify(record: dict, opener=None, env=None) -> str:
    """record['event']['map_url'] 후보를 확인한다. 확인 못 하면 비운다. 결과 상태를 돌려준다."""
    ev = record["event"]
    url = ev.get("map_url")
    if not url:
        return "none"
    if not url.startswith("https://map.naver.com/p/search/"):  # 직원이 보낸 링크
        if staff_link_ok(url, opener):
            return "staff_ok"
        ev["map_url"] = None
        record["consultation"]["questions"].append("보내 주신 지도 링크가 네이버 장소로 열리지 않아요. 링크를 다시 확인해 주세요")
        return "staff_failed"
    from . import business
    fixed = business.venue_of(ev.get("product"))  # 장소가 늘 같은 상품은 업체 설정의 장소로 (D53)
    link = (confirmed_search_link(fixed, opener, env) if fixed else None) or \
        confirmed_search_link(ev.get("venue") or "", opener, env)
    ev["map_url"] = link
    return "search_ok" if link else "search_unsure"


SEARCH_PREFIX = "https://map.naver.com/p/search/"


def recheck(store, dry_run: bool = False, opener=None, env=None) -> list:
    """노션의 모든 이벤트 지도 링크를 다시 확인한다 (D52).
    - 자동 검색 링크·빈칸: 확인되면 그 링크, 아니면 비움
    - 직원이 넣은 링크: 열리면 그대로, 안 열리면 알림만(지우지 않음)
    취소·완료 이벤트는 건너뛴다."""
    out = []
    for e in store.all_events():
        from . import business
        if e.get("status") in ("이벤트취소", "이벤트완료") or not (
                e.get("venue") or business.venue_of(e.get("product")) or business.map_url_of(e.get("product"))):
            continue
        old = e.get("map_url") or None
        item = {"title": e.get("title"), "url": e.get("url"), "old": old}
        if old and not old.startswith(SEARCH_PREFIX):
            item["result"] = "직원 링크 열림" if staff_link_ok(old, opener) else "직원 링크 안 열림(그대로 둠)"
            out.append(item)
            continue
        from . import business
        fixed = business.venue_of(e.get("product"))
        place = business.map_url_of(e.get("product"))
        if place and staff_link_ok(place, opener):  # 상품의 장소 링크가 있으면 그것으로
            new = place
        else:
            new = None
        new = new or (confirmed_search_link(fixed, opener, env) if fixed else None) or \
            confirmed_search_link(e.get("venue") or "", opener, env)
        if new == old:
            item["result"] = "확인됨(그대로)" if new else "확인 안 됨(빈칸 유지)"
        else:
            item["new"] = new
            item["result"] = "확인된 링크로 바꿈" if new else "확인 안 돼 지움"
            if not dry_run:
                store.set_map_url(e["id"], new)
        out.append(item)
    return out
