# SSU-LMS-Bridge

숭실대학교 캡스톤 프로젝트

숭실대 스마트캠퍼스 LMS(`lms.ssu.ac.kr`)의 강의·공지·과제·자료를 가져와
**FastAPI 백엔드 + React 프론트엔드 + LLM 채팅(MCP 도구 호출)**으로 통합 제공하는 웹 앱.

```
LMS (SSO + Canvas REST API)
   └─ FastAPI Backend (단일 프로세스)
         ├─ /api/lms/*        Playwright SSO 로그인 · 세션 관리 (주기 갱신 스케줄러)
         ├─ /api/courses, /api/assignments, /api/notices, /api/.../discussions
         ├─ /api/sync         수동 + APScheduler 예약 동기화 (매일 SYNC_HOUR시)
         │                    → Notion DB upsert + Obsidian Vault markdown push
         ├─ /api/chat         WebSocket 스트리밍 (litellm — 기본: gemini)
         ├─ /api/connectors/status   외부 연동 상태 (LMS/Notion/Obsidian/LLM)
         ├─ /api/connectors/config   커넥터 키를 루트 .env 로 저장
         ├─ 이메일 알림        마감 임박·신규 공지 SMTP 발송 (설정 시, 스캔 스케줄러)
         └─ /mcp/lms, /mcp/notion, /mcp/obsidian   MCP 서버 (SSE, 같은 프로세스에 마운트)
              ↑ ChatService 가 이 MCP 도구들을 LLM tools 로 노출
              │   - lms__*      : 강의·과제·공지·자료 실시간 조회 (Canvas REST)
              │   - notion__*   : 동기화된 Notion DB 조회/쓰기
              │   - obsidian__* : Obsidian Vault 노트 조회/쓰기
              ↓
         React Frontend (Vite)
```

---

## 디렉터리 구조

```
ssu-lms-bridge/
├── .env              # 백엔드 환경 변수 (루트에 위치 — .env.example 참고)
├── .venv/            # 공용 Python 가상환경 (루트에 하나만)
├── backend/          # FastAPI Python 백엔드
│   ├── app/
│   │   ├── adapter/      # LMS SSO 인증(Playwright) + Canvas API 클라이언트
│   │   ├── api/
│   │   │   ├── deps.py   # 공용 의존성 (CanvasClient, MCP 레지스트리)
│   │   │   ├── session_meta.py  # 세션 만료·갱신 상수 (프론트와 공유)
│   │   │   └── routes/   # REST + WebSocket 엔드포인트
│   │   ├── mcp_client/   # LMS·Notion·Obsidian MCP 서버 + SSE 클라이언트
│   │   ├── services/     # LLM 채팅 · Notion/Obsidian 동기화 · 이메일 알림
│   │   ├── config.py
│   │   ├── models.py
│   │   └── main.py
│   ├── tests/
│   └── pyproject.toml
└── frontend/         # React + Vite 프론트엔드
    ├── src/
    │   ├── api/          # 백엔드 호출 함수 (스키마 어댑터 포함)
    │   ├── auth/         # 클라이언트 사이드 계정 저장소
    │   ├── components/
    │   ├── data/         # DataStore (단일 데이터 소스)
    │   ├── pages/
    │   ├── App.jsx
    │   └── main.jsx
    ├── package.json
    └── vite.config.js
```

---

## 빠른 시작

### Backend

```bash
# 1) 가상환경 — 프로젝트 루트의 .venv 하나만 사용 (Python 3.11+)
python3 -m venv .venv
source .venv/bin/activate
(cd backend && pip install -e ".[dev]")
playwright install chromium              # 최초 1회 (SSO 로그인용)

# 2) .env — 프로젝트 루트에 위치 (.env.example 복사 후 값 입력)
cp .env.example .env

# 3) 서버 실행 — 반드시 backend/ 에서 실행 (app.* import 경로 때문)
cd backend
uvicorn app.main:app --reload --port 8000
```

→ `http://localhost:8000/docs` 에서 Swagger UI 확인

테스트 실행:

```bash
cd backend && python -m pytest -q
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

→ `http://localhost:3000` 접속 (`/api`는 자동으로 8000 포트로 프록시)

---

## 구현된 기능

- **LMS 로그인 · 세션** — Playwright 헤드리스 Chromium 으로 SSU SSO(`smartid.ssu.ac.kr`) 로그인, 세션을 `.cache/session_state.json`(0600)에 저장·연장 (`/api/lms/*`). APScheduler 가 주기적으로 세션을 갱신
- **데이터 조회** — 강의 / 과제(마감·제출현황) / 공지 / 자료 / 토론 REST API (`/api/courses`, `/api/assignments`, `/api/notices`, `/api/courses/{id}/discussions`). 본문 HTML→평문 변환 포함
- **동기화** — 수동(`POST /api/sync`) + APScheduler 예약(매일 `SYNC_HOUR`시), 동시 실행 가드. Notion 설정 시 공지·과제를 Notion DB 로 upsert, Obsidian 설정 시 공지/과제를 Vault markdown 으로 push
- **LLM 채팅** — WebSocket 스트리밍(`/api/chat`), **LMS·Notion·Obsidian MCP 도구**를 LLM tools 로 노출하는 멀티턴 도구 호출 루프(기본 모델 Gemini). `lms__*` 도구로 강의·과제·공지·마감을 **실시간** 조회
- **커넥터 관리** — `GET /api/connectors/status` 로 LMS/Notion/Obsidian/LLM 상태 일괄 조회, `POST /api/connectors/config` 로 키를 루트 `.env` 에 저장(가입 마법사·커넥터 페이지에서 입력). LLM 키는 즉시 반영, Notion/Obsidian 은 재시작 후 반영
- **이메일 알림** — SMTP 설정 시 마감 임박 과제·신규 공지를 디제스트 메일로 발송(스캔 스케줄러). 미설정이면 no-op. 푸시·데스크탑 알림은 범위 밖

---

## 기술 스택

**Backend**
- Python 3.11+
- FastAPI + Uvicorn (REST + WebSocket)
- Playwright (LMS SSO 로그인)
- httpx (Canvas REST API 클라이언트) + BeautifulSoup4 (공지/과제 본문 HTML→평문)
- litellm (Gemini(기본) / OpenAI / Anthropic 멀티 프로바이더)
- mcp + notion-client (LMS / Notion / Obsidian MCP 서버 — 같은 프로세스에 SSE 마운트)
- pydantic-settings, loguru, APScheduler, smtplib(이메일 알림)

**Frontend**
- React 18 + React Router
- Vite (개발 서버 + 번들러)
- JavaScript (TypeScript X)

---

## 주의사항

- ⚠️ `.env` 파일은 **절대 Git 에 커밋하지 마세요** (자격증명 포함)
- LLM 기본 프로바이더는 **Gemini** — `.env` 의 `LLM_API_KEY` 에 Google AI Studio 키를 넣으세요 (`LLM_PROVIDER`/`LLM_MODEL` 로 변경 가능)
- Notion/Obsidian/LLM/SMTP 키는 `.env` 직접 편집 외에 **가입 마법사·커넥터 페이지**에서도 저장할 수 있습니다 (`POST /api/connectors/config`). LLM 키는 즉시, MCP(Notion/Obsidian) 키는 백엔드 재시작 후 반영
- 스마트캠퍼스 LMS 는 매일 **새벽 3시** 데이터 갱신 → 동기화는 **오전 4시 이후** 권장 (`SYNC_HOUR`)
- LMS 는 SPA 구조 → 로그인은 `Playwright` 필수, 이후 데이터 조회는 `lms.ssu.ac.kr`(LearningX, Bearer)·`canvas.ssu.ac.kr`(Canvas, 쿠키) 두 호스트를 폴백하며 활용
