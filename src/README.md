# src

사각사각의 Python 코드입니다. 패키지 이름은 `sagak`.

| 모듈(예정) | 역할 |
|---|---|
| `transcribe.py` | 녹음 → 구간 시간 포함 전사 (전용 STT) |
| `validate.py` | 추출 결과 스키마 검사, 전화번호 정규화 |
| `notion_sync.py` | 고객 DB 갱신, 상담 이력 추가 (덮어쓰기 금지 등 규칙 강제) |

Hermes 스킬(`agent/skills/`)이 이 코드를 호출합니다.
