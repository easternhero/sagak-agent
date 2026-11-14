"""사각사각 공개 데모 봇: 사용 신청 → 관리자 승인 (Hermes 플러그인).

- 허용되지 않은 사람이 데모 봇에 DM을 보내면(pre_gateway_dispatch, 인증 전) Hermes 기본 연결 코드 대신
  신청을 받는다: 리뷰어에게 "승인 대기", 관리자(allow_admin_from)에게 신청 정보 + 승인/거절 명령을 보낸다.
- /demo_approve [번호] · /demo_deny [번호] · /demo_requests 는 관리자만 쓴다
  (user_allowed_commands에 없으니 Hermes가 다른 사람은 막고, 여기서도 관리자 ID를 다시 확인한다).
- 승인은 Hermes 연결 저장소(PairingStore)에 코드를 만들고 바로 승인해 기록한다 — `hermes pairing approve`와 같은 결과.
- 보내기만 텔레그램 API로 직접 한다(받기는 게이트웨이가 함). 상태는 프로필 폴더 sagak_demo_access.json.
선택 환경변수: SAGAK_DEMO_NOTION_URL(데모 노션), SAGAK_DEMO_GUIDE_URL(가이드 페이지).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

PLATFORM = "telegram"
logger = logging.getLogger("sagak-demo-access")
REMIND_SECONDS = 600  # 대기 중인 사람이 또 말을 걸면 10분에 한 번만 다시 안내

_lock = threading.Lock()
_store_ref = {"store": None}


# ---- 설정·상태 -------------------------------------------------------------

PROFILE = "sagak-demo"  # 이 플러그인을 켠 프로필 (게이트웨이가 여러 프로필을 함께 돌려도 이 폴더를 씀)


def _home() -> Path:
    """데모 프로필 폴더. 테스트는 HERMES_HOME으로 바꾼다."""
    if os.environ.get("SAGAK_DEMO_HOME"):
        return Path(os.environ["SAGAK_DEMO_HOME"])
    try:
        from hermes_constants import get_default_hermes_root
        root = Path(get_default_hermes_root())
    except Exception:
        root = Path(os.path.expanduser("~/.hermes"))
    if root.name == PROFILE:
        return root
    if (root / "profiles" / PROFILE).is_dir():
        return root / "profiles" / PROFILE
    return root


def _env_file() -> dict:
    out = {}
    try:
        for line in (_home() / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def _setting(name: str) -> str:
    """데모 프로필 .env 값이 먼저 (한 게이트웨이가 여러 프로필을 돌리면 프로세스 환경변수는 다른 봇 것일 수 있음)."""
    return _env_file().get(name) or os.environ.get(name, "")


def _yaml_load(text: str):
    """Hermes는 PyYAML이 아니라 자체 hermes_yaml(ruamel)을 쓴다. 둘 다 시도."""
    try:
        from hermes_yaml import safe_load
    except ImportError:
        from yaml import safe_load
    return safe_load(text)


def admins() -> list:
    try:
        cfg = _yaml_load((_home() / "config.yaml").read_text(encoding="utf-8")) or {}
        ids = (((cfg.get("platforms") or {}).get(PLATFORM) or {}).get("extra") or {}).get("allow_admin_from") or []
        return [str(i) for i in ids]
    except Exception as e:
        logger.warning("sagak-demo-access: 관리자 목록을 읽지 못함 (%s: %s)", type(e).__name__, e)
        return []


def _state_path() -> Path:
    return _home() / "sagak_demo_access.json"


def load_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"next": 1, "requests": {}}


def save_state(state: dict) -> None:
    p = _state_path()
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def _find_user(state: dict, user_id: str):
    for no, r in state["requests"].items():
        if r["user_id"] == str(user_id):
            return no, r
    return None, None


# ---- 보내기 --------------------------------------------------------------

def send(chat_id: str, text: str) -> bool:
    token = _setting("TELEGRAM_BOT_TOKEN")
    if not token:
        return False
    body = json.dumps({"chat_id": chat_id, "text": text, "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request("https://api.telegram.org/bot{}/sendMessage".format(token), data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception:
        return False


def _links() -> str:
    lines = []
    if _setting("SAGAK_DEMO_NOTION_URL"):
        lines.append("데모 노션(결과 보기): " + _setting("SAGAK_DEMO_NOTION_URL"))
    if _setting("SAGAK_DEMO_GUIDE_URL"):
        lines.append("사용 가이드: " + _setting("SAGAK_DEMO_GUIDE_URL"))
    return ("\n\n" + "\n".join(lines)) if lines else ""


def _who(r: dict) -> str:
    return "{} (ID {})".format(r.get("name") or "이름 없음", r["user_id"])


MSG_RECEIVED = ("안녕하세요! 사각사각 데모 봇입니다 🙂\n사용 신청을 받았어요 (신청 #{no}).\n"
                "개발자가 승인하면 여기로 바로 알려 드릴게요. 보통 몇 분~몇 시간 걸려요.")
MSG_WAITING = "아직 승인 대기 중이에요 (신청 #{no}). 승인되면 바로 알려 드릴게요."
# 리뷰어마다 다른 가상 고객으로 예시를 보내 기록이 섞이지 않게 (D60). 번호는 010-0000-8xxx (데모 자료 7xxx와 겹치지 않음)
FAKE_NAMES = ["서도윤", "김하린", "이준서", "박지아", "최시우", "정예린", "강도현", "윤서윤", "장하준", "임채원",
              "오지호", "한유나", "신민재", "권소율", "황태윤", "송다인", "전우진", "고은서", "문시온", "배하람"]


def example_for(no: str):
    n = int(no)
    name = FAKE_NAMES[(n - 1) % len(FAKE_NAMES)]
    phone = "010-0000-8{:03d}".format(n % 1000)
    return name, phone


def approved_message(no: str) -> str:
    name, phone = example_for(no)
    return ("승인됐어요! 🎉 이제 사각사각 데모 봇을 쓸 수 있어요.\n\n"
            "1) /new 를 눌러 새 대화를 시작하고\n"
            "2) 아래 예시를 그대로 보내 보세요. 신청 #{no} 전용 가상 고객이에요.\n\n"
            "{name} / {phone}\n갤러리 프로포즈 문의. 12월 5일 토요일 저녁 7시, 장미 50송이 추가, 촬영도 원함. "
            "서프라이즈라 여자친구에게 연락 금지\n\n"
            "3) 이어서 이것도 보내 보세요. 같은 고객의 2차 상담으로 이어지고, 바뀐 내용은 덮어쓰지 않고 표시해요.\n\n"
            "{name} / {phone}\n2차 통화 메모: 장소를 레스토랑으로 바꿀 수 있는지 물어봄. 날짜는 아직 고민 중이라고 함.\n\n"
            "직접 쓴 상담이나 녹음 파일(m4a·mp3), 카카오톡 대화 내보내기(txt)도 보낼 수 있어요. "
            "기록은 공개 노션에 올라가니 실제 이름·연락처는 쓰지 말고, 연락처는 010-0000-으로 시작하는 가상 번호를 써 주세요. "
            "노션에서 상담자가 '리뷰어 #{no}'인 기록이 직접 보낸 거예요. "
            "다 해 본 뒤 내 기록을 지우려면 /demo_reset 을 보내 주세요.").format(no=no, name=name, phone=phone)


MSG_DENIED = "이번 데모 신청은 승인되지 않았어요. 데모 영상과 노션에서 결과를 볼 수 있어요."
MSG_ADMIN_NEW = ("🔔 사각사각 데모 사용 신청 #{no}\n{who}\n\n"
                 "승인: /demo_approve {no}\n거절: /demo_deny {no}\n목록: /demo_requests")


# ---- 신청 받기 (게이트웨이 인증 전) ---------------------------------------

def handle_unknown(user_id: str, name: str, chat_id: str, now: float = None, sender=send) -> str:
    """허용되지 않은 사람의 DM 하나 처리. 돌려주는 값: 'new' | 'remind' | 'quiet'."""
    now = now or time.time()
    with _lock:
        state = load_state()
        no, r = _find_user(state, user_id)
        if r is None:
            no = str(state["next"])
            state["next"] += 1
            r = {"user_id": str(user_id), "name": name or "", "chat_id": str(chat_id), "status": "pending",
                 "requested_at": now, "notified_at": now}
            state["requests"][no] = r
            save_state(state)
            sender(chat_id, MSG_RECEIVED.format(no=no) + _links())
            for a in admins():
                sender(a, MSG_ADMIN_NEW.format(no=no, who=_who(r)))
            return "new"
        if r["status"] == "pending" and now - r.get("notified_at", 0) >= REMIND_SECONDS:
            r["notified_at"] = now
            save_state(state)
            sender(chat_id, MSG_WAITING.format(no=no))
            return "remind"
        return "quiet"


async def on_pre_gateway_dispatch(event=None, gateway=None, **kwargs):
    source = getattr(event, "source", None)
    if source is None or getattr(source, "chat_type", "dm") != "dm" or not getattr(source, "user_id", None):
        return None
    platform = getattr(getattr(source, "platform", None), "value", str(getattr(source, "platform", "")))
    if platform != PLATFORM or getattr(source, "is_bot", False):
        return None
    try:
        if gateway is not None and gateway._is_user_authorized_for_source(source):
            return None
        if gateway is not None and _store_ref["store"] is None:
            _store_ref["store"] = gateway._pairing_store_for(source)
    except Exception:
        return None  # 판단할 수 없으면 Hermes 기본 동작에 맡긴다
    await asyncio.to_thread(handle_unknown, str(source.user_id), source.user_name or "", str(source.chat_id))
    return {"action": "skip", "reason": "sagak-demo-access"}


# ---- 관리자 명령 ---------------------------------------------------------

def _store():
    if _store_ref["store"] is None:
        from gateway.pairing import PairingStore
        _store_ref["store"] = PairingStore()
    return _store_ref["store"]


def grant(store, user_id: str, name: str) -> bool:
    """Hermes 연결 저장소에 승인 기록 (`hermes pairing approve`와 같은 결과)."""
    code = store.generate_code(PLATFORM, user_id, name)
    if code and store.approve_code(PLATFORM, code):
        return True
    with store._locked():  # 대기 한도·횟수 제한에 걸리면 바로 승인 목록에
        store._approve_user(PLATFORM, user_id, name)
    return store.is_approved(PLATFORM, user_id)


def _pick(state: dict, args: str):
    pending = {no: r for no, r in state["requests"].items() if r["status"] == "pending"}
    no = (args or "").strip().lstrip("#")
    if no:
        r = state["requests"].get(no)
        return (no, r, None) if r else (None, None, "신청 #{}이 없어요.".format(no))
    if len(pending) == 1:
        no = next(iter(pending))
        return no, pending[no], None
    return None, None, ("대기 중인 신청이 없어요." if not pending else
                        "대기 중인 신청이 여러 개예요. 번호를 붙여 주세요: " + ", ".join("#" + n for n in pending))


def _is_admin(kwargs) -> bool:
    """Hermes가 먼저 관리자만 통과시킨다(user_allowed_commands에 없음). 보낸 사람 정보가 오면 한 번 더 확인."""
    source = kwargs.get("source")
    uid = str(getattr(source, "user_id", "") or "")
    ids = admins()
    ok = (uid in ids) if (uid and ids) else True
    (logger.info if ok else logger.warning)("sagak-demo-access: 관리자 확인 ok=%s uid=%s admins=%s home=%s",
                                            ok, uid or "-", ids, _home())
    return ok


def decide(args: str, approve: bool, store=None, sender=send, admin_ok: bool = True) -> str:
    if not admin_ok:
        return "관리자만 쓸 수 있어요."
    with _lock:
        state = load_state()
        no, r, err = _pick(state, args)
        if err:
            return err
        if r["status"] != "pending":
            return "신청 #{}은 이미 {}됐어요.".format(no, "승인" if r["status"] == "approved" else "거절")
        if approve:
            if not grant(store or _store(), r["user_id"], r.get("name", "")):
                return "신청 #{} 승인 기록에 실패했어요. 터미널에서 hermes pairing list로 확인해 주세요.".format(no)
            r["status"] = "approved"
            msg = approved_message(no) + _links()
        else:
            r["status"] = "denied"
            msg = MSG_DENIED + _links()
        r["decided_at"] = time.time()
        save_state(state)
    sender(r["chat_id"], msg)
    return "신청 #{} {} — {}".format(no, "승인했어요 ✅" if approve else "거절했어요", _who(r))


def list_requests(admin_ok: bool = True) -> str:
    if not admin_ok:
        return "관리자만 쓸 수 있어요."
    state = load_state()
    if not state["requests"]:
        return "신청이 아직 없어요."
    label = {"pending": "대기", "approved": "승인", "denied": "거절"}
    rows = ["#{} {} · {} · {}".format(no, label.get(r["status"], r["status"]), _who(r),
                                      time.strftime("%m/%d %H:%M", time.localtime(r["requested_at"])))
            for no, r in sorted(state["requests"].items(), key=lambda kv: int(kv[0]))]
    return "\n".join(rows)


# ---- 데모 기록 정리 (관리자 전용 /demo_reset) -----------------------------

RESET_CONFIRM_SECONDS = 600
REPO = Path(__file__).resolve().parents[3]  # agent/plugins/sagak-demo-access/__init__.py → 레포 (심볼릭 링크를 따라감)


def _run_reset(dry_run: bool, only: str = None, everything: bool = False) -> dict:
    """`python3 -m sagak demo-reset`을 데모 프로필 .env 값으로 실행 (게이트웨이 환경변수에는 다른 봇 값이 섞일 수 있음)."""
    env = dict(os.environ)
    env.update(_env_file())
    env["PYTHONPATH"] = str(REPO / "src")
    cmd = [sys.executable, "-m", "sagak", "demo-reset"] + (["--dry-run"] if dry_run else []) + (["--only", only] if only else []) + (["--all"] if everything else [])
    out = subprocess.run(cmd, cwd=str(REPO), env=env, capture_output=True, text=True, timeout=180)
    try:
        return json.loads(out.stdout)
    except ValueError:
        return {"ok": False, "message": (out.stderr or out.stdout or "출력 없음")[-300:]}


def _summary(res: dict, limit: int = 8) -> str:
    lines = []
    for key, label in (("customers", "고객"), ("events", "이벤트"), ("consultations", "상담")):
        items = res.get(key) or []
        head = ", ".join(items[:limit]) + (" 외 {}건".format(len(items) - limit) if len(items) > limit else "")
        lines.append("{} {}건{}".format(label, len(items), (": " + head) if items else ""))
    return "\n".join(lines)


def demo_reset(args: str = "", user_id: str = "", admin: bool = False, runner=_run_reset, now: float = None) -> str:
    """'/demo_reset' → 지울 목록 미리 보기, 10분 안에 '/demo_reset 확인' → 휴지통으로.
    리뷰어는 자기 기록('리뷰어 #번호')만, 관리자는 기본 예시만 남기고 전부(데모를 처음 상태로) (D61)."""
    now = now or time.time()
    uid = str(user_id or "")
    with _lock:
        state = load_state()
        only = None
        if not admin:
            no, r = _find_user(state, uid)
            if not r or r.get("status") != "approved":
                return "승인된 데모 사용자만 쓸 수 있어요."
            only = "리뷰어 #" + no
        asked = state.setdefault("reset_asked", {})
        confirm = (args or "").strip() in ("확인", "yes", "y")
        if confirm and now - asked.get(uid, 0) > RESET_CONFIRM_SECONDS:
            return "먼저 /demo_reset 으로 지울 목록을 확인해 주세요 (확인은 10분 안에)."
        asked[uid] = 0 if confirm else now
        save_state(state)
    res = runner(dry_run=not confirm, only=only, everything=admin)
    if not res.get("ok"):
        return "정리하지 못했어요: " + str(res.get("message") or res.get("error") or "알 수 없는 오류")
    whose = "내({})".format(only) if only else "기본 예시를 뺀 모든"
    if not any(res.get(k) for k in ("customers", "events", "consultations")):
        return "지울 {} 기록이 없어요.".format(whose)
    if confirm:
        return "{} 기록을 휴지통으로 보냈어요.\n{}".format(whose, _summary(res))
    keep = "기본 예시와 다른 사람 기록은 남아요." if only else "처음 넣어 둔 기본 예시만 남아요 (관리자 기록도 지워져요)."
    return ("{} 기록 정리 미리 보기 — {}\n{}\n\n지우려면 10분 안에 /demo_reset 확인 을 보내 주세요."
            .format(whose, keep, _summary(res)))


def _uid(kw) -> str:
    return str(getattr(kw.get("source"), "user_id", "") or "")


def register(ctx) -> None:
    ctx.register_hook("pre_gateway_dispatch", on_pre_gateway_dispatch)
    ctx.register_command("demo-approve", lambda raw_args="", **kw: decide(raw_args, True, admin_ok=_is_admin(kw)),
                         description="데모 사용 신청 승인 (관리자)", args_hint="<번호>")
    ctx.register_command("demo-deny", lambda raw_args="", **kw: decide(raw_args, False, admin_ok=_is_admin(kw)),
                         description="데모 사용 신청 거절 (관리자)", args_hint="<번호>")
    ctx.register_command("demo-reset",
                         lambda raw_args="", **kw: demo_reset(raw_args, user_id=_uid(kw), admin=_uid(kw) in admins()),
                         description="내가 남긴 데모 기록 정리 (확인 후 휴지통)", args_hint="[확인]")
    ctx.register_command("demo-requests", lambda raw_args="", **kw: list_requests(admin_ok=_is_admin(kw)),
                         description="데모 사용 신청 목록 (관리자)")
