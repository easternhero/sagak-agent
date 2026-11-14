"""공개 데모 모드 (SAGAK_DEMO=1, D58·D60).

- 연락처는 가상 번호(010-0000-)만: 기록이 공개 노션에 올라가므로 실제 번호를 받지 않는다.
- 승인된 리뷰어가 보낸 상담은 상담자를 '리뷰어 #신청번호'로 기록한다. 보낸 사람은 Hermes가 명령 실행 환경에 넣어 주는
  HERMES_SESSION_ACTOR_ID / HERMES_SESSION_USER_ID로 알고, 신청 번호는 데모 승인 플러그인 상태 파일에서 찾는다.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional
from urllib.parse import urlparse

REVIEWER_PREFIX = "리뷰어 #"


def is_demo() -> bool:
    return bool(os.environ.get("SAGAK_DEMO"))


def _state_path() -> str:
    if os.environ.get("SAGAK_DEMO_STATE"):
        return os.environ["SAGAK_DEMO_STATE"]
    home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes/profiles/sagak-demo")
    return os.path.join(home, "sagak_demo_access.json")


def reviewer_label(user_id: Optional[str] = None) -> Optional[str]:
    """데모 봇에서 보낸 사람의 상담자 표시: 승인된 리뷰어 → '리뷰어 #3', 관리자 → SAGAK_DEMO_ADMIN_NAME(예: 판교춘자).
    데모가 아니거나 알 수 없으면 None(대화에서 뽑은 상담자를 씀)."""
    if not is_demo():
        return None
    uid = str(user_id or os.environ.get("HERMES_SESSION_ACTOR_ID") or os.environ.get("HERMES_SESSION_USER_ID") or "")
    if not uid:
        return None
    admins = [a.strip() for a in os.environ.get("SAGAK_DEMO_ADMIN_IDS", "").split(",") if a.strip()]
    if uid in admins and os.environ.get("SAGAK_DEMO_ADMIN_NAME"):
        return os.environ["SAGAK_DEMO_ADMIN_NAME"]
    try:
        with open(_state_path(), encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        return None
    for no, r in (state.get("requests") or {}).items():
        if str(r.get("user_id")) == uid and r.get("status") == "approved":
            return REVIEWER_PREFIX + str(no)
    return None


def is_reviewer_label(name: Optional[str]) -> bool:
    return bool(name) and name.startswith(REVIEWER_PREFIX)


NOTION_URL_RE = re.compile(r"https://(?:www\.)?notion\.so/(?:[^\s\"/]+/)?(?:[^\s\"/?]*-)?([0-9a-f]{32})(?:\?[^\s\"]*)?")


def public_links(obj: Any) -> Any:
    """데모 봇 답장 속 노션 링크(API가 주는 워크스페이스 편집 링크)를 게시 주소(notion.site)로 바꾼다.
    워크스페이스 링크는 리뷰어가 열 수 없다. 게시 주소의 호스트는 SAGAK_DEMO_NOTION_URL에서 가져온다."""
    if not is_demo():
        return obj
    host = urlparse(os.environ.get("SAGAK_DEMO_NOTION_URL", "")).netloc
    if not host.endswith("notion.site"):
        return obj

    def walk(v):
        if isinstance(v, str):
            return NOTION_URL_RE.sub(lambda m: "https://{}/{}".format(host, m.group(1)), v)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v
    return walk(obj)
