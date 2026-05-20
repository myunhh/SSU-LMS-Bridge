# MCP 통합 모듈

LMS 데이터(공지·과제는 Notion DB, 강의자료는 Obsidian Vault)에 **LLM이 read/write로 접근**할 수 있도록, MCP(Model Context Protocol) 서버 두 개를 FastAPI 백엔드 안에 마운트하고 채팅 API에 연결한다.

> **담당:** MCP 연결 / LLM ↔ MCP tool-use 루프
> **범위:** `backend/app/mcp_client/*`, `backend/app/services/llm.py`, `backend/app/api/routes/chat.py`, `backend/app/api/deps.py`, `backend/app/config.py`, `backend/app/main.py`

---

## 1. 추가·변경 파일

### 신규 (3개)

| 파일 | 역할 |
|------|------|
| `mcp_client/sse_app.py` | `mcp.server.Server` 인스턴스를 SSE transport로 감싸 FastAPI에 mount 가능한 Starlette sub-app으로 변환 |
| `mcp_client/setup.py` | Notion / Obsidian MCP 서버를 한 번에 마운트하는 헬퍼 (`setup_mcp(app, settings)`) |
| `mcp_client/registry.py` | 여러 MCP 클라이언트를 prefix(`notion__` / `obsidian__`) 기반으로 묶어 LLM의 단일 tool 목록으로 노출하고, 호출을 dispatch |

### 수정 — 내 영역 (5개, 빈 파일 → 채움)

| 파일 | 역할 |
|------|------|
| `config.py` | pydantic-settings `Settings` 클래스. MCP 서버가 자기 자신에게 SSE 접속할 URL을 파생 프로퍼티(`notion_mcp_url`, `obsidian_mcp_url`)로 노출 |
| `main.py` | FastAPI 앱 부트, MCP 마운트, chat 라우터 등록. **다른 팀원이 라우터(courses/notices/assignments/sync)를 추가하기 좋게 TODO 블록 남김** |
| `api/deps.py` | `get_mcp_registry`, `get_chat_service` DI (싱글턴은 `lru_cache`) |
| `api/routes/chat.py` | `WS /api/chat` 스트리밍 + `POST /api/chat` 폴백 |
| `services/llm.py` | litellm 멀티 프로바이더 래퍼 + **MCP tool-use 멀티턴 루프** |

### 수정 — 팀원 영역 보강 (2개)

| 파일 | 변경 내용 | 이유 |
|------|-----------|------|
| `mcp_client/notion_server.py` | **read tool 2개 추가** (`query_notices`, `query_assignments`) + property 추출 헬퍼 (`_title/_select/_date/_checkbox/_number`) | 기존 코드는 write(`ensure_db`, `upsert_*`)만 제공. AI가 "이번 주 마감 과제 알려줘"에 답하려면 조회 도구가 필수 |
| `mcp_client/obsidian_server.py` | `write_file`이 **binary 파일(PDF/이미지)도 저장하도록** 처리 (mime_type 또는 `encoding` 인자 기반으로 base64 자동 디코드). **`search_files` tool 추가** (Local REST API `/search/simple/` 활용) | 기존 `write_file`은 base64 문자열을 디코드 안 하고 그대로 PUT → 강의자료가 base64 평문으로 저장되던 버그. search는 AI가 자료를 검색하려면 필요 |

---

## 2. 동작 흐름

```
┌─ Frontend (chat.jsx)
│      WebSocket /api/chat
│      {messages: [{role, content}, ...]}
│              ↓
├─ routes/chat.py  : chat_ws / chat_http
│              ↓
├─ services/llm.py : ChatService.stream()
│       ① registry.list_tools_openai()  ── 모든 MCP tool을 OpenAI 함수 스펙으로
│       ② litellm.acompletion(stream=True, tools=...)
│       ③ tool_calls 누적되면 dispatch, 텍스트는 chunk별 yield
│       ④ tool 결과를 messages에 붙여 다시 호출 (멀티턴, max=8)
│              ↓
├─ mcp_client/registry.py
│       prefix__name 으로 dispatch  (notion__query_notices → notion 클라이언트)
│              ↓
├─ mcp_client/base.py : MCPClientBase (SSE 클라이언트, 팀원 작성)
│              ↓  SSE
├─ mcp_client/sse_app.py + setup.py : FastAPI에 마운트된 SSE 엔드포인트
│       /mcp/notion/sse        (핸드셰이크)
│       /mcp/notion/messages/  (JSON-RPC POST)
│       /mcp/obsidian/sse
│       /mcp/obsidian/messages/
│              ↓
└─ mcp_client/notion_server.py / obsidian_server.py
       실제 Notion API · Obsidian Local REST API 호출
```

같은 백엔드 프로세스 안에서 MCP 서버와 클라이언트가 SSE로 통신한다. 외부 노드 프로세스나 stdio 자식 프로세스 관리가 필요 없다.

---

## 3. LLM이 호출 가능한 도구 (총 9개)

### Notion MCP (`notion__*`)

| Tool | 방향 | 인자 |
|------|------|------|
| `ensure_db` | write/init | `title`, `properties` |
| `upsert_notice` | write | `db_id`, `title`, `course_name`, `date`, `pinned?`, `unread?` |
| `upsert_assignment` | write | `db_id`, `title`, `course_name`, `due`, `type?`, `weight?`, `submitted?` |
| **`query_notices`** ✨ | **read** | `db_id`, `limit?`, `only_unread?`, `course_name?` |
| **`query_assignments`** ✨ | **read** | `db_id`, `limit?`, `only_upcoming?`, `days_ahead?`, `only_unsubmitted?`, `course_name?` |

### Obsidian MCP (`obsidian__*`)

| Tool | 방향 | 인자 |
|------|------|------|
| `write_file` (개선) | write | `relative_path`, `content`, `mime_type?`, `encoding?` (`utf-8`/`base64`) |
| `list_files` | read | — |
| `file_count` | read | — |
| **`search_files`** ✨ | **read** | `query`, `context_length?` |

---

## 4. 사용법 — 로컬 실행

### 4-1. `.env` 설정 (`backend/.env`)

```bash
# Notion
NOTION_TOKEN=secret_xxx                # https://www.notion.so/my-integrations
NOTION_ROOT_PAGE_ID=xxx                # MCP가 DB를 만들 부모 페이지

# Obsidian Local REST API 플러그인 (커뮤니티 플러그인)
OBSIDIAN_MCP_AUTH_CODE=xxx             # 플러그인 설정에서 발급한 API Key
OBSIDIAN_VAULT_PATH=                   # ⚠️ vault 내부 상대 경로 (보통 비워둠)

# LLM
LLM_PROVIDER=anthropic                 # openai | gemini | anthropic
LLM_API_KEY=sk-ant-...
LLM_MODEL=claude-haiku-4-5

BACKEND_PORT=8000
```

### 4-2. 의존성 / 실행

```bash
cd backend
pip install -e ".[dev]"
playwright install chromium            # LMS 로그인용 (다른 팀원 영역)
uvicorn app.main:app --reload --port 8000
```

### 4-3. 동작 확인

```bash
# 1. 서버 OK
curl http://localhost:8000/health
# → {"status":"ok"}

# 2. MCP 마운트 OK (SSE 응답이 흐르면 성공, Ctrl+C로 끊기)
curl -N http://localhost:8000/mcp/notion/sse

# 3. End-to-end tool-use (NOTION_TOKEN 설정 시)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"이번 주 마감 과제 알려줘"}]}'
```

---

## 5. WebSocket 이벤트 스키마 (Frontend 연동용)

클라이언트 → 서버:
```json
{ "messages": [ { "role": "user", "content": "이번 주 마감 과제 알려줘" } ] }
```

서버 → 클라이언트 (이벤트 단위로 순차 전송):
```json
{ "type": "tool_call",   "name": "notion__ensure_db", "args": {...} }
{ "type": "tool_result", "name": "notion__ensure_db", "result": "abc-123" }
{ "type": "tool_call",   "name": "notion__query_assignments", "args": {...} }
{ "type": "tool_result", "name": "notion__query_assignments", "result": "[{...}]" }
{ "type": "text",        "delta": "이번 주" }
{ "type": "text",        "delta": "에 마감인 과제는..." }
{ "type": "done" }
```

오류 시:
```json
{ "type": "error", "message": "..." }
```

---

## 6. ⚠️ 주의사항 (다른 팀원이 꼭 봐야 할 것)

### A. 환경 설정 — 실 동작 차단 가능

1. **`OBSIDIAN_VAULT_PATH`는 vault 내부 상대 경로**여야 함. `.env.example`의 `/path/to/ObsidianVault/LMS`는 가이드가 잘못된 것으로, 보통 **빈 문자열** 또는 vault 내부 폴더명(예: `LMS`)을 넣어야 한다. 절대 경로 넣으면 `/vault//path/...`처럼 슬래시 중복돼 404.
2. **Obsidian Local REST API 포트** — 플러그인 기본은 HTTPS:27124 / HTTP:27123. 현재 `obsidian_server.py:17`은 `http://localhost:27124`로 되어 있어 환경에 따라 안 맞을 수 있다. (팀원 코드 영역이라 이번 PR에서는 안 건드림)
3. **`LLM_MODEL=claude-haiku-4-5`** — litellm/Anthropic이 별칭을 그대로 받는지 미검증. 실패 시 정확한 모델 ID로 교체.

### B. Notion DB 이름 규약

`notion_server.py`의 read tool은 DB property 이름이 **"제목/과목/날짜/마감일/유형/비중(%)/제출완료/중요/읽음"** (한글, 띄어쓰기/괄호 포함)으로 만들어진 것을 가정한다. 이는 `services/notion_services.py`의 `NOTICE_DB_PROPS` / `ASSIGNMENT_DB_PROPS`와 일치해야 한다. **이 이름을 바꾸려면 양쪽을 모두 수정해야 함.**

### C. 동기화(`services/notion_services.py`, `vault_service.py`)는 누가 호출?

이번 PR에서는 동기화 트리거(`routes/sync.py`, APScheduler)를 만들지 않았다. 동기화 담당자가:
- `routes/sync.py`에 `POST /api/sync` 엔드포인트를 만들고
- 내부에서 `sync_notion(notices, assignments, settings.notion_mcp_url, settings.notion_token)` 와 `sync_vault(materials, lms_client, settings.obsidian_mcp_url, settings.obsidian_mcp_auth_code, progress_cb)` 호출

`Settings`에 이미 `notion_mcp_url` / `obsidian_mcp_url`이 파생 프로퍼티로 노출되어 있으니 그대로 쓰면 된다.

### D. `vault_service.py:7` `MANIFEST_PATH`

`Path("_manifest.json")`로 작업 디렉토리 상대경로. uvicorn 실행 위치에 따라 매번 다른 곳에 생성된다. **동기화 담당자**가 settings 기반 절대 경로로 옮기는 것이 좋다. (이번 PR 범위 밖)

### E. `main.py`의 `@app.on_event("startup")`

FastAPI에서 deprecated이지만 동작은 한다. 다른 팀원이 라우터를 추가하는 김에 lifespan으로 옮기는 것을 권장.

### F. 모듈 import 영향

- `pyproject.toml` 의존성은 **변경 없음** (`mcp>=1.0.0`, `notion-client>=2.2.1`, `litellm>=1.40.0` 이미 포함됨).
- `httpx`, `loguru`, `pydantic-settings`도 기존에 있음.

---

## 7. 알려진 한계 / TODO

| # | 항목 | 우선순위 |
|---|------|---------|
| 1 | `ChatService.stream`이 매번 `registry.list_tools_openai()`로 두 MCP에 SSE 연결을 새로 열어 tools 조회 → 부하 증가. tools 캐싱 권장 | 중 |
| 2 | `ensure_db` 결과(DB ID)를 매 turn마다 LLM이 호출 — Settings/Redis 등에 캐시하면 호출 절약 | 중 |
| 3 | `obsidian_server.py` `read_resource`는 `resp.text` 사용 → binary 파일은 깨짐 (텍스트 노트만 가정) | 낮 |
| 4 | 단위 테스트 부재 — `tests/test_mcp_*.py` 필요 (특히 tool-use 루프 mock 테스트) | 중 |
| 5 | `OBSIDIAN_VAULT_PATH` 가이드 (.env.example 수정) | 낮 |
| 6 | `main.py`를 lifespan 핸들러로 마이그레이션 | 낮 |

---

## 8. 다른 팀원 영역과의 인터페이스

내 영역이 외부에 노출하는 것:
- **Settings 객체** (`app.config.get_settings()`) — `notion_mcp_url`, `obsidian_mcp_url`, `notion_token`, `obsidian_mcp_auth_code` 등 모든 환경 변수 접근
- **`setup_mcp(app, settings)`** — 이미 `main.py`에서 호출됨. 다시 부를 필요 없음
- **`chat.router`** — 이미 `/api`에 등록됨

내 영역이 의존하는 것 (다른 팀원 영역):
- **없음.** chat은 LMS adapter나 동기화 결과에 직접 의존하지 않는다. Notion/Obsidian 데이터에만 의존하므로 동기화가 먼저 한 번 돌아 있어야 의미 있는 답이 나옴.

---
*문의 / 변경 사항은 PR 코멘트로 부탁드립니다.*
