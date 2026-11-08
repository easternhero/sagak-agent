# agent

Hermes profile `sagak`에 들어갈 파일입니다. Hermes profile distribution 형식으로 관리합니다.

- `SOUL.md` — 사각사각의 역할과 금지 규칙 (프로필 폴더에 복사해 씀)
- `skills/sagak-intake/` — 상담 기록 스킬
- `config.example.yaml` — 프로필 설정 예시
- `business.example.json` — 업체별 값 예시(브랜드·상품·상품 묶음·접수 경로). 실제 값은 `business.json`(커밋 안 함)
- `CHANGES.md` — 봇 사용자에게 보내는 변경 안내

## 프로필 `.env`에 넣는 값 (이름만, 값은 레포·대화에 쓰지 않음)

| 이름 | 용도 | 없으면 |
|---|---|---|
| `NOTION_API_KEY` | 노션 연결 | 기록 불가 |
| `SAGAK_NOTION_CUSTOMERS_DB` · `SAGAK_NOTION_EVENTS_DB` · `SAGAK_NOTION_CONSULTATIONS_DB` | 노션 DB 3개 | 기록 불가 |
| `SAGAK_OPENAI_STT_KEY` | 녹음 전사 | 녹음 처리 불가 |
| `SAGAK_STT_MODEL` | 전사 모델 (선택) | 기본 모델 |
| `SAGAK_NAVER_CLIENT_ID` · `SAGAK_NAVER_CLIENT_SECRET` | 네이버 검색 API(지역) — 자동 지도 링크 확인 (D48) | 자동 지도 링크를 달지 않음(직원 링크는 확인 후 달림) |
| `SAGAK_AUDIO_CLIPS` | `1`이면 근거별 녹음 클립 (D43) | 클립 없음 |
