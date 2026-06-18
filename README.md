# SSU-LMS-Bridge

숭실대학교 캡스톤 프로젝트

숭실대 스마트캠퍼스 LMS(`lms.ssu.ac.kr`, Canvas 기반)의 강의·공지·과제·자료·**출석·성적**을 가져와
**FastAPI 백엔드 + React 프론트엔드 + LLM 채팅(in-process MCP 6종)**으로 통합하고,
**Notion·Obsidian 동기화**와 **강의자료 원본 파일 다운로드**까지 자동화하는 웹 앱.

```
SSU LMS (Canvas / LearningX / commons · SSO)
   │  Playwright SSO 로그인 + httpx (LearningX Bearer · Canvas 쿠키 폴백)
   ▼
FastAPI 백엔드 (단일 프로세스 · :8000)
   ├─ 라우트(REST/WS)  /api/lms · courses · assignments · notices · sync · chat · connectors · mcp
   ├─ 서비스           sync · attendance(출석율) · material(자료 다운로드) · vault · notion · notify
   ├─ APScheduler      매일 동기화(SYNC_HOUR) · 세션 갱신 · 알림 스캔
   └─ in-process MCP 6종 (SSE · /mcp/{name}/sse)  ← ChatService(litellm)가 LLM tools 로 노출
        lms · study · grades · materials · notion · obsidian
   ▼  외부 연동
   Notion · Obsidian(Local REST API) · Gemini(litellm) · SMTP
   ▲
React + Vite 프론트엔드 (:3000)   대시보드 · 캘린더 · 학습 비서 · 커넥터 · MCP
```

---

## 핵심 기능

| 기능 | 설명 |
|---|---|
| **LMS 로그인 · 세션** | Playwright 헤드리스 Chromium 으로 SSU SSO(`smartid.ssu.ac.kr`) 로그인 → 세션을 `.cache/session_state.json`(0600) 에 저장·연장. APScheduler 주기 갱신 |
| **데이터 조회** | 강의 / 과제(마감·제출현황) / 공지 / 자료 / 토론 REST API + 본문 HTML→평문 변환 |
| **출석율(진도율)** | `Course.progress` = **출결현황 기준 출석율**(출석 일수 / 전체 일수). 과목 '출결현황' LTI 를 1회 런치(보기 전용)해 `lessons/attendances` 를 읽어 계산·캐시 |
| **강의자료 원본 다운로드** | 주차학습(LTI) 뒤의 **PPT/PDF/문서 원본**을 commons 에서 받아 Obsidian `강의자료/{과목}/` 에 저장. 항목별 매니페스트로 **항목당 LTI 런치 1회**(출석 보호) |
| **동기화** | 수동(`POST /api/sync`) + 예약(매일 `SYNC_HOUR`시) · 동시 실행 가드. 출석율 계산 → Notion DB upsert → Obsidian Vault push → 강의자료 파일 다운로드 → 이메일 |
| **LLM 채팅 (학습 비서)** | WebSocket 스트리밍(`/api/chat`) · litellm 멀티턴 도구 호출 루프(기본 Gemini). **MCP 6종**을 LLM tools 로 노출 |
| **MCP 페이지** | `/mcp` 전용 페이지에서 6종 서버 상태·도구 목록·설명 확인, 도구별 **"실행" 버튼** → 학습 비서가 그 도구를 호출해 결과 응답 |
| **커넥터 관리** | `GET /api/connectors/status` 상태 일괄 조회, `POST /api/connectors/config` 로 키를 루트 `.env` 저장 (LLM 즉시 반영, Notion/Obsidian 재시작 후) |
| **이메일 알림** | SMTP 설정 시 마감 임박·신규 공지 디제스트 발송. 미설정이면 no-op (푸시·데스크탑은 범위 밖) |

---

## in-process MCP 6종

같은 FastAPI 프로세스에 SSE 서브앱(`/mcp/{name}/sse`)으로 마운트되고, `ChatService` 가 `McpRegistry`
를 통해 `prefix__name`(예: `lms__list_deadlines`) 으로 평탄화해 LLM 에 노출한다.

| MCP | 마운트 | 도구 | 소스 |
|---|---|---|---|
| `lms__*` | 상시 | 6 — list_courses/assignments/deadlines/notices/materials/discussions | SSU LMS (실시간) |
| `study__*` | 상시 | 8 — save/list/get/delete_quiz · save/list_deck · review_due · grade_card (SM-2 SRS) | 로컬 JSON `.cache/study` |
| `grades__*` | 상시 | 2 — list(과목별 점수) · summary(평균·GPA 추정) | SSU LMS 성적 |
| `materials__*` | Obsidian 설정 시 | 3 — list_files · read(본문 추출) · search(키워드 RAG) | Obsidian 강의자료 파일 |
| `notion__*` | Notion 설정 시 | 5 — ensure_db · upsert/query notice·assignment | Notion API |
| `obsidian__*` | Obsidian 설정 시 | 4 — write_file · list_files · file_count · search_files | Obsidian Local REST API |

> 상태는 `GET /api/mcp/status` (실측 SSE 핸드셰이크) 로 조회, 프론트 `/mcp` 페이지에 표시.

---

## 디렉터리 구조

```
ssu-lms-bridge/
├── .env              # 백엔드 환경 변수 (루트 — .env.example 참고, Git 제외)
├── .venv/            # 공용 Python 가상환경 (루트에 하나)
├── .cache/           # 세션·출석율·study JSON·다운로드 매니페스트 (Git 제외)
├── backend/          # FastAPI Python 백엔드
│   ├── app/
│   │   ├── adapter/      # SSO 인증(Playwright) + Canvas/LearningX 클라이언트 + courses/assignments/notices/materials/grades
│   │   ├── api/
│   │   │   ├── deps.py        # 공용 의존성 (CanvasClient · MCP 레지스트리)
│   │   │   ├── session_meta.py # 세션 만료·갱신 상수 (프론트와 공유)
│   │   │   └── routes/        # REST + WebSocket + /api/mcp/status
│   │   ├── mcp_client/   # MCP 서버 6종(lms·study·grades·materials·notion·obsidian) + SSE 클라이언트
│   │   ├── services/     # llm(챗) · sync · attendance(출석율) · material(자료 다운로드) · vault · notion · notify
│   │   ├── config.py · models.py · main.py
│   ├── tests/            # pytest (오프라인, 338개)
│   └── pyproject.toml
└── frontend/         # React + Vite 프론트엔드
    └── src/
        ├── api/          # 백엔드 호출 + 스키마 어댑터
        ├── auth/         # 클라이언트 사이드 계정 저장소
        ├── data/         # DataStore (단일 데이터 소스)
        ├── pages/        # dashboard · calendar · chat · connectors · mcp · course-detail · settings
        └── App.jsx · main.jsx
```

---

## 빠른 시작

### Backend

```bash
# 1) 가상환경 — 프로젝트 루트의 .venv 하나만 (Python 3.11+)
python3 -m venv .venv && source .venv/bin/activate
(cd backend && pip install -e ".[dev]")
playwright install chromium              # 최초 1회 (SSO 로그인용)

# 2) .env — 프로젝트 루트에 위치 (.env.example 복사 후 값 입력)
cp .env.example .env

# 3) 서버 실행 — 반드시 backend/ 에서 (app.* import 경로 때문)
cd backend && uvicorn app.main:app --reload --port 8000
```

→ `http://localhost:8000/docs` 에서 Swagger UI · 테스트: `cd backend && python -m pytest -q`

### Frontend

```bash
cd frontend && npm install && npm run dev
```

→ `http://localhost:3000` (`/api` 는 자동으로 8000 포트로 프록시)

---

## 기술 스택

**Backend (Python 3.11+)**
- FastAPI + Uvicorn (REST + WebSocket) · Starlette (MCP SSE 서브앱)
- Playwright (SSO 로그인 · LTI 런치 · 출결현황/자료 수집)
- httpx (Canvas/LearningX/commons) + BeautifulSoup4 (본문 HTML→평문)
- litellm (Gemini 기본 · OpenAI/Anthropic/Groq/Ollama 호환)
- mcp (Model Context Protocol SDK) · notion-client
- pypdf · python-pptx · python-docx (강의자료 본문 추출 — RAG MCP)
- pydantic-settings · loguru · APScheduler · smtplib(이메일)
- pytest · pytest-asyncio · ruff

**Frontend**
- React 18 + React Router 6 · Vite 5 · Tailwind CSS(CDN) · JavaScript(TS 미사용)

---

## 주의사항

- ⚠️ `.env` 는 **절대 Git 에 커밋하지 마세요** (LMS/Notion/LLM 자격증명 포함)
- LLM 기본 프로바이더는 **Gemini** — `.env` 의 `LLM_API_KEY`(Google AI Studio). `LLM_PROVIDER`/`LLM_MODEL` 로 교체 가능(Groq·Ollama 등). 키는 커넥터 페이지에서도 저장(즉시 반영)
- Notion/Obsidian/SMTP 키는 커넥터 페이지(`POST /api/connectors/config`) 또는 `.env` 직접 입력. MCP(Notion/Obsidian/Materials) 마운트는 **백엔드 재시작 후** 반영
- **강의자료 다운로드·출석율 계산은 주차학습/출결현황 LTI 를 런치**한다. 출결현황은 보기 전용이라 출석을 새로 찍지 않지만, 개별 주차학습 항목 런치는 진도/출결을 기록할 수 있어 매니페스트로 **항목당 1회**만 런치한다
- 스마트캠퍼스 LMS 는 매일 **새벽 3시** 데이터 갱신 → 동기화는 **오전 4시 이후** 권장 (`SYNC_HOUR`)
- LMS 는 두 호스트(`lms.ssu.ac.kr` LearningX/Bearer · `canvas.ssu.ac.kr` Canvas/쿠키)를 폴백하며 사용. ⚠️ Canvas 호스트에 Bearer 를 보내면 쿠키 세션이 깨지므로 호스트별 인증을 분리한다
</content>
