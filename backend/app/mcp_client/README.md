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
| `mcp_client/lms_server.py` | LMS adapter를 in-process MCP 서버로 노출 (`lms__*` 실시간 직접 조회, 읽기 전용). 토큰 없어 무조건 마운트, 세션 라이프사이클은 도구 호출 단위로 관리 |
| `mcp_client/study_server.py` | 학습 도우미(`study__*`) — 공지/과제 본문으로 만든 퀴즈·플래시카드를 로컬 JSON에 저장/조회/복습. **토큰 없는 항상-마운트 MCP의 2번째 사례** (LMS와 동일 규약). 외부 의존 0, SRS(SM-2 경량)로 복습 간격 관리 |
| `mcp_client/setup.py` | LMS / Study / Notion / Obsidian MCP 서버를 한 번에 마운트하는 헬퍼 (`setup_mcp(app, settings)`) |
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

## 3. LLM이 호출 가능한 도구

### LMS MCP (`lms__*`) — 실시간 직접 조회 (읽기 전용)

`mcp_client/lms_server.py`. LMS adapter(courses/assignments/notices/materials)를 그대로 노출해 LLM이 강의·과제·공지·자료를 **실시간** 조회한다. Notion(하루 1회 동기화 스냅샷)보다 최신이라 마감/신규 공지는 이쪽이 더 정확. 토큰이 없어 **무조건 마운트**(`/mcp/lms`)되고, 세션 파일이 없으면 도구가 한국어 안내(`NO_SESSION_MSG`)를 반환한다(예외로 안 죽음). 세션 만료(401)는 가드하지 않고 전파 → `base.py`가 `RuntimeError`로 변환 → LLM이 재로그인 안내.

| Tool | 방향 | 인자 |
|------|------|------|
| `list_courses` | read | — |
| `list_assignments` | read | `course_id` (required) |
| `list_deadlines` | read | — (전 과목 마감, 오름차순) |
| `list_notices` | read | `course_id` (optional, 생략 시 전 과목 통합) |
| `list_materials` | read | `course_id` (required) |
| `list_discussions` | read | `course_id` (required) |

### Study MCP (`study__*`) — 학습 도우미 (퀴즈 · 플래시카드 · SRS)

`mcp_client/study_server.py`. 공지/과제 본문으로 만든 **퀴즈·플래시카드를 저장/조회/복습**한다. LMS와 같은 **토큰 없는 항상-마운트** MCP(`/mcp/study`)의 2번째 사례 — `setup.py` 무조건 마운트 ↔ `deps.py:_build_registry` 무조건 등록이 짝이라야 미마운트 URL에 클라이언트가 붙는 불일치를 막는다. 외부 의존 0이고 저장소는 로컬 JSON 2종(`.cache/study/quizzes.json`·`decks.json`, 경로는 `_store_dir()` 파생)뿐이라 세션/`_client_cm`이 없다.

> **역할 분담:** 퀴즈 문항·카드의 *생성*은 채팅 LLM 몫이다. LLM이 `lms__list_notices`/`list_assignments`로 본문을 읽어 문항을 만든 뒤 `study__save_quiz`/`save_deck`로 **저장만** 한다 — MCP 안에서 LLM을 재호출하지 않으며 `litellm` import도 두지 않는다.

| Tool | 방향 | 인자 |
|------|------|------|
| `save_quiz` | write | `title`, `questions[]`, `id?`, `source?` (upsert — id 있으면 덮어쓰기) |
| `list_quizzes` | read | `course?`, `limit?` (본문 제외 메타 목록) |
| `get_quiz` | read | `id` (문항·정답·해설 전체) |
| `delete_quiz` | write | `id` (멱등 — 없어도 ok:false) |
| `save_deck` | write | `title`, `cards[]`, `id?`, `source?`, `now?` (id 갱신 시 동일 front+back 카드 SRS 보존) |
| `list_decks` | read | `course?`, `now?` (덱별 due_count 포함) |
| `review_due` | read | `deck_id?`, `now?`, `limit?` (due<=now 카드만, due asc·card_id 정렬) |
| `grade_card` | write | `deck_id`, `card_id`, `correct`, `now?` (SRS 재계산·저장) |

**SRS(SM-2 경량):** ease(기본 2.5, 하한 1.3), interval(일), reps. 정답 시 `reps==1→interval=1`, `==2→3`, 이후 `round(interval*ease)`이며 `ease += 0.1`. 오답 시 `reps=0`·`interval=1`·`ease=max(1.3, ease-0.2)`. 신규 카드는 `due=now`라 즉시 복습 대상. 모든 시각 계산은 순수 함수 `_apply_review(card, correct, now)`에 모여 있고 `now`를 인자로 받아 **결정적**(테스트가 정확한 due/interval/ease 단언) — `save_deck`/`list_decks`/`review_due`/`grade_card`에 `now`를 주입할 수 있다.

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

`notion_server.py`의 read tool은 DB property 이름이 **"제목/과목/날짜/마감일/유형/배점/제출완료/중요/읽음"** (한글, 띄어쓰기 포함)으로 만들어진 것을 가정한다. 이는 `services/notion_services.py`의 `NOTICE_DB_PROPS` / `ASSIGNMENT_DB_PROPS`와 일치해야 한다. **이 이름을 바꾸려면 양쪽을 모두 수정해야 함.**

> **'배점' property (#8):** 과거엔 `비중(%)`(percent 포맷)에 `points_possible / 100`을 저장해 배점 100점이 100%로 왜곡됐다. 지금은 `배점`(일반 number)에 `points_possible`을 **그대로** 저장한다 (`upsert_assignment`의 `/100` 제거). 라벨을 `비중(%)`→`배점`으로, 포맷을 percent→number로 바꾸면서 `notion_services.py:ASSIGNMENT_DB_PROPS`·`notion_server.py`(upsert/query)·`routes/sync.py` payload·`CLAUDE.md`의 property 목록을 모두 맞췄다.

> **'유형' 라벨 (#12):** Notion '유형' select 에는 원시 Canvas 코드(`online_upload` 등)가 아니라 앱 화면과 통일된 한글 라벨이 들어간다. 백엔드 단일 소스 `models.py:SUBMISSION_TYPE_LABELS`(`online_upload→과제(보고서)`/`online_text_entry→에세이`/`online_quiz→퀴즈`/`discussion_topic→토론`, 폴백 `기타`)를 `routes/sync.py`가 payload 조립 시 매핑한다 — 프론트 `api/index.js`의 `SUBMISSION_TYPE_MAP`(report/essay/quiz 표시 키)과 의미가 어긋나지 않게 유지.

### C. 동기화(`services/notion_services.py`, `vault_service.py`)는 누가 호출?

`routes/sync.py:perform_sync()`(수동 `POST /api/sync` + APScheduler 예약 공용)가 호출한다:
- `sync_notion(notices, assignments, settings.notion_mcp_url, settings.notion_token)` — Notion 설정 시
- `sync_obsidian(notices, assignments, settings.obsidian_mcp_url, settings.obsidian_mcp_auth_code)` — Obsidian 설정 시 (`is_configured(obsidian_mcp_auth_code)` 가드, setup.py 마운트 조건과 동일)

`sync_obsidian` 은 공지/과제를 `공지/{과목}/{제목}.md`·`과제/{과목}/{제목}.md` markdown 노트로 push 한다 (강의자료 파일은 LTI 뷰어 뒤라 범위 밖). manifest(sha256)로 변경 없는 노트는 건너뛴다. `Settings`에 `notion_mcp_url` / `obsidian_mcp_url`이 파생 프로퍼티로 노출되어 있다.

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
| 3 | 단위 테스트 부재 — `tests/test_mcp_*.py` 필요 (특히 tool-use 루프 mock 테스트) | 중 |
| 4 | `OBSIDIAN_VAULT_PATH` 가이드 (.env.example 수정) | 낮 |
| 5 | `main.py`를 lifespan 핸들러로 마이그레이션 | 낮 |

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
