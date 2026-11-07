---
name: sagak-intake
description: 상담 녹음·전사 텍스트와 고객 정보를 받아 Notion 고객 보드(고객·이벤트·상담 이력)에 기록한다
version: 0.1.0
author: sagak-agent
platforms: [macos, linux]
metadata:
  hermes:
    tags: [사각사각, 상담, Notion]
    requires_toolsets: [terminal, file]
required_environment_variables:
  - name: NOTION_API_KEY
    prompt: "사각사각 Notion integration 키"
    required_for: "Notion 기록"
  - name: SAGAK_NOTION_CUSTOMERS_DB
    required_for: "고객 DB ID"
  - name: SAGAK_NOTION_EVENTS_DB
    required_for: "이벤트(의뢰) DB ID"
  - name: SAGAK_NOTION_CONSULTATIONS_DB
    required_for: "상담 이력 DB ID"
  - name: SAGAK_OPENAI_STT_KEY
    prompt: "STT용 OpenAI 키 (Hermes 자체 음성 키는 보안상 넘겨받을 수 없어 별도 이름)"
    required_for: "녹음 전사"
---

# 사각사각 상담 기록

## When to Use
대표나 직원이 상담 내용(전사 텍스트 또는 녹음)과 고객 정보를 보냈을 때. 상담 기록과 관계없는 요청에는 쓰지 않는다.

## Procedure

### 1. 입력 모으기
- **고객 정보**: 성함과 연락처는 꼭 필요하다. 보통 `김민수 / 010-0000-0000 / 이메일 / 회사명` 형태(캡션 또는 메시지 첫 줄).
- **상담 내용**: 전사 텍스트, 또는 녹음을 전사한 텍스트.
- 둘 중 하나가 없으면 기록하지 말고 빠진 것을 요청한다. 고객 정보와 상담 내용이 두 메시지로 나뉘어 오면 이어진 것으로 보고 합친다.
- 성함에 불명확한 접두 문자나 오타 의심 부분이 있으면 임의로 제거하지 말고, 쓰기 전에 직원에게 성함만 확인한다. 정정 답변을 받으면 기존 상담과 합치고 `caption` 원문은 보존하되 `customer.name`에 확인된 성함을 명시한다.
- 후속 상담은 성함·연락처가 모두 같은 고객에만 연결한다. 앞선 상담의 정보를 활용할 때는 이번 발언과 이전 맥락을 요약에서 구분하고, 이번에 언급되지 않은 예산·마감일을 새로 확정한 것처럼 쓰지 않는다.
- 상담과 관계없는 내용(일상 대화 등)이면 기록하지 말고 그렇다고 알린다.
- **녹음 파일**이 오면(메시지에 `[The user sent a voice message: <경로>]`나 파일 경로가 붙어 옴) 먼저 전사한다.

      PYTHONPATH=/path/to/sagak-agent/src python3 -m sagak transcribe "<녹음 파일 경로>"

  결과의 `lines`(예: `[01:23] B: 내용`)를 `transcript`로 쓰고, `input_type`은 `녹음`, `evidence.time`에는 근거 문장이 있는 줄의 시간을 넣는다. 화자(A, B)가 상담자인지 고객인지는 내용으로 판단하되, 애매하면 화자 표시 그대로 둔다.
  전사 오류(`BAD_AUDIO`, `UNSUPPORTED_FORMAT`, `FILE_TOO_LARGE`, `EMPTY_AUDIO`)면 기록하지 말고 message대로 재전송을 요청한다. `STT_FAILED`면 잠시 후 다시 보내 달라고 한다.

### 2. 추출 JSON 작성
상담 내용에서 아래 JSON을 만든다. **말한 내용만** 넣고, 없거나 불확실하면 `null`로 두고 `needs_check`에 항목 이름을 넣는다. 숫자를 지어내지 않는다.

```json
{
  "caption": "고객 정보 원문 그대로",
  "input_type": "전사 텍스트 | 녹음",
  "consulted_at": "상담 시각 ISO (모르면 null → 받은 시각으로 기록)",
  "consultant": "텔레그램으로 보낸 사람의 표시 이름",
  "customer": {"customer_type": "개인 | 기업", "company": "회사·단체명 | null"},
  "event": {
    "theme": "프로포즈 | 생일/기념일 | 기타",
    "product": "갤러리패키지 | 호텔패키지 | 레스토랑패키지 | 출장 렌탈 | 소극장패키지 | null",
    "venue": "희망 장소 | null",
    "desired_at": "YYYY-MM-DDTHH:MM:SS (날짜와 시각이 모두 분명할 때만) | null",
    "desired_at_text": "말한 그대로 (예: 12월 12일 저녁)",
    "budget": 1000000,
    "request": "요청 사항 요약 | null"
  },
  "consultation": {
    "summary": "상담 내역 2~3문장",
    "options": "옵션 | null", "option_price": 150000,
    "follow_up": "후속 업무", "next_contact": "다음 연락 시점 | null",
    "questions": ["고객에게 다시 물을 것"],
    "needs_check": ["희망 일시", "예산", "희망 장소", "이벤트 테마", "다음 연락 시점" 중에서만]
  },
  "evidence": [{"field": "예산", "quote": "통화 속 문장 그대로", "time": "mm:ss | null"}],
  "transcript": "상담 내용 원문"
}
```
- 연도를 말하지 않았으면 상담일 기준 **가장 가까운 미래**의 날짜로 본다(예: 11월 상담에서 '1월 5일' → 다음 해 1월 5일). 날짜와 시각이 모두 분명하지 않으면 `desired_at`은 `null`로 두고 희망 일시 원문을 보존한다.
- 상대적인 연락 기한은 도구로 확인한 수신일을 기준으로 해석하되 원문도 함께 남긴다. 후속 상담에서 재견적 기한을 언급하지 않았다면 이전 연락 기한이 재견적에도 적용되는지 확인 질문으로 남긴다.
- 옵션 문의·가격 안내·선택 확정을 구분한다. 안내된 추가 옵션 가격은 `option_price`에 기록할 수 있으나, 선택 확정이나 결제 확정으로 취급하거나 기존 예산에 자동 합산하지 않는다. 포함 여부를 질문으로 남긴다.
- 후속 업무는 상담자가 약속한 업무와 추가 확인이 필요한 업무를 구분하고, 명시되지 않은 담당자·발송 기한을 만들어 넣지 않는다.
- `budget`·`option_price`는 원 단위 정수. "100만 원 정도" → 1000000, "200 안팎"처럼 범위가 불분명하면 값을 넣되 `needs_check`에 "예산".
- 결제 방식·결제 금액 확정·결제일은 넣지 않는다.
- `product`는 관리 페이지 상품명으로 쓴다. 고객은 안내용 이름으로 말한다: 갤러리 프로포즈 → `갤러리패키지`, 호텔·신혼집 프로포즈 → `호텔패키지`, 레스토랑(스카이라운지) 프로포즈 → `레스토랑패키지`, 출장 렌탈 패키지 → `출장 렌탈`. 목록 밖 상품(요트·연극·콘서트홀 등)이나 정하지 않았으면 `null`로 두고 `request`에 적는다.
- `customer_type`은 기본 `개인`. 상담이나 고객 정보에 회사·단체(회사 행사, 단체 예약, 회사명 등)가 나오면 `기업`으로 하고 `company`에 이름을 넣는다.
- **짧게 쓴다.** `summary`는 2~3문장, `next_contact`·`follow_up`은 한 줄. 모르면 `null`(기록 시 '미정').
- **이번 통화에서 새로 말한 내용만** `event`에 넣는다. 이전 상담 내용을 다시 옮겨 적지 않는다(기존 값은 코드가 유지한다).
- `needs_check`에는 위 다섯 항목만 쓴다. 그 밖에 확인할 것은 `questions`에 질문으로 쓴다.

### 3. 기록
JSON을 현재 프로필의 scratch 디렉터리(`TMPDIR`)에 고유 파일명으로 저장하고 실행한다. 시스템 `/tmp`나 다른 프로필에 개인정보를 저장하지 않는다.

    PYTHONPATH=/path/to/sagak-agent/src python3 -m sagak record "$TMPDIR/<고유파일명>.json"

실행 결과의 JSON과 종료 코드를 확보하고, 성공·실패와 관계없이 `finally`에서 입력 JSON 파일을 삭제한다(고객 개인정보). 기록 실행은 한 번만 하고 아래 검증을 이어서 수행한다.

### 4. 사람의 확인 답변 처리 (`고객 확인 필요`였던 상담)
직원이 "같은 고객", "별도 고객", 또는 어느 이벤트에 붙일지 답하면 아래 명령으로만 처리한다.

    PYTHONPATH=/path/to/sagak-agent/src python3 -m sagak resolve <상담 링크> same [--customer <고객 링크>] [--event <이벤트 링크>] --by "<답한 사람>"
    PYTHONPATH=/path/to/sagak-agent/src python3 -m sagak resolve <상담 링크> separate --by "<답한 사람>"

- 후보 고객이 하나면 `--customer`는 생략할 수 있다. 여러 명이면 어느 고객인지 먼저 묻는다.
- 결과가 `NEED_EVENT`이면 후보 이벤트를 보여 주고 골라 달라고 한 뒤 `--event`로 다시 실행한다.
- 결과가 `NO_PENDING`이면 자동 처리할 수 없다. "Notion에서 직접 연결해 주세요"라고 안내한다.
- 같은 고객이어도 기존 고객 이름은 바꾸지 않는다. 이름 정정은 사람이 Notion에서 한다.

### 5. 답장
결과 JSON을 보고 SOUL의 답장 형식으로 짧게 답한다.
- `review`가 `확인 대기`: "✅ OOO님 · 테마 · N차 상담 기록 완료" + 핵심 조건 + 확인 필요 + `consultation.url`
- `review`가 `고객 확인 필요`: 자동 연결하지 않은 이유와 `candidates`를 보여 주고, 상담 이력 링크를 준다.
- `warnings`가 있으면(블랙리스트 고객) 답장 **맨 위**에 "⚠️ " + 내용 그대로 쓴다. 표시(K·S·B)는 사람이 Notion에서 고르며, 봇이 붙이거나 바꾸지 않는다.
- `diffs`가 있으면 "기존 정보와 다른 내용은 덮어쓰지 않았습니다"와 함께 한 줄씩.
- 연락처·이메일 전체를 답장에 다시 쓰지 않는다.

## Pitfalls
- **Notion에는 `python3 -m sagak` 명령(record, resolve)으로만 쓴다.** curl·Python 등으로 Notion API를 직접 호출하지 않는다. 명령으로 할 수 없는 수정(이름 정정, 이벤트 상태 변경, 삭제 등)은 하지 말고 사람이 Notion에서 하도록 안내한다.
- 종료 코드 2(`MISSING_CUSTOMER`, `EMPTY_CONSULTATION`): 기록되지 않았다. message대로 다시 요청한다.
- 종료 코드 1: 전체가 미기록됐다고 단정하지 않는다. 고객 → 이벤트 → 상담 순으로 쓰므로 일부만 기록됐을 수 있다. 오류 내용을 짧게 전하고 기록 명령은 재실행하지 않는다(중복 기록 방지).
- 같은 상담을 두 번 기록하지 않는다. 사용자가 다시 보내 달라고 하기 전에는 재실행하지 않는다.

## Verification
결과 JSON의 `ok: true`와 `consultation.url`이 있으면 기록된 것이다. 코드가 Notion의 생성 응답을 받은 경우에만 `ok: true`를 돌려주므로, Notion을 다시 읽어 확인하지 않는다.
