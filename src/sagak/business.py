"""업체별 설정(접수 브랜드, 상품명과 고객 안내 이름). 레포에는 예시만 두고 실제 값은 agent/business.json(커밋 안 함).

파일 위치: 환경변수 SAGAK_BUSINESS_FILE, 없으면 <레포>/agent/business.json. 파일이 없으면 빈 목록(상품·브랜드를 채우지 않음).
형식은 agent/business.example.json 참고.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_cache: dict = {}


def _key(text: str) -> str:
    return re.sub(r"[\s·&/()\-]", "", text or "")


def load(path: Optional[str] = None) -> dict:
    path = path or os.environ.get("SAGAK_BUSINESS_FILE") or os.path.join(ROOT, "agent", "business.json")
    if path in _cache:
        return _cache[path]
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        raw = {}
    products = [p["name"] for p in raw.get("products", []) if p.get("name")]
    aliases = {}
    for p in raw.get("products", []):
        for a in [p.get("name", "")] + list(p.get("aliases", [])):
            if a:
                aliases[_key(a)] = p["name"]
    groups = {}
    for g in raw.get("groups", []):  # 종류를 말하지 않으면 고를 수 없는 상품 묶음 (D45)
        for a in [g.get("name", "")] + list(g.get("aliases", [])):
            if a:
                groups[_key(a)] = {"name": g["name"], "choices": list(g.get("choices", [])), "theme": g.get("theme")}
    data = {"brands": list(raw.get("brands", [])), "products": products, "aliases": aliases, "groups": groups,
            "channels": dict(raw.get("channels", {})),
            "guide": {p["name"]: list(p.get("aliases", [])) for p in raw.get("products", []) if p.get("name")},
            "themes": {p["name"]: p["theme"] for p in raw.get("products", []) if p.get("name") and p.get("theme")}}
    _cache[path] = data
    return data


def product_of(value: Optional[str]) -> Optional[str]:
    """상품명 또는 고객 안내 이름 → 관리 페이지 상품명. 모르면 None."""
    if not value:
        return None
    return load()["aliases"].get(_key(value))


def group_of(value: Optional[str]) -> Optional[dict]:
    """'호텔 프로포즈'처럼 종류가 여럿인 상품 묶음 → {"name", "choices", "theme"}. 아니면 None."""
    if not value:
        return None
    return load()["groups"].get(_key(value))


def channels() -> dict:
    """접수 경로 표시: {"kakao": "...", "phone": "...", "homepage": "...", "smartstore": "..."} (D46)."""
    return load()["channels"]


def theme_of(product: Optional[str]) -> Optional[str]:
    """관리 페이지 상품명 → 업체 설정의 이벤트 테마. 설정이 없으면 None(추출값을 쓴다)."""
    if not product:
        return None
    return load().get("themes", {}).get(product)


def brand_of(value: Optional[str]) -> Optional[str]:
    """'네, OO 이벤트입니다'처럼 들은 브랜드 → 목록의 브랜드명. 모르면 None."""
    if not value:
        return None
    key = _key(value)
    hits = [b for b in load()["brands"] if _key(b) == key or _key(b) in key]
    return hits[0] if len(hits) == 1 else None
