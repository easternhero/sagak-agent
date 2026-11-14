# 직접 써 보기

사각사각은 텔레그램 봇 + Hermes Agent + 노션으로 돌아가서, 웹 주소 하나로 배포하는 형태가 아닙니다.
대신 세 가지 방법으로 써 볼 수 있습니다. 모든 데모 데이터는 가상입니다.

| 방법 | 필요한 것 | 시간 |
|---|---|---|
| A. 키 없이 체험 | Python 3.9+ | 1분 |
| B. 데모 봇 써 보기 | 텔레그램 | 바로 (허용 요청 후) |
| C. 내 노션·봇으로 설치 | 노션·텔레그램·OpenAI 계정, Hermes Agent | 30분 |

결과를 보는 곳: **[공개 데모 노션](https://sagak-demo-home.notion.site/0976d6e4c49f82ca8fab813dfe18cf6d)** (가상 업체 '설렘 이벤트')

## A. 키 없이 체험 (1분)

```bash
git clone https://github.com/easternhero/sagak-agent.git
cd sagak-agent
PYTHONPATH=src python3 -m sagak demo
```

가상 상담 6건을 봇과 같은 코드로 처리하고, 봇 답장과 노션에 들어갈 기록을 화면에 보여 줍니다(노션에는 쓰지 않음).

1. 새 고객 첫 상담 → 고객·이벤트·1차 상담 생성, 빠진 시각은 '확인 필요'와 물어볼 질문으로
2. 같은 고객 2차 상담 → 다음 차수로 연결, 바뀐 장소는 덮어쓰지 않고 표시
3. 같은 연락처·다른 이름 → "같은 사람인가요?" 확인 후에만 연결
4. 정보가 빠진 상담 → 추측하지 않고 물어볼 것으로
5. 예약금 입금 → 확정 일시 채우고 '이벤트진행예정'으로 (자동 점검)
6. 상담과 관계없는 녹음, 고객 정보 없음 → 기록하지 않고 정보 요청

대화에서 내용을 뽑는 단계(대화 모델)는 미리 뽑아 둔 결과(`tests/fixtures/extractions/`)를 씁니다. 실제 녹음 전사와 추출은 B·C에서 볼 수 있습니다.
외부 패키지 없이 표준 라이브러리만 씁니다. 단위 테스트: `python3 -m unittest discover -s tests -t .`

## B. 데모 봇 써 보기

데모 봇은 개발자 PC에서 돌고, 승인한 계정만 쓸 수 있습니다(봇이 PC에서 명령을 실행하는 에이전트라 아무나 열지 않음).

1. 데모 봇 [@sagak_demo_bot](https://t.me/sagak_demo_bot)을 열고 아무 말이나 보냅니다.
2. 봇이 "사용 신청을 받았어요 (신청 #번호)"라고 답합니다. 개발자에게 신청이 전달됩니다.
3. 승인되면 봇이 "승인됐어요!"와 예시 메시지를 보내 줍니다. `/new` 후 예시를 보내 보세요. 결과는 공개 데모 노션에 바로 보입니다.

```
한지우 / 010-0000-7001
갤러리 프로포즈 문의. 12월 5일 토요일 저녁 7시, 장미 50송이 추가, 촬영도 원함. 서프라이즈라 여자친구에게 연락 금지
```

녹음 파일(m4a·mp3 등)이나 카카오톡 대화 내보내기(txt)를 캡션 `이름 / 010-0000-xxxx`와 함께 보내도 됩니다. 연락처는 꼭 `010-0000-`로 시작하는 가상 번호를 써 주세요.
업무와 관계없는 요청(날씨, 검색 등)은 거절합니다.

개발자 쪽: 같은 데모 봇에서 관리자에게 신청 알림이 오고, `/demo_approve 번호` · `/demo_deny 번호` · `/demo_requests`로 밖에서도 처리합니다(Hermes 플러그인 [`agent/plugins/sagak-demo-access`](../agent/plugins/sagak-demo-access), 관리자만 실행 가능).

## C. 내 노션·봇으로 설치

### 1. 노션

1. 공개 데모 노션 페이지 오른쪽 위 **복제**로 내 워크스페이스에 복사합니다.
2. https://www.notion.so/profile/integrations 에서 **새 연결(내부)** → 키를 복사합니다.
3. 복제한 홈 페이지 → ⋯ → **연결** → 방금 만든 연결을 추가합니다.
4. DB ID는 3단계에서 `.env`에 키를 넣은 뒤 `PYTHONPATH=src python3 -m sagak setup-notion --env ~/.hermes/profiles/sagak/.env`로 자동으로 채웁니다.

### 2. 텔레그램 봇

@BotFather → `/newbot` → 토큰을 복사합니다. 내 숫자 ID는 @userinfobot으로 확인합니다.

### 3. Hermes Agent 프로필

[Hermes Agent](https://github.com/NousResearch/hermes-agent)를 설치하고 대화 모델을 연결한 뒤:

```bash
hermes profile create sagak
cp agent/SOUL.md ~/.hermes/profiles/sagak/SOUL.md
```

`~/.hermes/profiles/sagak/config.yaml`에 [`agent/config.example.yaml`](../agent/config.example.yaml)의 `terminal.env_passthrough`, `skills`, `platforms.telegram` 부분을 옮기고, `skills.external_dirs`를 이 레포의 `agent/skills` 절대 경로로 바꿉니다.

`~/.hermes/profiles/sagak/.env` (값은 레포나 대화에 쓰지 마세요):

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USERS=내 숫자 ID
NOTION_API_KEY=...
# SAGAK_NOTION_*_DB 4개는 setup-notion이 채움
SAGAK_OPENAI_STT_KEY=...          # 녹음 전사 (텍스트만 쓰면 생략 가능)
SAGAK_BUSINESS_FILE=/레포경로/agent/demo/business.json
SAGAK_DEMO=1
```

선택: 네이버 지도 자동 링크(`SAGAK_NAVER_CLIENT_ID`·`SECRET`), 근거별 녹음 클립(`SAGAK_AUDIO_CLIPS=1`, ffmpeg 필요). 전체 목록은 [agent/README.md](../agent/README.md).

### 4. 실행

```bash
cd sagak-agent
PYTHONPATH=src python3 -m sagak setup-notion --env ~/.hermes/profiles/sagak/.env   # 노션 DB ID 채우기
hermes -p sagak gateway run              # 봇 실행 (상시 실행은 hermes -p sagak gateway install)
```

텔레그램에서 봇에 `/new` → B의 예시 메시지를 보내면 내 노션에 기록됩니다.

## 되돌리기 어려운 작업과 사람 확인

- 봇은 고객에게 연락하거나 결제·예약 확정을 하지 않습니다. 결제 상태와 취소는 사람이 노션에서 바꿉니다.
- 같은 연락처에 다른 이름, 진행 중 이벤트가 둘 이상이면 "같은 고객인가요?"라고 묻고 답을 받은 뒤에 연결합니다.
- 기존 값은 덮어쓰지 않고 '기존 정보와 다름'으로 표시합니다.
- 테스트 기록 일괄 삭제는 목록을 보여 주고 확인을 받은 뒤에만 합니다.
