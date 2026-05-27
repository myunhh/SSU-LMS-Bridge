# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

숭실대학교 LMS Bridge — a capstone web app that bridges SSU's Smart Campus LMS (`lms.ssu.ac.kr`, Canvas-based) into a FastAPI backend + React frontend with an LLM chat layer that can read/write Notion and Obsidian via MCP.

Comments, log messages, user-facing strings, and the README are all in Korean. Match that style when editing.

## Common commands

Backend (run from `backend/`):

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium                       # one-time, for SSO login
uvicorn app.main:app --reload --port 8000         # MUST run from backend/ so `app.*` imports resolve
pytest                                            # tests dir is currently empty; asyncio_mode = auto
pytest tests/test_foo.py::test_bar                # single test
ruff check .                                      # lint (line 100, py311, selects E/F/I/UP, ignores E501)
```

Frontend (run from `frontend/`):

```bash
npm install
npm run dev        # Vite on :3000, proxies /api → :8000
npm run build      # output to dist/
npm run preview
```

Quick smoke tests:

```bash
curl http://localhost:8000/health                 # FastAPI alive
curl -N http://localhost:8000/mcp/notion/sse      # MCP SSE handshake (Ctrl+C to stop)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"이번 주 마감 과제 알려줘"}]}'
```

## Architecture

### Backend (FastAPI single-process)

`backend/app/main.py` boots one FastAPI app that does four things in `lifespan`: configures loguru, schedules a daily APScheduler sync at `SYNC_HOUR:00`, mounts two MCP servers as Starlette sub-apps, and registers REST routers. There's a global `HTTPStatusError` handler that maps upstream 401/403/419 → 401 ("재로그인 필요") and everything else → 502 — adapters can just `raise_for_status` without per-route try/except.

**SSU has two API hosts with different auth, and they conflict.**
`adapter/canvas_client.py` is the only place that knows this:

- `lms.ssu.ac.kr/learningx/api/v1` — LearningX, **Bearer `xn_api_token`** from localStorage
- `canvas.ssu.ac.kr/api/v1` — Canvas, **session cookies only** (no Bearer)

⚠️ Canvas evaluates `Authorization: Bearer` before cookies. Sending a Bearer to Canvas — even a valid LearningX one — kills the cookie session with `Invalid access token`. `CanvasClient._headers_for(use_canvas)` enforces this and is the reason adapters pass `use_canvas=True` selectively. Don't add `Authorization` to the default headers.

Adapters (`adapter/courses.py`, `assignments.py`, `notices.py`, `materials.py`) are pure async functions that take a `CanvasClient`, fall back from LearningX to Canvas on failure, and return Pydantic models from `models.py`. `list_courses` does an N+1 fan-out for professor + progress; use `list_course_ids` when you only need IDs (e.g., the `/assignments/todos` and combined-notices routes).

**Session lifecycle is Playwright-driven.** `adapter/auth.py:SSULMSAuthPlaywright.login()` launches headless Chromium against `smartid.ssu.ac.kr` SSO, stores cookies + storage_state into `.cache/session_state.json` (path from `settings.session_cache_abspath`). `load_session()` revalidates *and* extends — it's invoked by both `POST /api/lms/session/refresh` and the start of every `/api/sync`. The `session_keeper_loop` in `auth.py` is standalone (not wired into the FastAPI app); current session extension happens via the manual refresh route or piggy-backed onto sync.

**Sync is one function, two entry points.** `routes/sync.py:perform_sync()` is shared by the manual `POST /api/sync` route and `run_scheduled_sync()` (APScheduler). Steps: verify+extend session → CanvasClient → collect → optionally push to Notion DB via MCP (only if `notion_token` and `notion_root_page_id` are real, not placeholder `xxxx`). Errors are appended to `SyncResult.errors`, not raised — except `SyncSessionError` which becomes HTTP 401/503. Module-level `_state` dict tracks `running`/`last_sync_at` (resets on process restart).

**Routes are thin.** `api/routes/*.py` just call adapters and dump models; the work is in adapters. `api/deps.py:get_canvas_client` is a yield-style dependency that init/closes the client per request and converts `FileNotFoundError` (no session file) → 503.

### MCP (in-process)

Notion + Obsidian MCP servers run as Starlette sub-apps mounted at `/mcp/notion` and `/mcp/obsidian` **in the same FastAPI process** (`mcp_client/setup.py`). The chat service then opens SSE clients back to those URLs (`MCPClientBase` in `mcp_client/base.py`), so `Settings.notion_mcp_url` is just `http://localhost:{backend_port}/mcp/notion/sse`. No external Node process or stdio child to manage.

⚠️ `mcp_client/sse_app.py` builds the sub-app. Pass only the relative `"/messages/"` to `SseServerTransport` — the MCP SDK auto-prefixes the ASGI mount root_path when it emits SSE endpoint events. Adding the prefix here too yields paths like `/mcp/notion/mcp/notion/messages/`.

`McpRegistry` (`mcp_client/registry.py`) flattens both MCPs into one OpenAI-spec tool list using `prefix__name` (e.g., `notion__query_assignments`) and dispatches calls back to the right client by splitting on `__`. Prefixes must not contain `__`.

`services/llm.py:ChatService.stream()` is a multi-turn `tools` loop (max 8 iterations) over `litellm.acompletion(stream=True)`. Provider prefix is added to the model name for non-OpenAI providers (`anthropic/claude-haiku-4-5`). It yields events typed as `text | tool_call | tool_result | error | done`; both the WebSocket route and the POST fallback consume the same generator.

The system prompt in `services/llm.py:SYSTEM_PROMPT` instructs the LLM to call `notion__ensure_db` first to resolve Notion DB IDs, then query. Notion DB property names are Korean and must match `services/notion_services.py:NOTICE_DB_PROPS` / `ASSIGNMENT_DB_PROPS` exactly (`제목/과목/날짜/마감일/유형/비중(%)/제출완료/중요/읽음`). Changing one side requires changing the other.

### Frontend (React 18 + Vite, no TS)

- **No build-step Tailwind.** Tailwind comes from the CDN script in `index.html` along with Pretendard/Inter — pages can use Tailwind classes directly. CSS variables (`--accent`, `--bg`, etc.) defined inline in `index.html` and overridden at runtime by `AppLayout` in `App.jsx`.
- **`DataStore.jsx` is the single source of truth.** Pages call `useData()`; never `fetch` directly from page components. Initial load runs `Api.fetchInitialBundle()` (parallel `courses` + `assignments` + `notices`) on mount.
- **`api/index.js` adapts backend schemas to frontend field names.** Backend Pydantic models use snake_case + canonical Canvas shapes (e.g., `Course.name` is literally `"고급프로그래밍 (2150164103)"`). The `adaptCourse / adaptNotice / adaptAssignment` functions in `api/index.js` split the name/code, convert `progress` from 0-100 to 0-1, invert `is_read` → `unread`, and derive a per-course color from the ID. Add new backend fields here, not in the page components.
- **`USE_MOCK` toggles** in `api/index.js` and `api/lmsAuth.js` switch each module between real fetch and `mockData.js` seeds — useful for UI work without a running backend. Currently both `false`.
- **Auth is client-side only for now.** `auth/AccountStore.js` stores accounts in `localStorage` with SHA-256 + salt password hashes; there's no backend `/api/auth/*` yet. The LMS credentials entered at signup live next to it (currently plaintext — flagged in code comments).
- **LMS session calls** go through `api/lmsAuth.js` (`POST /api/lms/login`, etc.). Frontend never sees cookies / storage_state — only `userInfo` + `savedAt` metadata.
- **Chat is WebSocket-streamed.** `api/chat.js:openChatStream` sends `{messages}` once on open and dispatches typed events to callbacks; both sides assume the schema in `services/llm.py`.

### Environment / config

`backend/app/config.py` reads **the project-root `.env`** (`parents[2]` from config.py) — *not* `backend/.env`. `frontend/.env` is separate. Pydantic-settings ignores unknown keys. Derived properties to know:

- `settings.session_cache_abspath` — resolves relative `SESSION_CACHE_PATH` against project root. Always use this, not raw `SESSION_CACHE_PATH`.
- `settings.notion_mcp_url` / `obsidian_mcp_url` — built from `backend_port`. Used by `deps.get_mcp_registry` and `services/notion_services.py`.
- `settings.cors_origins` — `localhost:{frontend_port}` only; update for prod.

SSU LMS regenerates data around 03:00 daily, so the default `SYNC_HOUR=4` exists for a reason — don't lower it. Frontend's `lmsAuth.js` mirrors `SESSION_REFRESH_INTERVAL=5400` and `SESSION_MAX_AGE=7d` from the backend; keep them in sync if you change one.

## Notable gotchas

- **CanvasClient Bearer-to-Canvas footgun** — covered above. Most "401 Invalid access token" bugs trace here.
- **`backend/app/services/vault_service.py:7`** uses `Path("_manifest.json")` which is relative to the uvicorn CWD. Move to a settings-based absolute path if you start using it.
- **`OBSIDIAN_VAULT_PATH` is a vault-relative path**, usually empty or a sub-folder name (e.g., `LMS`). The `.env.example` shows an absolute path; that's misleading and leads to `/vault//path/...` 404s. See `backend/app/mcp_client/README.md` §6 for the full set of MCP caveats.
- **Run uvicorn from `backend/`**, not the repo root — imports like `from app.config import settings` assume `backend/` is on `sys.path`.
- **N+1 in `list_courses`** — each course triggers two extra Canvas calls (`_get_professor`, `_get_progress`). If you add a route that only needs IDs, use `list_course_ids` instead.
