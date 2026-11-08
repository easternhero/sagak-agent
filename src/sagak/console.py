"""개발자 PC에서 띄우는 작은 발송 화면 (D27-B).  python3 -m sagak console [--port 8765]

agent/CHANGES.md 중 아직 안 보낸 안내를 보여 주고, 고쳐서 미리 보기(dry-run)·보내기를 한다.
아래 칸에서는 요청·공지를 그대로(머리말·버튼 없이) 보낸다(notify). 변경 안내 보낸 기록과는 무관.
127.0.0.1에서만 열리고, 페이지에 심은 일회용 토큰과 Host 확인으로 다른 사이트의 요청을 막는다.
"""
from __future__ import annotations

import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from . import announce as an

PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>사각사각 안내·알림 보내기</title>
<style>
:root{--bg:#f6f7f9;--surface:#fff;--surface-2:#eceef2;--fg:#1b1f24;--muted:#5d6675;--line:#dde1e7;--accent:#2d55c9;--ok:#1f7a4d;--bad:#b42318;
--font:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--surface:#1c2027;--surface-2:#252a33;--fg:#e8ebf0;--muted:#9aa3b2;--line:#2f3540;--accent:#8aa6f5;--ok:#5cc28f;--bad:#f2867a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 var(--font)}
.wrap{max-width:1000px;margin:0 auto;padding:28px 16px 60px}h1{font-size:24px;margin:0 0 6px}.lede{color:var(--muted);margin:0 0 18px}
.grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px}@media(max-width:720px){.grid{grid-template-columns:minmax(0,1fr)}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px;display:flex;flex-direction:column;gap:10px;min-width:0}
h2{font-size:16px;margin:0}.muted{color:var(--muted);font-size:13px;margin:0}
textarea{font:inherit;font-size:14px;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;width:100%;min-height:220px;resize:vertical}
.actions{display:flex;gap:8px;flex-wrap:wrap}button{font:inherit;font-size:14px;font-weight:600;border-radius:8px;padding:8px 14px;border:1px solid var(--line);background:var(--surface);color:var(--fg);cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:var(--surface)}button.danger{background:var(--bad);border-color:var(--bad);color:#fff}button:disabled{opacity:.5;cursor:not-allowed}
.who{font-size:12px;color:var(--muted)}.bubble{background:var(--surface-2);border-radius:12px 12px 12px 4px;padding:10px 12px;font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}
.key{text-align:center;font-size:13px;font-weight:600;padding:6px;border-radius:8px;border:1px solid var(--line);color:var(--accent)}
.msg{display:flex;flex-direction:column;gap:6px}h1.sub{font-size:20px;margin:34px 0 6px}select{font:inherit;font-size:14px;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:7px 10px}
#ntext{min-height:150px}.status{font-size:14px;padding:10px 12px;border-radius:8px;background:var(--surface-2)}.status.ok{color:var(--ok)}.status.bad{color:var(--bad)}
</style></head><body><div class="wrap">
<h1>사각사각 안내 보내기</h1>
<p class="lede">봇이 바뀐 점을 알리고 [/new] 버튼을 띄웁니다. ① 관리자에게 먼저 보내 [/restart]·[/new]로 잘 되는지 확인한 뒤 ② 직원에게 보내세요. 줄 끝에 [restart]가 있으면 관리자에게만 [/restart] 버튼이 갑니다. 이 화면은 이 개발자 PC에서만 열립니다.</p>
<div class="grid">
 <div class="card"><h2>안내 문구</h2><p class="muted" id="meta"></p>
  <textarea id="text" aria-label="안내 문구, 한 줄에 하나"></textarea>
  <div class="actions"><button class="primary" id="send-admin">① 관리자에게 보내기</button><button class="primary" id="send-others">② 직원에게 보내기</button></div>
  <div class="actions"><button id="dry">미리 보기(발송 안 함)</button><button id="reload">다시 불러오기</button></div>
  <p class="muted" id="flow"></p>
  <div class="status" id="status" hidden></div></div>
 <div class="card"><h2>텔레그램에 보이는 모습</h2><div id="preview" class="msg"></div></div>
</div>
<h1 class="sub">요청·공지 보내기</h1>
<p class="lede">봇 변경과 상관없는 부탁이나 공지를 적은 그대로 보냅니다. 머리말과 버튼이 붙지 않고, 위의 변경 안내 기록에도 영향이 없습니다.</p>
<div class="grid">
 <div class="card"><h2>보낼 내용</h2>
  <label class="muted" for="nto">받는 사람</label>
  <select id="nto"><option value="others">직원(관리자 제외)</option><option value="admin">관리자만(시험용)</option><option value="all">모두</option></select>
  <textarea id="ntext" aria-label="요청·공지 내용" placeholder="예) 📍 부탁드려요&#10;○○ 장소의 네이버 지도 공유 링크를 보내 주세요."></textarea>
  <div class="actions"><button class="primary" id="nsend">보내기</button><button id="ndry">미리 보기(발송 안 함)</button></div>
  <div class="status" id="nstatus" hidden></div></div>
 <div class="card"><h2>텔레그램에 보이는 모습</h2><div id="npreview" class="msg"></div></div>
</div></div>
<script>
const TOKEN="__TOKEN__";const $=id=>document.getElementById(id);const RESTART="[restart]";let armed=null,info={};
const lines=t=>t.split("\n").map(l=>l.replace(/^\s*[-•*]\s*/,"").trim()).filter(l=>l&&!l.startsWith("#"));
function preview(){const ls=lines($("text").value),box=$("preview");box.replaceChildren();
 if(!ls.length){box.textContent="보낼 안내가 없어요.";return}
 const restart=ls.some(l=>l.includes(RESTART));const head="🆕 사각사각 봇이 바뀌었어요\n\n"+ls.map(l=>"• "+l.replace(RESTART,"").trim()).join("\n")+"\n\n";
 const tail=" 진행 중인 확인(같은 고객인가요? 등)이 있으면 끝낸 뒤 눌러 주세요.";
 const n=info.users||0;const ms=[{who:"② 직원 "+Math.max(n-1,0)+"명"+(restart?"":" (① 관리자도 같은 내용)"),text:head+"아래 [/new] 버튼을 누르면 적용돼요."+tail,keys:["/new"]}];
 if(restart)ms.unshift({who:"① 관리자",text:head+"봇 전체 재시작이 필요해요. [/restart]를 먼저 누르고, 재시작 뒤 [/new]를 눌러 주세요."+tail,keys:["/restart","/new"]});
 ms.forEach(m=>{const d=document.createElement("div");d.className="msg";const w=document.createElement("div");w.className="who";w.textContent=m.who;const b=document.createElement("div");b.className="bubble";b.textContent=m.text;d.append(w,b);m.keys.forEach(k=>{const e=document.createElement("div");e.className="key";e.textContent=k;d.append(e)});box.append(d)});disarm()}
function status(t,c){const s=$("status");s.hidden=false;s.className="status "+(c||"");s.textContent=t}
const LABEL={admin:"① 관리자에게 보내기",others:"② 직원에게 보내기"};
function disarm(){armed=null;["admin","others"].forEach(a=>{$("send-"+a).textContent=LABEL[a];$("send-"+a).className="primary"})}
async function api(path,body){const r=await fetch(path,{method:body?"POST":"GET",headers:{"X-Sagak-Token":TOKEN,"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined});return r.json()}
async function load(){try{info=await api("/api/state");$("text").value=info.lines.map(l=>"- "+l).join("\n");
 $("meta").textContent=info.lines.length?"아직 안 보낸 안내 "+info.lines.length+"줄 (agent/CHANGES.md)":"새 안내가 없어요. 직접 적어서 보낼 수도 있어요.";
 $("flow").textContent="관리자: "+(info.admin.length?"안 보낸 안내 "+info.admin.length+"줄":"모두 보냄")+" · 직원: "+(info.others.length?"안 보낸 안내 "+info.others.length+"줄":"모두 보냄");
 if(info.warning)status(info.warning,"bad");else $("status").hidden=true;preview()}catch(e){status("불러오지 못했어요: "+e,"bad")}}
$("text").addEventListener("input",preview);$("reload").onclick=load;
$("dry").onclick=async()=>{const r=await api("/api/send",{text:$("text").value,dry_run:true});status(r.ok?"미리 보기 확인: "+(r.preview||[]).length+"명에게 갈 예정 (보내지 않음)":"실패: "+r.message,r.ok?"ok":"bad")};
["admin","others"].forEach(to=>{$("send-"+to).onclick=async()=>{if(!lines($("text").value).length){status("보낼 안내가 없어요.","bad");return}
 const n=to==="admin"?1:Math.max((info.users||1)-1,0);
 if(armed!==to){disarm();armed=to;const early=to==="others"&&info.admin.length>0;
  $("send-"+to).textContent=early?"관리자 확인 전이에요. 그래도 보내기 ("+n+"명)":"정말 보내기 ("+n+"명)";$("send-"+to).className="danger";return}
 $("send-"+to).disabled=true;try{const r=await api("/api/send",{text:$("text").value,to});
  status(r.ok?(to==="admin"?"관리자에게 보냈어요. 텔레그램에서 [/restart]·[/new]를 눌러 확인한 뒤 ② 직원에게 보내세요.":r.sent+"명의 직원에게 보냈어요."):"실패: "+r.message,r.ok?"ok":"bad");
  if(r.ok){const t=$("text").value;await load();$("text").value=t;preview()}}finally{$("send-"+to).disabled=false;disarm()}}});
const NWHO={others:"직원",admin:"관리자",all:"모두"};let narmed=false;
function nstatus(t,c){const s=$("nstatus");s.hidden=false;s.className="status "+(c||"");s.textContent=t}
function ncount(){const n=info.users||0,to=$("nto").value;return to==="admin"?1:to==="all"?n:Math.max(n-1,0)}
function npreview(){const box=$("npreview");box.replaceChildren();const t=$("ntext").value.trim();
 if(!t){box.textContent="보낼 내용을 적어 주세요.";ndisarm();return}
 const d=document.createElement("div");d.className="msg";const w=document.createElement("div");w.className="who";w.textContent=NWHO[$("nto").value]+" "+ncount()+"명";
 const b=document.createElement("div");b.className="bubble";b.textContent=t;d.append(w,b);box.append(d);ndisarm()}
function ndisarm(){narmed=false;$("nsend").textContent="보내기";$("nsend").className="primary"}
$("ntext").addEventListener("input",npreview);$("nto").addEventListener("change",npreview);
$("ndry").onclick=async()=>{const r=await api("/api/notify",{text:$("ntext").value,to:$("nto").value,dry_run:true});
 nstatus(r.ok?"미리 보기 확인: "+r.count+"명에게 갈 예정 (보내지 않음)":"실패: "+r.message,r.ok?"ok":"bad")};
$("nsend").onclick=async()=>{if(!$("ntext").value.trim()){nstatus("보낼 내용이 없어요.","bad");return}
 if(!narmed){narmed=true;$("nsend").textContent="정말 보내기 ("+NWHO[$("nto").value]+" "+ncount()+"명)";$("nsend").className="danger";return}
 $("nsend").disabled=true;try{const r=await api("/api/notify",{text:$("ntext").value,to:$("nto").value});
  nstatus(r.ok?r.sent+"명에게 보냈어요.":"실패: "+r.message,r.ok?"ok":"bad");if(r.ok){$("ntext").value="";npreview()}}finally{$("nsend").disabled=false;ndisarm()}};
load().then(npreview);
</script></body></html>"""


def state(env_path: Optional[str] = None) -> dict:
    env_path = env_path or an.DEFAULT_ENV
    env = an.load_env(env_path)
    users = [u for u in env.get("TELEGRAM_ALLOWED_USERS", "").split(",") if u.strip()]
    pend = an.pending_for(env_path)
    return {"ok": True, "admin": pend["admin"], "others": pend["others"],
            "lines": pend["admin"] or pend["others"], "users": len(users), "warning": an.soul_warning(env_path)}


def make_handler(token: str, port: int, env_path: Optional[str] = None, send=an.announce, notify=an.notify):
    hosts = {"127.0.0.1:{}".format(port), "localhost:{}".format(port)}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # 터미널을 조용히
            pass

        def _reply(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj: dict, code: int = 200) -> None:
            self._reply(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _allowed(self, api: bool) -> bool:
            if self.headers.get("Host") not in hosts:  # DNS rebinding 방지
                return False
            return not api or secrets.compare_digest(self.headers.get("X-Sagak-Token", ""), token)

        def do_GET(self):
            if not self._allowed(self.path.startswith("/api/")):
                return self._json({"ok": False, "message": "허용되지 않은 요청"}, 403)
            if self.path == "/":
                return self._reply(200, PAGE.replace("__TOKEN__", token).encode("utf-8"), "text/html; charset=utf-8")
            if self.path == "/api/state":
                return self._json(state(env_path))
            return self._json({"ok": False, "message": "없음"}, 404)

        def do_POST(self):
            if self.path not in ("/api/send", "/api/notify") or not self._allowed(True):
                return self._json({"ok": False, "message": "허용되지 않은 요청"}, 403)
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                if self.path == "/api/notify":  # 요청·공지: 적은 그대로, 기본 직원에게
                    out = notify(str(body.get("text") or ""), to=str(body.get("to") or "others"),
                                 dry_run=bool(body.get("dry_run")), env_path=env_path)
                    return self._json({"ok": True, **out})
                out = send(dry_run=bool(body.get("dry_run")), env_path=env_path, text=str(body.get("text") or ""),
                           to=str(body.get("to") or "all"))
                return self._json({"ok": True, **out})
            except (an.AnnounceError, ValueError, OSError) as e:
                return self._json({"ok": False, "message": str(e)})

    return Handler


def serve(port: int = 8765, env_path: Optional[str] = None, open_browser: bool = True) -> None:
    token = secrets.token_urlsafe(24)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(token, port, env_path))
    url = "http://127.0.0.1:{}/".format(port)
    print("사각사각 안내·알림 보내기: " + url + "  (끄기: Ctrl+C)")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
