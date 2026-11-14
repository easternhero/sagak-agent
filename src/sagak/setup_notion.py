"""`sagak setup-notion --env <.env 경로>`: 노션 키로 볼 수 있는 DB 중 고객·이벤트(의뢰)·상담 이력·상품을 찾아
그 .env의 SAGAK_NOTION_*_DB 줄을 채운다. 키 값은 출력하지 않는다(DB ID만)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .notion import API, VERSION, NotionError

TITLES = {  # 노션 DB 제목 → .env 이름
    "고객": "SAGAK_NOTION_CUSTOMERS_DB",
    "이벤트 (의뢰)": "SAGAK_NOTION_EVENTS_DB",
    "상담 이력": "SAGAK_NOTION_CONSULTATIONS_DB",
    "상품": "SAGAK_NOTION_PRODUCTS_DB",
}


def read_env(path: str) -> dict:
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def write_env(path: str, values: dict) -> None:
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in values and not line.lstrip().startswith("#"):
            lines[i] = "{}={}".format(key, values[key])
            done.add(key)
    lines += ["{}={}".format(k, v) for k, v in values.items() if k not in done]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _search(token: str) -> list:
    found, cursor = [], None
    while True:
        body = {"filter": {"property": "object", "value": "database"}, "page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        req = urllib.request.Request(API + "/search", method="POST", data=json.dumps(body).encode("utf-8"),
                                     headers={"Authorization": "Bearer " + token, "Notion-Version": VERSION,
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise NotionError("노션 검색 실패 HTTP {} (키와 '연결' 추가를 확인)".format(e.code))
        found += data.get("results") or []
        if not data.get("has_more"):
            return found
        cursor = data.get("next_cursor")


SEEN: list = []  # 키로 보이는 DB 제목 (진단용)


def find(token: str) -> dict:
    """제목별 DB 후보 {제목: [id, ...]}"""
    out = {t: [] for t in TITLES}
    SEEN.clear()
    for db in _search(token):
        SEEN.append("".join(t.get("plain_text", "") for t in db.get("title") or []).strip() or "(제목 없음)")
        if db.get("archived") or db.get("in_trash"):
            continue
        title = "".join(t.get("plain_text", "") for t in db.get("title") or []).strip()
        if title in out:
            out[title].append(db["id"].replace("-", ""))
    return out


def run(env_path: str, dry_run: bool = False) -> dict:
    env_path = os.path.expanduser(env_path)
    token = read_env(env_path).get("NOTION_API_KEY") or os.environ.get("NOTION_API_KEY")
    if not token:
        raise NotionError(env_path + "에 NOTION_API_KEY가 없습니다")
    cands = find(token)
    values, problems = {}, []
    for title, ids in cands.items():
        if len(ids) == 1:
            values[TITLES[title]] = ids[0]
        else:
            problems.append("'{}' DB {}개 ({})".format(title, len(ids), "없음 — 연결을 추가했나요?" if not ids else "여러 개 — 하나만 남겨 주세요"))
    if not problems and not dry_run:
        write_env(env_path, values)
    out = {"found": values, "problems": problems, "written": bool(values) and not problems and not dry_run}
    if problems:
        out["visible_databases"] = SEEN[:30]
        if not SEEN:
            out["hint"] = ("이 키로 볼 수 있는 DB가 하나도 없어요. 노션에서 데모 홈 페이지 → ⋯ → 연결 → 이 키의 연결을 추가했는지, "
                           "연결(integration)을 데모 페이지와 같은 워크스페이스에서 만들었는지 확인해 주세요.")
    return out
