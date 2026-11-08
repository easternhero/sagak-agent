"""'고객 연결 필요'로 남은 상담의 추출 결과를 사람의 답이 올 때까지 보관한다.

고객 개인정보가 들어 있으므로 resolve가 끝나면 지운다.
기본 위치는 ~/.sagak/pending (sagak profile은 home_mode: profile이라 profile 폴더 안에 생긴다).
"""
from __future__ import annotations

import json
import os


def _dir() -> str:
    path = os.environ.get("SAGAK_PENDING_DIR") or os.path.join(os.path.expanduser("~"), ".sagak", "pending")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _path(consultation_id: str) -> str:
    return os.path.join(_dir(), consultation_id.replace("-", "") + ".json")


def save(consultation_id: str, record: dict, candidates: list) -> None:
    with open(_path(consultation_id), "w", encoding="utf-8") as f:
        json.dump({"record": record, "candidates": candidates}, f, ensure_ascii=False)
    os.chmod(_path(consultation_id), 0o600)


def load(consultation_id: str):
    try:
        with open(_path(consultation_id), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def delete(consultation_id: str) -> None:
    try:
        os.remove(_path(consultation_id))
    except FileNotFoundError:
        pass
