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
---

# 사각사각 상담 기록

## When to Use
대표나 직원이 상담 내용(전사 텍스트 또는 녹음)과 고객 정보를 보냈을 때. 상담 기록과 관계없는 요청에는 쓰지 않는다.

## Procedure

### 1. 입력 모으기
- **고객 정보**: 성함과 연락처는 꼭 필요하다. 보통 `김민수 / 010-0000-0000 / 이메일 / 회사명` 형태(캡션 또는 메시지 첫 줄).
- **상담 내용**: 전사 텍스트, 또는 녹음을 전사한 텍스트.
- 둘 중 하나가 없으면 기록하지 말고 빠진 것을 요청한다. 고객 정보와 상담 내용이 두 메시지로 나뉘어 오면 이어진 것으로 보고 합친다.
- 상담과 관계없는 내용(일상 대화 등)이면 기록하지 말고 그렇다고 알린다.
- 녹음 파일이 왔는데 전사 텍스트가 없으면: "녹음 처리 기능은 준비 중입니다. 전사 텍스트로 보내 주세요."라고 답한다.

### 2. 추출 JSON 작성
상담 내용에서 아래 JSON을 만든다. **말한 내용만** 넣고, 없거나 불확실하면 `null`로 두고 `needs_check`에 항목 이름을 넣는다. 숫자를 지어내지 않는다.

```json
{
  "caption": "고객 정보 원문 그대로",
  "input_type": "전사 텍스트 | 녹음",
  "consulted_at": "상담 시각 ISO (모르면 null → 받은 시각으로 기록)",
  "consultant": "보낸 사람 이름",
  "customer": {"customer_type": "개인 | 기업 | null", "company": "회사·단체명 | null"},
  "event": {
    "theme": "프로포즈 | 생일/기념일 | 기타",
    "product": "호텔패키지 | 갤러리패키지 | 레스토랑패키지 | 소극장패키지 | null",
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
    "needs_check": ["희망 일시", "예산", "희망 장소"]
  },
  "evidence": [{"field": "예산", "quote": "통화 속 문장 그대로", "time": "mm:ss | null"}],
  "transcript": "상담 내용 원문"
}
```
- 연도가 없으면 상담일 이후 가장 가까운 날짜로 본다. 시각이 없으면 `desired_at`은 `null`.
- `budget`·`option_price`는 원 단위 정수. "100만 원 정도" → 1000000, "200 안팎"처럼 범위가 불분명하면 값을 넣되 `needs_check`에 "예산".
- 결제 방식·결제 금액 확정·결제일은 넣지 않는다.

### 3. 기록
JSON을 `/tmp/sagak/` 아래 파일로 저장하고 실행한다.

    mkdir -p /tmp/sagak
    PYTHONPATH=${HERMES_SKILL_DIR}/../../../src python3 -m sagak record /tmp/sagak/${HERMES_SESSION_ID}.json

실행이 끝나면 JSON 파일을 지운다(고객 개인정보).

### 4. 답장
결과 JSON을 보고 SOUL의 답장 형식으로 짧게 답한다.
- `review`가 `확인 대기`: "✅ OOO님 · 테마 · N차 상담 기록 완료" + 핵심 조건 + 확인 필요 + `consultation.url`
- `review`가 `고객 확인 필요`: 자동 연결하지 않은 이유와 `candidates`를 보여 주고, 상담 이력 링크를 준다.
- `diffs`가 있으면 "기존 정보와 다른 내용은 덮어쓰지 않았습니다"와 함께 한 줄씩.
- 연락처·이메일 전체를 답장에 다시 쓰지 않는다.

## Pitfalls
- 종료 코드 2(`MISSING_CUSTOMER`, `EMPTY_CONSULTATION`): 기록되지 않았다. message대로 다시 요청한다.
- 종료 코드 1: 기록 실패. 오류 내용을 짧게 전하고 다시 시도하지 않는다(중복 기록 방지).
- 같은 상담을 두 번 기록하지 않는다. 사용자가 다시 보내 달라고 하기 전에는 재실행하지 않는다.

## Verification
결과 JSON의 `ok: true`와 `consultation.url`이 있으면 기록된 것이다.
