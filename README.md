# 사각사각 (sagak-agent)

이벤트 회사의 전화 상담 녹음(또는 전사 텍스트)과 고객 정보를 텔레그램으로 받아,
Notion 고객 관리 보드에 요구 사항과 상담 이력을 정리하는 Hermes Agent 기반 에이전트입니다.
AX School 프로젝트 제출용 레포입니다.

- 상태: 개발 준비 (레포 구조와 문서 정리 완료, 1단계 profile 뼈대 진행 예정)
- 기획안: [docs/planning.md](docs/planning.md)
- 개발 계획서: [docs/dev-plan.md](docs/dev-plan.md)
- 결정 기록: [docs/decisions.md](docs/decisions.md)

## 폴더 구조

```
sagak/
├── README.md
├── CLAUDE.md          Claude 작업 규칙 (Karpathy 가이드라인 + 프로젝트 규칙)
├── docs/              기획안, 개발 계획서, 결정 기록
├── src/               Python 코드 (전사, 검증, Notion 동기화)
├── agent/             Hermes profile `sagak` 파일 (SOUL.md, skills, 설정 예시)
├── recordings/        로컬 실제 녹음·전사 (커밋 안 됨)
└── tests/fixtures/    가상 테스트 데이터 (커밋 가능)
```

## 원칙

- API 키, 봇 토큰, 실제 고객 데이터는 커밋하지 않습니다. 키는 Hermes 대시보드에서만 입력합니다.
- 녹음과 고객 정보에 없는 내용은 추측하지 않고 `확인 필요`로 표시합니다.
- 기존 고객 정보는 덮어쓰지 않고, 상담은 매번 새 이력으로 추가합니다.

## 개발 흐름

맥 네이티브 Hermes에서 profile `sagak`으로 개발하고, 운영은 컨테이너(맥 호스트 → 클라우드)로 옮깁니다.
자세한 단계는 [개발 계획서](docs/dev-plan.md)를 보세요.
