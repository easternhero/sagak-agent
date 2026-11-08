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
    if len(same) != 1:
        return None
    place = same[0]
    title = re.sub(r"</?b>", "", place.get("title") or "")
    return naver_search_url("{} {}".format(title, place.get("roadAddress") or place.get("address") or "").strip())


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
    link = confirmed_search_link(ev.get("venue") or "", opener, env)
    ev["map_url"] = link
    return "search_ok" if link else "search_unsure"
