"""공개 데모 모드 (SAGAK_DEMO=1, D58·D60).

- 연락처는 가상 번호(010-0000-)만: 기록이 공개 노션에 올라가므로 실제 번호를 받지 않는다.
- 승인된 리뷰어가 보낸 상담은 상담자를 '리뷰어 #신청번호'로 기록한다. 보낸 사람은 Hermes가 명령 실행 환경에 넣어 주는
  HERMES_SESSION_ACTOR_ID / HERMES_SESSION_USER_ID로 알고, 신청 번호는 데모 승인 플러그인 상태 파일에서 찾는다.
"""
from __future__ import annotations

import json
import os
from typing import Optional

REVIEWER_PREFIX = "리뷰어 #"


def is_demo() -> bool:
    return bool(os.environ.get("SAGAK_DEMO"))


def _state_path() -> str:
    if os.environ.get("SAGAK_DEMO_STATE"):
        return os.environ["SAGAK_DEMO_STATE"]
    home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes/profiles/sagak-demo")
    return os.path.join(home, "sagak_demo_access.json")


def reviewer_label(user_id: Optional[str] = None) -> Optional[str]:
    """보낸 사람이 승인된 데모 리뷰어면 '리뷰어 #3', 아니면(관리자·직원) None."""
    if not is_demo():
        return None
    uid = str(user_id or os.environ.get("HERMES_SESSION_ACTOR_ID") or os.environ.get("HERMES_SESSION_USER_ID") or "")
    if not uid:
        return None
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
