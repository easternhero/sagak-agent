# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

# 사각사각 프로젝트 규칙

위 원칙에 더해 이 레포에서 지키는 규칙입니다.

## 무엇을 만드는가
- 이벤트 회사의 상담 녹음(또는 전사 텍스트)과 고객 정보를 받아 Notion 고객 보드에 정리하는 Hermes Agent profile `sagak`.
- 기획안: https://gist.github.com/easternhero/d9f084c0d4a62a263cbb640e7ecbe585
- 진행 결정과 체크리스트: 사각사각 준비 보드(claude.ai artifact). 새 결정이 필요하면 코드로 정하지 말고 보드에 결정 항목을 올린다.

## 비밀값과 고객 데이터
- API 키, 봇 토큰, OAuth 정보는 레포·Notion 페이지·대화에 쓰지 않는다. 입력은 Hermes 대시보드의 sagak profile에서만 한다. 레포에는 `.env.example`(키 이름만)만 둔다.
- 실제 고객 녹음, 전사본, 연락처는 커밋하지 않는다. 테스트는 `tests/fixtures/`의 가상 데이터만 쓴다.

## 데이터 처리 규칙 (코드로 강제)
- 녹음과 고객 정보에 없는 내용은 추측해서 채우지 않고 `확인 필요`로 표시한다.
- 고객 연결은 전화번호(정규화 후) 일치일 때만 자동으로 한다. 이름이나 내용만 비슷하면 후보로만 보여준다.
- 새 입력에 없는 값으로 기존 Notion 값을 지우지 않는다. 상담은 매번 새 이력으로 추가한다.
- 추출 항목마다 근거 문장과 (가능하면) 녹음 시간을 남긴다.
- 고객에게 메시지를 자동으로 보내지 않는다.

## 역할 분담
- 판단(정보 추출)은 LLM, 기록(Notion 쓰기)과 규칙 검사는 Python 스크립트가 한다.
- 전사는 전용 STT. 텍스트 입력(srt/vtt 포함)은 전사 단계를 건너뛴다.
- 고객사마다 달라지는 값(Notion DB ID, 모델, 봇 토큰)은 코드에 넣지 않고 설정으로 뺀다. 고객사 1곳 = Hermes profile 1개.

## 작업 방식
- 사용자가 확인해야 할 결정(이름, 위치, 외부 서비스 설정, 삭제)은 진행 전에 묻는다.
- 코드는 Python. 변경마다 테스트로 확인할 수 있는 기준을 먼저 정한다.
- 봇 사용자에게 보이는 변경이면 `agent/CHANGES.md` 맨 위에 사용자용 안내 한 줄을 함께 적는다(설정·키 변경은 `[restart]`). 작업 단위마다 개발 PC의 레포에 커밋한다. 커밋 시각은 한국 시간으로 남긴다(`TZ=Asia/Seoul git commit …`). `git push`는 하지 않는다(사용자가 원할 때 직접 푸시).
