# 사각사각 (sagak-agent)

이벤트 회사의 상담 내용(통화 녹음, 전사, 채팅 내보내기)과 고객 정보를 텔레그램으로 받아,
Notion 고객 관리 보드에 고객 · 이벤트(의뢰) · 상담 이력으로 정리해 주는 Hermes Agent 기반 에이전트입니다.
AX School 프로젝트 제출용 레포입니다.

- 기획안: [docs/planning.md](docs/planning.md) · 개발 계획서: [docs/dev-plan.md](docs/dev-plan.md)
- 서비스 흐름: [docs/service-flow.md](docs/service-flow.md) · 노션 구성: [docs/notion-schema.md](docs/notion-schema.md)
- 결정 기록(D1–D57): [docs/decisions.md](docs/decisions.md) · 봇 테스트 시나리오: [docs/bot-test-scenarios.md](docs/bot-test-scenarios.md)

## 직접 써 보기

- **키 없이 1분 체험:** `PYTHONPATH=src python3 -m sagak demo` — 가상 상담 6건을 봇과 같은 코드로 처리해 답장과 기록을 보여 줍니다.
- **데모 봇과 공개 데모 노션, 내 노션·봇으로 설치하는 방법:** [docs/setup.md](docs/setup.md)

## 1. 누구를 위한 에이전트인가

**대상**: 프러포즈·기념일 이벤트를 기획하고 현장에서 진행하는 소규모 이벤트 회사의 대표와 상담 직원(4명, 하루 상담 5~10건).

**지금 일하는 방식의 문제**: 상담은 전화와 메신저 채널로 들어오고, 직원이 통화를 마친 뒤 내용을 기억에 의존해 관리 페이지에 손으로 옮깁니다.
옮기는 데 시간이 들고, 희망 일시·장소·예약금·현장 주의사항 같은 세부 내용이 빠지거나 늦게 들어갑니다.
같은 고객의 2차·3차 상담이 흩어지고, 예약금이 들어왔는지·취소 후 환불했는지 같은 상태도 따로 챙겨야 합니다.

**사각사각이 대신하는 업무**

| 업무 | 사람이 하던 일 | 사각사각 |
|---|---|---|
| 상담 기록 | 통화 후 관리 페이지에 직접 입력 | 녹음·채팅 파일을 텔레그램으로 보내면 노션 고객·이벤트·상담 이력에 정리 |
| 녹음 정리 | 다시 들으며 메모 | 화자·시각이 있는 전사, 원문 전체 보관 |
| 빠진 정보 챙기기 | 다음 통화 때 기억에 의존 | 확인 필요 항목과 고객에게 물어볼 질문을 남기고 답장으로 알림 |
| 고객 이력 잇기 | 같은 고객인지 직접 찾기 | 연락처·이름으로 같은 고객·이벤트에 이어 붙이고, 애매하면 사람에게 확인 |
| 일정·결제 상태 | 날짜·입금·환불을 따로 확인 | 예약금 입금 → 확정 일시·진행 예정, 날짜가 지나면 완료, 취소인데 환불 표시가 없으면 알림 |
| 현장 준비 | 대화에서 다시 찾기 | 특이사항(서프라이즈 연락 금지, 반입 제한 등)과 확인된 네이버 지도 링크를 이벤트에 정리 |

봇은 기록하고 정리할 뿐, 고객에게 직접 연락하거나 결제를 처리하지 않습니다. 결제·취소 같은 판단은 사람이 노션에서 합니다.

## 2. 진행 상황 (2026-11-09 기준)

고객사(이벤트 회사)가 실제 상담으로 테스트 사용 중입니다. 봇은 아직 개발자 PC에서 돕니다.

### 지금 되는 것

- 텔레그램으로 받은 **녹음·전사 파일·채팅 내보내기·붙여넣은 대화**를 노션 고객 · 이벤트(의뢰) · 상담 이력에 기록
- 녹음 전사(OpenAI, 화자·시각 포함). 전사·채팅 원문은 모델을 거치지 않고 파일 그대로 끝까지 보관
- 추출 결과 검증: 연도 없는 날짜·상대 날짜 해석, 상품 안내 이름 → 관리 페이지 상품명, 상품별 테마, 예약금·확정 일시·특이사항·접수 경로
- 같은 고객·이벤트 자동 연결(다음 차수 상담), 기존 값은 덮어쓰지 않고 다르면 표시, 애매하면 "같은 고객인가요?" 확인 후 연결
- 기록 전 그 고객의 이전 상담을 읽어 빈 칸 보충, 기록 후 전체 이벤트 점검(예약금 입금·지난 일정·취소 후 환불)
- 근거별 녹음 클립: 녹음 기록의 근거 문장마다 그 구간을 잘라 노션에서 바로 들어 볼 수 있음(고객사 동의 후 켬)
- 계좌·카드번호 자동 가림, 블랙리스트 고객 경고, 테스트 기록 표시(성함 `[테스트]` 또는 연락처 `010-0000-`)와 일괄 정리
- 네이버 지도 링크: 직원 링크는 열리는지 확인, 자동 링크는 네이버 검색 API(API HUB)로 장소가 확인될 때만, 장소가 고정인 상품은 노션 '상품'의 링크 사용
- 운영 도구: 변경 안내·요청 보내기 화면(개발자 PC 로컬), 직원용 명령 메뉴 제한(/new · /stop · /help)
- 테스트: 단위 테스트 149개(표준 라이브러리만), 키 없이 체험하는 `sagak demo`, 텔레그램 봇 시나리오 T1–T9

### 아직 안 되는 것

- **상시 운영**: 개발자 PC에서만 돌아 PC가 꺼지면 멈춥니다. 컨테이너·클라우드 이전과 고객사 명의 계정 전환은 남아 있습니다(계획서 7–8단계).
- **정확도 검증**: "상담 10건 중 9건 정확" 기준으로 정해서 재어 본 적이 없습니다. 실제 사용 중 나온 오류를 고치며 보완 중입니다.
- **장소 링크 자동 생성**: 네이버 검색 API가 장소 번호를 주지 않아 naver.me 형식 링크는 직원·상품 링크로만 답니다.
- **기존 관리 페이지 연동**: 고객사의 기존 관리 페이지와는 연결하지 않았습니다(노션을 별도로 사용).
- **알림**: '확인 대기'·'다음 연락 시점'을 정해진 시간에 먼저 알려 주는 기능은 아직 없습니다.
- 결제 상태·이벤트 취소 표시는 사람이 입력합니다(봇은 대화에 분명한 환불 완료만 표시).

## 3. 연결한 정보와 도구

| 구분 | 무엇 | 용도 |
|---|---|---|
| 입력 채널 | 텔레그램 봇 (Hermes gateway) | 직원이 녹음·파일·메모를 보내고 결과를 받음 |
| 에이전트 | Hermes Agent profile `sagak` + OpenAI 대화 모델 | 규칙(SOUL)과 스킬에 따라 상담 내용을 구조화 |
| 음성 인식 | OpenAI 전사 API (`gpt-4o-transcribe-diarize`) + ffmpeg | 녹음 → 화자·시각 있는 전사, 형식 변환 |
| 정보 저장 | Notion API: 고객 · 이벤트(의뢰) · 상담 이력 · 상품 DB | 기록 결과, 상품별 장소 링크 |
| 외부 API | 네이버 검색 API(NAVER API HUB 지역 검색) | 지도 링크 장소 확인 |
| 업체 설정 | `agent/business.json` (커밋 안 함, 예시만 공개) | 브랜드, 상품 안내 이름, 상품 묶음, 접수 경로 |

**AX School에서 배운 것 활용**: Hermes profile로 에이전트 분리, SOUL.md로 역할·금지 규칙, 스킬(`agent/skills/sagak-intake`)로 절차, 기본 스킬 끄기(`skills.disabled`, 봇은 사각사각 스킬과 Hermes 자체 안내 스킬만 사용), 스킬 쓰기 승인(`skills.write_approval`)으로 봇의 스킬 자동 수정 막기, 텔레그램 gateway의 허용 사용자·관리자 명령 분리, 결정 기록과 테스트로 사람 확인을 남기는 개발 흐름.

## 4. 서비스 흐름

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/service-flow-dark.png">
  <img alt="직원 휴대폰의 텔레그램 → 개발자 PC의 Hermes 봇(사각사각 프로필) → OpenAI(대화 모델·녹음 전사) → 노션 기록 → 텔레그램 답장 구성도" src="docs/images/service-flow-light.png">
</picture>

1. 직원이 텔레그램 봇에 통화 녹음(또는 메모)과 고객 이름·연락처를 보냅니다.
2. 개발자 PC의 Hermes 봇(profile `sagak`)이 받습니다.
3. OpenAI 대화 모델이 규칙(`agent/`)에 따라 내용을 정리합니다.
4. 녹음이면 OpenAI 전사 모델로 글로 옮깁니다.
5. 기록 프로그램(`src/sagak/`)이 노션 고객·이벤트·상담 이력에 씁니다.
6. 봇이 확인 필요 항목과 노션 링크를 답장합니다.

단계별 담당 파일, 쓰는 모델과 도구, 지금 테스트 구성의 한계와 클라우드 이전 계획은 [서비스 흐름 문서](docs/service-flow.md)에 있습니다.

## 5. 폴더 구조

```
sagak/
├── README.md
├── CLAUDE.md          Claude 작업 규칙 (Karpathy 가이드라인 + 프로젝트 규칙)
├── docs/              기획안, 개발 계획서, 결정 기록, 노션 구성, 봇 테스트 시나리오
├── src/sagak/         Python 코드 (전사, 검증, Notion 동기화, 점검, 지도 링크, 안내 보내기)
├── scripts/           공개 레포 검사(커밋 전 금지어 확인) 등
├── agent/             Hermes profile `sagak` 파일 (SOUL.md, skills, 설정 예시)
├── recordings/        로컬 실제 녹음·전사 (커밋 안 됨)
└── tests/fixtures/    가상 테스트 데이터 (커밋 가능)
```

## 6. 실행과 테스트

업체별 값(접수 브랜드, 상품명과 고객 안내 이름)은 `agent/business.json`에 둡니다. 레포에는 예시 `agent/business.example.json`만 있으니 복사해서 고쳐 쓰세요(실제 파일은 커밋되지 않음).

```bash
python3 -m unittest discover -s tests -t .           # 단위 테스트 (표준 라이브러리만 사용)
PYTHONPATH=src python3 -m sagak demo                 # 키 없이 체험 (가상 상담 6건)
PYTHONPATH=src python3 -m sagak check tests/fixtures/extractions/s01.json   # 검증만
PYTHONPATH=src python3 -m sagak ping                 # Notion 접근 확인 (sagak profile 환경변수 필요)
PYTHONPATH=src python3 -m sagak announce --dry-run   # 봇 변경 안내 미리 보기 (--dry-run 빼면 텔레그램 발송 + [/new] 버튼)
PYTHONPATH=src python3 -m sagak console              # 개발자 PC 브라우저에서 변경 안내·요청 편집·미리 보기·보내기
PYTHONPATH=src python3 -m sagak sweep --dry-run      # 전체 이벤트 점검 미리 보기 (기록 때 자동 실행)
PYTHONPATH=src python3 -m sagak recheck-maps --dry-run  # 지도 링크 다시 확인 미리 보기
PYTHONPATH=src python3 -m sagak                      # 전체 명령 목록
```

봇에서는 `agent/skills/sagak-intake` 스킬이 `python3 -m sagak record`를 호출합니다.

## 7. 원칙

- API 키, 봇 토큰, 실제 고객 데이터, 업체 정보는 커밋하지 않습니다. 키는 Hermes 프로필 폴더의 `.env`에만 둡니다(이름 목록: [agent/README.md](agent/README.md)). 커밋 전 검사(`scripts/check_public.py`)가 금지어를 막습니다.
- 녹음과 고객 정보에 없는 내용은 추측하지 않고 `확인 필요`로 표시합니다.
- 기존 고객 정보는 덮어쓰지 않고, 상담은 매번 새 이력으로 추가합니다.

## 8. 개발 흐름

개발자 PC에 설치한 Hermes에서 profile `sagak`으로 개발하고, 운영은 컨테이너(개발자 PC → 클라우드)로 옮깁니다.
자세한 단계는 [개발 계획서](docs/dev-plan.md)를 보세요.
