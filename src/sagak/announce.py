"""봇 변경 안내를 텔레그램으로 보낸다 (D26). 맥에서 관리자이 직접 실행.

agent/CHANGES.md의 안내 줄 중 아직 보내지 않은 것을 허용된 사용자에게 보내고,
'답장 키보드'로 [/new] 버튼을 띄운다. 버튼을 누르면 '/new' 글자가 메시지로 가서 Hermes가 그대로 처리한다.
`[restart]`가 붙은 줄이 있으면 관리자에게만 [/restart] 버튼도 띄운다(봇 전체 재시작).
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHANGES = os.path.join(ROOT, "agent", "CHANGES.md")
DEFAULT_ENV = os.path.expanduser("~/.hermes/profiles/sagak/.env")
RESTART_TAG = "[restart]"


class AnnounceError(Exception):
    pass


def read_lines(path: str = CHANGES) -> list:
    """안내 줄('- '로 시작) 목록. 위가 최신."""
    with open(path, encoding="utf-8") as f:
        return [m.group(1).strip() for m in (re.match(r"^- (.+)$", l) for l in f) if m]


def unsent(lines: list, last: Optional[str]) -> list:
    """지난번에 보낸 맨 위 줄보다 위에 있는 줄 = 새 안내."""
    if last is None:
        return lines
    return lines[:lines.index(last)] if last in lines else lines


def _state_path(env_path: str) -> str:
    """보낸 위치 기록. 기본은 프로필 폴더(.env 옆) — 준비 보드 동기화 때 읽을 수 있게."""
    base = os.environ.get("SAGAK_STATE_DIR") or os.path.dirname(os.path.abspath(env_path))
    return os.path.join(base, "sagak_announced.json")


AUDIENCES = ("admin", "others")  # 관리자 / 나머지 직원 — 보낸 위치를 따로 기록한다


def _load_state(env_path: str) -> dict:
    try:
        with open(_state_path(env_path), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if "top" in data:  # 예전 형식: 모두에게 보낸 위치 하나
        return {a: data["top"] for a in AUDIENCES}
    return data


def load_last(env_path: str = DEFAULT_ENV, audience: str = "others") -> Optional[str]:
    return _load_state(env_path).get(audience)


def save_last(top: str, env_path: str = DEFAULT_ENV, audiences=AUDIENCES) -> None:
    state = _load_state(env_path)
    state.update({a: top for a in audiences})
    path = _state_path(env_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def pending_for(env_path: str, changes: str = CHANGES) -> dict:
    """받는 쪽별로 아직 안 보낸 안내."""
    lines = read_lines(changes)
    return {a: unsent(lines, load_last(env_path, a)) for a in AUDIENCES}


def load_env(path: str) -> dict:
    """KEY=VALUE 파일을 읽는다. 값은 출력하지 않는다. 이미 환경변수에 있으면 그것이 우선."""
    env = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$", line)
                if m:
                    env[m.group(1)] = m.group(2).strip("'\"")
    except OSError:
        pass
    env.update({k: v for k, v in os.environ.items() if k.startswith(("TELEGRAM_", "SAGAK_"))})
    return env


def build_messages(lines: list, users: list, admin: str) -> list:
    """[(chat_id, text, 버튼 목록)]"""
    needs_restart = any(RESTART_TAG in l for l in lines)
    body = "\n".join("• " + l.replace(RESTART_TAG, "").strip() for l in lines)
    text = ("🆕 사각사각 봇이 바뀌었어요\n\n" + body +
            "\n\n아래 [/new] 버튼을 누르면 적용돼요. 진행 중인 확인(같은 고객인가요? 등)이 있으면 끝낸 뒤 눌러 주세요.")
    out = []
    for u in users:
        if u == admin and needs_restart:
            out.append((u, text.replace("아래 [/new] 버튼을 누르면 적용돼요.",
                                        "봇 전체 재시작이 필요해요. [/restart]를 먼저 누르고, 재시작 뒤 [/new]를 눌러 주세요."),
                        ["/restart", "/new"]))
        else:
            out.append((u, text, ["/new"]))
    return out


def send(token: str, chat_id: str, text: str, buttons: list, opener=None) -> None:
    body = {"chat_id": chat_id, "text": text,
            "reply_markup": {"keyboard": [[{"text": b}] for b in buttons],
                             "one_time_keyboard": True, "resize_keyboard": True}}
    req = urllib.request.Request("https://api.telegram.org/bot{}/sendMessage".format(token),
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with (opener or urllib.request.urlopen)(req, timeout=20) as resp:
            if not json.loads(resp.read().decode("utf-8")).get("ok"):
                raise AnnounceError("텔레그램 전송 실패")
    except urllib.error.HTTPError as e:  # URL에 토큰이 있으므로 코드만 남긴다
        raise AnnounceError("텔레그램 전송 실패 (HTTP {})".format(e.code)) from None
    except urllib.error.URLError as e:
        raise AnnounceError("텔레그램 연결 실패: {}".format(e.reason)) from None


def soul_warning(env_path: str) -> Optional[str]:
    """레포 SOUL.md와 프로필 SOUL.md가 다르면 알려 준다 (프로필은 복사본)."""
    profile = os.path.join(os.path.dirname(env_path), "SOUL.md")
    try:
        with open(os.path.join(ROOT, "agent", "SOUL.md"), encoding="utf-8") as a, open(profile, encoding="utf-8") as b:
            if a.read() != b.read():
                return "agent/SOUL.md가 프로필 SOUL.md와 다릅니다. 복사한 뒤 /new 하세요: cp agent/SOUL.md " + profile
    except OSError:
        return None
    return None


def parse_text(text: str) -> list:
    """보드에서 편집한 안내(한 줄에 하나, 앞의 '- '·'• '는 있어도 됨)."""
    return [re.sub(r"^[-•*]\s*", "", l).strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]


def announce(dry_run: bool = False, env_path: Optional[str] = None, opener=None, changes: str = CHANGES,
             text: Optional[str] = None, to: str = "all") -> dict:
    """to: admin(관리자만) | others(나머지 직원만) | all.
    text를 주면(편집한 안내) 그 내용을 보내고, CHANGES.md의 새 줄은 받은 쪽에 보낸 것으로 표시한다."""
    if to not in ("admin", "others", "all"):
        raise AnnounceError("받는 쪽은 admin, others, all 중 하나입니다.")
    env_path = env_path or os.environ.get("SAGAK_ENV_FILE") or DEFAULT_ENV
    env = load_env(env_path)
    audiences = AUDIENCES if to == "all" else (to,)
    pend = pending_for(env_path, changes)
    pending_lines = max((pend[a] for a in audiences), key=len)
    lines = parse_text(text) if text is not None else pending_lines
    out = {"lines": lines, "warning": soul_warning(env_path)}
    if not lines:
        return dict(out, sent=0, message="새 안내가 없습니다.")
    users = [u.strip() for u in env.get("TELEGRAM_ALLOWED_USERS", "").split(",") if u.strip()]
    if not users:
        raise AnnounceError("TELEGRAM_ALLOWED_USERS가 비어 있습니다.")
    admin = env.get("SAGAK_TELEGRAM_ADMIN") or users[0]
    targets = [u for u in users if (to == "all") or ((u == admin) == (to == "admin"))]
    if not targets:
        raise AnnounceError("보낼 사람이 없습니다.")
    messages = build_messages(lines, targets, admin)
    if dry_run:
        return dict(out, sent=0, dry_run=True, preview=[{"to": "관리자" if m[0] == admin else "사용자", "text": m[1],
                                                         "buttons": m[2]} for m in messages])
    token = env.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise AnnounceError("TELEGRAM_BOT_TOKEN이 없습니다.")
    for chat_id, text, buttons in messages:
        send(token, chat_id, text, buttons, opener)
    if pending_lines:
        save_last(pending_lines[0], env_path, audiences)
    return dict(out, sent=len(messages), to=to)
