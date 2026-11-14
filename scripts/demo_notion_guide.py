"""공개 데모용 '사각사각 데모 가이드' 노션 페이지를 채운다 (개발자 PC에서 한 번).

쓰는 법 (권장: 빈 가이드 페이지를 맨 위에 만들고 데모 홈을 그 아래로 옮긴 뒤):
  PYTHONPATH=src python3 scripts/demo_notion_guide.py --env ~/.hermes/profiles/sagak-demo/.env \
      --into <빈 가이드 페이지 링크> --home <데모 홈 링크> [--public <게시된 데모 홈 주소>] [--video <영상 링크>]
  --into 없이 쓰면 데모 홈 아래에 가이드 하위 페이지를 새로 만들고 홈 맨 위에 링크를 넣는다.

- 데모 홈에 연결된 노션 키(.env의 NOTION_API_KEY)로 쓴다. 홈이 웹에 게시돼 있으면 가이드도 함께 공개된다.
- demo/kakao-chat.txt, demo/call-recording.m4a(있으면)를 첨부해 리뷰어가 내려받아 봇에 보낼 수 있게 한다.
- 데모 홈 맨 위 안내 바로 아래에 가이드 링크를 넣는다. 같은 제목의 가이드가 이미 있으면 만들지 않는다.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from sagak.notion import NotionStore  # noqa: E402
from sagak.setup_notion import read_env  # noqa: E402

TITLE = "사각사각 데모 가이드"
BOT = "https://t.me/sagak_demo_bot"
REPO = "https://github.com/easternhero/sagak-agent"
EX_NEW = ("한지우 / 010-0000-7001\n갤러리 프로포즈 문의. 12월 5일 토요일 저녁 7시, 장미 50송이 추가, 촬영도 원함. "
          "서프라이즈라 여자친구에게 연락 금지")
EX_FOLLOW = "한지우 / 010-0000-7001\n2차 통화 메모: 장소를 레스토랑으로 바꿀 수 있는지 물어봄. 날짜는 아직 고민 중이라고 함."
EX_OFF = "오늘 서울 날씨 어때?"
EX_HELLO = "안녕하세요"
EX_MINE_NEW = ("서도윤 / 010-0000-8001\n갤러리 프로포즈 문의. 12월 5일 토요일 저녁 7시, 장미 50송이 추가, 촬영도 원함. "
               "서프라이즈라 여자친구에게 연락 금지")
EX_MINE_FOLLOW = "서도윤 / 010-0000-8001\n2차 통화 메모: 장소를 레스토랑으로 바꿀 수 있는지 물어봄. 날짜는 아직 고민 중이라고 함."
EX_SAME = "서도연 / 010-0000-8001\n예약 날짜 다시 확인하고 싶다고 전화 옴"
EX_CALL_CAPTION = "강민준 / 010-0000-7003"
MINE_NOTE = "아래는 신청 #1 예시예요. 승인 안내에 온 내 전용 이름·번호로 바꿔서 보내 주세요."
EX_REAL = "홍길동 / 010-1234-5678\n호텔 프로포즈 문의"


def t(text, link=None, bold=False, code=False):
    r = {"type": "text", "text": {"content": text}}
    if link:
        r["text"]["link"] = {"url": link}
    if bold or code:
        r["annotations"] = {"bold": bold, "code": code}
    return r


def para(*rich):
    return {"type": "paragraph", "paragraph": {"rich_text": list(rich)}}


def h2(text):
    return {"type": "heading_2", "heading_2": {"rich_text": [t(text)]}}


def num(*rich, children=None):
    item = {"type": "numbered_list_item", "numbered_list_item": {"rich_text": list(rich)}}
    if children:
        item["numbered_list_item"]["children"] = children  # 코드 블록을 안에 넣어야 번호가 이어진다
    return item


def bullet(*rich):
    return {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": list(rich)}}


def code(text, lang="plain text"):
    return {"type": "code", "code": {"rich_text": [t(text)], "language": lang}}


def callout(emoji, color, *rich):
    return {"type": "callout", "callout": {"rich_text": list(rich), "icon": {"type": "emoji", "emoji": emoji},
                                           "color": color}}


def divider():
    return {"type": "divider", "divider": {}}


def file_block(upload_id, caption):
    return {"type": "file", "file": {"type": "file_upload", "file_upload": {"id": upload_id},
                                     "caption": [t(caption)]}}


SCRIPT_TOGGLE = "📄 통화 대본 보기"


def script_toggle():
    """통화 녹음 바로 아래에 둘 대본 토글 (demo/call-script.txt)."""
    path = os.path.join(ROOT, "demo", "call-script.txt")
    lines = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            who, _, text = line.strip().partition("|")
            if text:
                lines.append(para(t(who + ": ", bold=True), t(text)))
    return {"type": "toggle", "toggle": {"rich_text": [t(SCRIPT_TOGGLE)], "children": lines}}


def page_id(text: str) -> str:
    m = re.search(r"([0-9a-f]{32})", text.replace("-", ""))
    if not m:
        sys.exit("데모 홈 링크에서 페이지 ID를 찾지 못했어요: " + text)
    return m.group(1)


def blocks(home_url, video, chat_id, audio_id):
    out = [
        callout("💐", "pink_background",
                t("사각사각", bold=True),
                t("은 이벤트 회사 직원이 상담 녹음·채팅을 텔레그램 봇에 보내면, 노션 고객 보드에 고객 · 이벤트 · 상담 이력으로 "
                  "정리해 주는 AI 에이전트예요. 이 데모는 가상 업체 ‘설렘 이벤트’와 가상 고객으로 돌아가요.")),
        para(t("녹음·대화 보내기 → 전사·내용 정리 → 같은 고객 찾기 → 노션 기록 → 확인할 것 답장", bold=True)),
        divider(),
        h2("1. 1분 만에 보기"),
        para(t("봇이 정리한 결과가 쌓여 있는 데모 홈(가상 업체 ‘설렘 이벤트’)을 둘러보세요. "),
             t("고객 → 이벤트 → 상담 이력", bold=True),
             t(" 순서로 열면 근거 문장, 녹음 클립, 전사 원문까지 볼 수 있어요.")),
        bullet(t("결과 보기: 설렘 이벤트 홈 (데모)", link=home_url, bold=True)),
        bullet(t("시연 영상", link=video) if video else t("시연 영상: 곧 올라와요")),
        bullet(t("GitHub 저장소", link=REPO)),
        para(t("개발자라면 키 없이 터미널에서도 돌려 볼 수 있어요. 가상 상담 6건을 봇과 같은 코드로 처리해 답장과 기록을 보여 줘요.")),
        code("git clone {}.git\ncd sagak-agent && PYTHONPATH=src python3 -m sagak demo".format(REPO), "shell"),
        divider(),
        h2("2. 데모 봇으로 테스트하기"),
        para(t("아래 순서대로 보내 보면 사각사각이 하는 일을 처음부터 끝까지 볼 수 있어요. 메시지마다 "),
             t("/new", code=True), t("를 먼저 보내면 깔끔해요.")),
        num(t("신청: ", bold=True), t("텔레그램에서 "), t("@sagak_demo_bot", link=BOT, bold=True),
            t("을 열고 아무 말이나 보내요. “사용 신청을 받았어요 (신청 #번호)” → 승인되면 "),
            t("내 전용 가상 고객 예시", bold=True), t("가 함께 와요."), children=[code(EX_HELLO)]),
        num(t("새 상담: ", bold=True), t("승인 안내의 첫 번째 예시를 보내요. 고객 · 이벤트 · 1차 상담이 생기고 상품·일시·특이사항이 정리돼요. "
              "노션에서 상담자가 "), t("리뷰어 #번호", bold=True), t("인 기록이 내가 보낸 거예요."),
            children=[para(t(MINE_NOTE)), code(EX_MINE_NEW)]),
        num(t("2차 메모: ", bold=True), t("두 번째 예시를 보내요. 같은 고객의 2차 상담으로 이어지고, 바뀐 장소는 "),
            t("덮어쓰지 않고", bold=True), t(" ‘기존 정보와 다름’으로 표시돼요."), children=[code(EX_MINE_FOLLOW)]),
        num(t("같은 번호, 다른 이름: ", bold=True), t("예시의 이름만 한 글자 바꿔 보내요. 봇이 추측하지 않고 "),
            t("“같은 고객인가요?”", bold=True), t("라고 물어요. 답하면 그때 연결해요."), children=[code(EX_SAME)]),
        num(t("실제 같은 번호: ", bold=True), t("공개 노션에 올라가지 않도록 가상 번호(010-0000-)가 아니면 기록하지 않고 다시 요청해요."),
            children=[code(EX_REAL)]),
        num(t("업무와 상관없는 요청: ", bold=True), t("한 문장으로 거절하고 할 수 있는 일을 안내해요."), children=[code(EX_OFF)]),
        num(t("카카오톡 대화 파일: ", bold=True), t("아래 첨부한 "), t("kakao-chat.txt", code=True),
            t("를 내려받아 그대로 보내요(캡션 없이). 윤서아 고객, 12/24 20:00 확정, 케이크 옵션, 견과류 금지가 정리돼요.")),
        num(t("통화 녹음: ", bold=True), t("아래 첨부한 "), t("call-recording.m4a", code=True),
            t("를 내려받아 이 캡션과 함께 보내요. 화자·시각이 붙은 전사, 정원패키지 종류 질문, 근거 문장마다 녹음 클립이 생겨요."),
            children=[code(EX_CALL_CAPTION)]),
        num(t("결과 보기: ", bold=True), t("데모 홈", link=home_url, bold=True),
            t(" → 상담 이력에서 상담자가 ‘리뷰어 #번호’인 기록을 열어 보세요. 봇 답장의 노션 링크로 바로 가도 돼요.")),
        num(t("정리: ", bold=True), t("다 해 봤으면 내가 남긴 기록을 지울 수 있어요. 목록을 먼저 보여 주고, 10분 안에 "),
            t("/demo_reset 확인", code=True), t("을 보내면 휴지통으로 보내요. 다른 사람 기록과 기본 예시는 남아요."),
            children=[code("/demo_reset")]),
    ]
    if chat_id or audio_id:
        out.append(para(t("실제 상담처럼 파일로도 보내 보세요 (7·8번). 아래 파일을 내려받아 봇에 그대로 보내면 돼요.", bold=True)))
    if chat_id:
        out.append(file_block(chat_id, CAPTION_CHAT))
    if audio_id:
        out.append(file_block(audio_id, CAPTION_CALL))
        out.append(script_toggle())
    out += [
        callout("💡", "yellow_background",
                t("연락처는 꼭 "), t("010-0000-", bold=True),
                t("으로 시작하는 가상 번호를 써 주세요. 이 봇은 개발자 PC에서 명령을 실행하는 에이전트라, 승인한 분만 쓸 수 있게 했어요. "
                  "사각사각은 고객에게 직접 연락하거나 결제를 처리하지 않아요.")),
        divider(),
        h2("3. 내 노션·내 봇으로 쓰기 (준비 중)"),
        para(t("Hermes와 사각사각이 들어 있는 컨테이너 이미지로, 노션 키와 봇 토큰만 넣으면 돌아가게 만드는 중이에요. "
               "지금은 Hermes를 직접 설치해 연결하는 방법을 문서로 안내해요.")),
        bullet(t("설치 방법 (docs/setup.md)", link=REPO + "/blob/main/docs/setup.md")),
        divider(),
        para(t("만든 사람: 판교춘자 (AX 스쿨) · 모든 업체·고객·연락처는 가상 데이터예요")),
    ]
    return out


CAPTION_CHAT = "카카오톡 대화 내보내기 (윤서아, 레스토랑 프로포즈) — 캡션 없이 보내도 돼요"
CAPTION_CALL = "상담 통화 녹음 (강민준, 정원 프로포즈) — 캡션: 강민준 / 010-0000-7003"
FILES_INTRO = "실제 상담처럼 파일로도 보내 보세요"


def _upload(store, path, ctype):
    p = os.path.join(ROOT, path)
    if not os.path.exists(p):
        print("건너뜀 (파일 없음):", path)
        return None
    with open(p, "rb") as f:
        return store.upload_file(os.path.basename(p), f.read(), ctype)


def refresh_files(store, target):
    """가이드의 파일 블록을 지우고 새 파일을 같은 자리(안내 문장 바로 아래)에 다시 올린다."""
    kids = store._request("GET", "/blocks/{}/children?page_size=100".format(target)).get("results", [])
    intro = next((b for b in kids if b.get("type") == "paragraph" and "".join(
        r.get("plain_text", "") for r in b["paragraph"].get("rich_text", [])).startswith(FILES_INTRO)), None)
    if intro is None:
        sys.exit("가이드에서 '{}' 문장을 찾지 못했어요.".format(FILES_INTRO))
    for b in kids:
        is_script = b.get("type") == "toggle" and "".join(
            r.get("plain_text", "") for r in b["toggle"].get("rich_text", [])) == SCRIPT_TOGGLE
        if b.get("type") == "file" or is_script:
            store._request("DELETE", "/blocks/{}".format(b["id"]))
    new = []
    chat = _upload(store, "demo/kakao-chat.txt", "text/plain")
    if chat:
        new.append(file_block(chat, CAPTION_CHAT))
    call = _upload(store, "demo/call-recording.m4a", "audio/mp4")
    if call:
        new.append(file_block(call, CAPTION_CALL))
        new.append(script_toggle())
    if new:
        store._request("PATCH", "/blocks/{}/children".format(target), {"children": new, "after": intro["id"]})
    print("첨부 파일과 대본을 바꿨어요 (블록 {}개).".format(len(new)))


def update_guide(store, target, a, home):
    """맨 위 소개 카드와 하위 페이지(데모 홈)는 두고 나머지를 지운 뒤, 새 내용을 소개 카드 바로 아래에 차례로 넣는다."""
    kids = store._request("GET", "/blocks/{}/children?page_size=100".format(target)).get("results", [])
    first = next((b for b in kids if b.get("type") not in ("child_page", "child_database")), None)
    if first is None:
        sys.exit("가이드에 소개 카드가 없어요. --into로 처음부터 채워 주세요.")
    for b in kids:
        if b.get("type") not in ("child_page", "child_database") and b["id"] != first["id"]:
            store._request("DELETE", "/blocks/{}".format(b["id"]))
    chat_id = _upload(store, "demo/kakao-chat.txt", "text/plain")
    audio_id = _upload(store, "demo/call-recording.m4a", "audio/mp4")
    body = blocks(a.public or ("https://app.notion.com/p/" + home), a.video, chat_id, audio_id)[1:]  # 소개 카드는 그대로
    after = first["id"]
    for i in range(0, len(body), 95):
        res = store._request("PATCH", "/blocks/{}/children".format(target), {"children": body[i:i + 95], "after": after})
        after = (res.get("results") or [{}])[-1].get("id") or after
    print("가이드를 새로 썼어요 (블록 {}개, 데모 홈 하위 페이지는 그대로).".format(len(body) + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True)
    ap.add_argument("--home", required=True)
    ap.add_argument("--video")
    ap.add_argument("--public", help="게시된 데모 홈 주소 (notion.site). 가이드의 '데모 홈으로' 링크에 씀")
    ap.add_argument("--into", help="내용을 채울 빈 가이드 페이지 (링크 또는 ID)")
    ap.add_argument("--update", action="store_true",
                    help="--into 가이드 내용을 새로 쓰기 (하위 페이지인 데모 홈은 그대로 둠)")
    ap.add_argument("--refresh-files", action="store_true",
                    help="--into 가이드의 첨부 파일(대화 txt·통화 녹음)만 새로 올려 바꾸기")
    a = ap.parse_args()
    env = read_env(os.path.expanduser(a.env))
    store = NotionStore(env["NOTION_API_KEY"], "", "", "")
    home = page_id(a.home)
    home_url = a.public or ("https://app.notion.com/p/" + home)

    if a.into and a.update:
        update_guide(store, page_id(a.into), a, home)
        return
    if a.into and a.refresh_files:
        refresh_files(store, page_id(a.into))
        return
    if a.into:
        target = page_id(a.into)
        if store._request("GET", "/blocks/{}/children?page_size=5".format(target)).get("results"):
            sys.exit("가이드 페이지가 비어 있지 않아요. 내용을 지운 뒤 다시 실행해 주세요.")
        home_url = a.public or ("https://app.notion.com/p/" + home)
    else:
        children = store._request("GET", "/blocks/{}/children?page_size=100".format(home)).get("results", [])
        for b in children:
            if b.get("type") == "child_page" and b["child_page"].get("title") == TITLE:
                sys.exit("이미 '{}' 페이지가 있어요: https://app.notion.com/p/{} (다시 만들려면 노션에서 지운 뒤 실행)".format(
                    TITLE, b["id"].replace("-", "")))

    def up(path, ctype):
        p = os.path.join(ROOT, path)
        if not os.path.exists(p):
            print("건너뜀 (파일 없음):", path)
            return None
        with open(p, "rb") as f:
            return store.upload_file(os.path.basename(p), f.read(), ctype)

    chat_id = up("demo/kakao-chat.txt", "text/plain")
    audio_id = up("demo/call-recording.m4a", "audio/mp4")
    body = blocks(home_url, a.video, chat_id, audio_id)
    if a.into:
        for i in range(0, len(body), 95):
            store._request("PATCH", "/blocks/{}/children".format(target), {"children": body[i:i + 95]})
        store._request("PATCH", "/pages/{}".format(target), {"icon": {"type": "emoji", "emoji": "📘"}})
        print("채웠어요:", "https://app.notion.com/p/" + target)
        return
    page = store._request("POST", "/pages", {
        "parent": {"page_id": home}, "icon": {"type": "emoji", "emoji": "📘"},
        "properties": {"title": {"title": [t(TITLE)]}}, "children": body[:95]})
    if len(body) > 95:
        store._request("PATCH", "/blocks/{}/children".format(page["id"]), {"children": body[95:]})
    link = {"type": "link_to_page", "link_to_page": {"type": "page_id", "page_id": page["id"]}}
    req = {"children": [link]}
    if children:
        req["after"] = children[0]["id"]  # 맨 위 안내 바로 아래
    store._request("PATCH", "/blocks/{}/children".format(home), req)
    print("만들었어요:", "https://app.notion.com/p/" + page["id"].replace("-", ""))


if __name__ == "__main__":
    main()
