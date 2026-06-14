# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

숭실대학교 LMS Bridge — a capstone web app that bridges SSU's Smart Campus LMS (`lms.ssu.ac.kr`, Canvas-based) into a FastAPI backend + React frontend with an LLM chat layer that can read/write Notion and Obsidian via MCP.

Comments, log messages, user-facing strings, and the README are all in Korean. Match that style when editing.

## Common commands

Backend:

```bash
# venv lives at the PROJECT ROOT (one shared .venv), not backend/
python3 -m venv .venv && source .venv/bin/activate    # Python 3.11+
(cd backend && pip install -e ".[dev]")
playwright install chromium                       # one-time, for SSO login

# everything below runs from backend/ so `app.*` imports resolve
cd backend
uvicorn app.main:app --reload --port 8000
pytest                                            # asyncio_mode = auto; tests are offline (network pings monkeypatched)
pytest tests/test_connectors_status.py::test_lms_connected_with_fresh_session   # single test
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

Adapters (`adapter/courses.py`, `assignments.py`, `notices.py`, `materials.py`) are pure async functions that take a `CanvasClient`, try one host and fall back to the other on failure (courses/assignments: LearningX→Canvas; notices: Canvas→LearningX), and return Pydantic models from `models.py`. Error policy: because the two hosts' auth is independent, a 401 from one still triggers the fallback — but once both fail, session-expired 401s must **propagate** to the global handler, not be swallowed. Use `notices.py:is_session_unauthorized(exc)` in any per-course `try/except` loop to re-raise those (tests enforce this). `notices.py:html_to_text` is the shared HTML→plain-text helper that fills `Notice.message_text` / `Assignment.description_text` (8000-char cap — a team contract with the frontend's `fullText`).

`list_courses` does an N+1 fan-out: exactly two extra calls per course (`_get_professor` + `_get_progress_and_materials` — the modules call computes progress *and* `Course.materials` together; don't split it back into two calls). Use `list_course_ids` when you only need IDs (e.g., the `/assignments/todos` and combined-notices routes).

**Session lifecycle is Playwright-driven.** `adapter/auth.py:SSULMSAuthPlaywright.login()` launches headless Chromium against `smartid.ssu.ac.kr` SSO, stores cookies + storage_state into `.cache/session_state.json` (path from `settings.session_cache_abspath`). `load_session()` revalidates *and* extends — it's invoked by `POST /api/lms/session/refresh`, the start of every `/api/sync`, **and** the periodic `session_refresh` APScheduler job (`main.py` schedules it via `IntervalTrigger(seconds=SESSION_REFRESH_INTERVAL)`, calling `routes/lms.py:run_scheduled_session_refresh`, which skips when no session file exists and yields to an in-progress sync to avoid concurrent Playwright writes to the session file). That periodic job is what `GET /api/lms/session`'s `nextRefreshIn` counts down to. ⚠️ Error contract: `login()`/`load_session()` return `False` **only** for credential mismatch / invalid-or-expired session (incl. corrupt session file); infrastructure errors (Chromium missing, network down, SSO markup change → TimeoutError) propagate as exceptions, which the routes convert to 502 (`/api/lms/login`, `/api/lms/session/refresh`) or 503 (`/api/sync`). Don't re-wrap them in a blanket `except: return False` — that misreports server problems as "wrong password" (regression tests: `tests/test_lms_routes.py`).

**Sync is one function, two entry points.** `routes/sync.py:perform_sync()` is shared by the manual `POST /api/sync` route and `run_scheduled_sync()` (APScheduler). Steps: verify+extend session → CanvasClient → collect → optionally push to Notion DB via MCP (only if `notion_token` and `notion_root_page_id` are real, not placeholder `xxxx`). Errors are appended to `SyncResult.errors`, not raised — except `SyncSessionError` which becomes HTTP 401/503/409. Module-level `_state` dict tracks `running`/`last_sync_at` (resets on process restart); `perform_sync` raises `SyncSessionError(409)` on entry if a sync is already `running` (concurrent-run guard — manual + scheduled syncs can't overlap; `tests/test_sync_guard.py`). The Notion push runs over a **single** MCP SSE session (`notion_services.py:sync_notion` wraps everything in one `mcp.session()`, calling `MCPClientBase.call_tool_in`); per-item upsert failures are counted into `pushed["failed"]` and surfaced as a `notion: N건 upsert 실패` entry in `errors`, while `ensure_db` failures propagate (the whole push is pointless without the DBs).

**Email notifications are SMTP-only.** `services/notify_service.py` sends digest emails for **upcoming deadlines** (assignments whose `due_at` is `now ~ now+NOTIFY_DEADLINE_HOURS`, unsubmitted) and **new notices** (posted since the last scan). The compute side is pure functions — `upcoming_deadlines` / `new_notices` / `render_digest`, accepting either payload dicts *or* `Assignment`/`Notice` models — so tests stay offline (`tests/test_notify_service.py` monkeypatches `smtplib.SMTP`). `send_email` follows the Notion/Obsidian `is_configured` guard: if SMTP is unset/placeholder it's a no-op that returns `False`, and it never raises (notifications must not break sync/scheduler). `smtp_configured()` needs `SMTP_HOST + NOTIFY_FROM + NOTIFY_TO` (user/password optional — only then does it `login`). `main.py` registers an APScheduler `IntervalTrigger` job (`notify_scan`, every `NOTIFY_SCAN_INTERVAL_MINUTES`) **only when `smtp_configured()`** — mirror the session_refresh pattern; the job's `scan_and_notify` lazily imports the adapters, skips silently if the session is missing/expired, and tracks `_state["last_scan_at"]` for the new-notice diff. `perform_sync` also fires a best-effort deadline email (step 5, reusing already-collected data, no extra calls; new-notice diff is left to the scan job). ⚠️ Real push (FCM/web-push) and desktop notifications are out of scope — they need a frontend service worker — so the settings page's `푸시`/`데스크탑` chips stay disabled; only `이메일` is wired.

**Routes are thin.** `api/routes/*.py` just call adapters and dump models; the work is in adapters. `api/deps.py:get_canvas_client` is a yield-style dependency that init/closes the client per request and converts `FileNotFoundError` (no session file) → 503.

**`GET /api/connectors/status` has a strict contract** (routes/connectors.py, "팀 공유 컨트랙트 B" — the frontend connector widget depends on it): always return all 4 items (`lms/notion/obsidian/llm`) with HTTP 200; any per-item exception is demoted to `disconnected`, never propagated; empty or placeholder (`xxxx`) settings short-circuit to `disconnected` **without network calls**. The network pings (`_ping_notion`, `_ping_obsidian`) are module-level functions specifically so tests can monkeypatch them — keep them that way.

### MCP (in-process)

LMS + Study + Notion + Obsidian MCP servers run as Starlette sub-apps mounted at `/mcp/lms`, `/mcp/study`, `/mcp/notion`, `/mcp/obsidian` **in the same FastAPI process** (`mcp_client/setup.py`). The chat service then opens SSE clients back to those URLs (`MCPClientBase` in `mcp_client/base.py`), so `Settings.notion_mcp_url` is just `http://localhost:{backend_port}/mcp/notion/sse`. No external Node process or stdio child to manage.

The **LMS MCP** (`mcp_client/lms_server.py`, `lms__*`) exposes the LMS adapters as 6 read-only tools (`list_courses/list_assignments/list_deadlines/list_notices/list_materials/list_discussions`) so chat can query courses/assignments/notices/materials in **real time** (Notion is a once-a-day snapshot, so deadlines/new notices are fresher here). Unlike Notion/Obsidian it has **no token → it always mounts** (no `is_configured` guard) and `deps.py:_build_registry` registers `lms` unconditionally too — the mount and registration conditions must stay paired. Session lifecycle is per-tool-call: each handler makes a fresh `CanvasClient(session_file=...)`, `init()`s, runs the adapter, then `close()`s (the `get_canvas_client` DI pattern ported into an `asynccontextmanager`). The `_run` wrapper guards **only** `FileNotFoundError` (login-not-yet → returns the Korean `NO_SESSION_MSG` text instead of dying); a 401 (session expired) **propagates** so `base.py:call_tool_in` turns it into a `RuntimeError` and the LLM tells the user to re-login — mirroring the adapters' `is_session_unauthorized` policy. For offline testing the dispatch logic lives in a module-level `_dispatch(name, arguments, session_file)` (+ pure `_dump`), so `tests/test_lms_mcp.py` calls it directly without touching SSE/Server internals.

The **Study MCP** (`mcp_client/study_server.py`, `study__*`) is the **2nd token-less always-mount MCP** (same contract as LMS): `setup.py` mounts it unconditionally and `deps.py:_build_registry` registers `study` unconditionally — the mount and registration must stay paired (the `study_url` param threads through `_build_registry` next to `lms_url`). It exposes 8 tools (`save_quiz/list_quizzes/get_quiz/delete_quiz/save_deck/list_decks/review_due/grade_card`) that store LLM-authored quizzes + flashcards in two local JSON files (`.cache/study/quizzes.json`·`decks.json`, path via the test-monkeypatchable `_store_dir()` — same trick as `connectors._env_path`). No session/token/`_client_cm`; the dispatch is a module-level `async _dispatch(name, arguments)` (+ pure `_dump`) for offline tests. **Role split is a contract:** quiz/card *generation* is the chat LLM's job (read `lms__*` content → `study__save_quiz/save_deck`), so the MCP never re-invokes the LLM and never imports `litellm`. Flashcards carry a lightweight **SM-2 SRS** state computed by the pure `_apply_review(card, correct, now)` — `now` is injected (deterministic due/interval/ease) by `save_deck/list_decks/review_due/grade_card`; correct→`interval` 1→3→`round(interval*ease)` with `ease+=0.1`, wrong→reset `reps=0`/`interval=1`/`ease=max(1.3, ease-0.2)`. `save_deck` upsert preserves existing SRS state for unchanged `front+back` cards (no review-progress loss).

⚠️ `mcp_client/sse_app.py` builds the sub-app. Pass only the relative `"/messages/"` to `SseServerTransport` — the MCP SDK auto-prefixes the ASGI mount root_path when it emits SSE endpoint events. Adding the prefix here too yields paths like `/mcp/notion/mcp/notion/messages/`.

The Obsidian MCP server (`mcp_client/obsidian_server.py`) wraps Obsidian's Local REST API. Its base URL comes from `settings.obsidian_base_url` (shared with the connectors-status ping); its `_vault_url()` helper filters empty path segments to avoid `/vault//...` 404s — build vault URLs through it, not by f-string concatenation.

`McpRegistry` (`mcp_client/registry.py`) flattens all mounted MCPs into one OpenAI-spec tool list using `prefix__name` (e.g., `notion__query_assignments`, `lms__list_deadlines`, `study__review_due`) and dispatches calls back to the right client by splitting on `__`. Prefixes must not contain `__`.

`services/llm.py:ChatService.stream()` is a multi-turn `tools` loop (max 8 iterations) over `litellm.acompletion(stream=True)`. Provider prefix is added to the model name for non-OpenAI providers (default: `gemini/gemini-2.5-flash`). It yields events typed as `text | tool_call | tool_result | error | done`; both the WebSocket route and the POST fallback consume the same generator.

The system prompt in `services/llm.py:SYSTEM_PROMPT` instructs the LLM to call `notion__ensure_db` first to resolve Notion DB IDs, then query. Notion DB property names are Korean and must match `services/notion_services.py:NOTICE_DB_PROPS` / `ASSIGNMENT_DB_PROPS` exactly (`제목/과목/날짜/마감일/유형/배점/제출완료/중요/읽음`). Changing one side requires changing the other — the same label appears in `mcp_client/notion_server.py` (upsert/query), `routes/sync.py`'s payload, and `mcp_client/README.md`. ⚠️ `배점` is a plain `number` holding `points_possible` verbatim (e.g. 100점), **not** a percentage — the old `비중(%)` property stored `points_possible/100` and distorted 배점 100점 into 100% (#8). The `유형` select stores app-aligned Korean labels (`과제(보고서)/에세이/퀴즈/토론`, fallback `기타`) mapped from raw Canvas `submission_types` by the single-source `models.py:submission_type_label` / `SUBMISSION_TYPE_LABELS`, applied in `routes/sync.py`'s payload — keep it consistent with the frontend `api/index.js:SUBMISSION_TYPE_MAP` (#12).

### Frontend (React 18 + Vite, no TS)

- **No build-step Tailwind.** Tailwind comes from the CDN script in `index.html` along with Pretendard/Inter — pages can use Tailwind classes directly. CSS variables (`--accent`, `--bg`, etc.) defined inline in `index.html` and overridden at runtime by `AppLayout` in `App.jsx`.
- **`DataStore.jsx` is the single source of truth.** Pages call `useData()`; never `fetch` directly from page components. Initial load runs `Api.fetchInitialBundle()`, which uses `Promise.allSettled` and returns `{courses, assignments, notices, errors}` — failed items are `null`, never thrown. `applyBundle` applies results: a successful **empty array replaces state** (so seeds don't linger), only `null` keeps the previous state. If `errors` look auth-related (`_isAuthError`), DataStore attempts one automatic re-login with the saved LMS credentials, then refetches.
- **Read/submitted state is a localStorage overlay, not backend state.** The app can't write to Canvas, so notice-read and assignment-submitted toggles persist in `localStorage` key `ssu_overrides:{studentId}` and are merged over every fetch/refetch (`_overlayNotices` / `_overlayAssignments` in DataStore.jsx). Compare ids with `String(id) === String(id)` — seed ids are strings (`'n1'`), real ids are numbers.
- **Connector widget state** merges `GET /api/connectors/status` over the seed list by `id`; `fetchConnectorsStatus` returns `null` on any failure (never throws) and the seed is kept, so the app works with the backend down.
- **`api/index.js` adapts backend schemas to frontend field names.** Backend Pydantic models use snake_case + canonical Canvas shapes (e.g., `Course.name` is literally `"고급프로그래밍 (2150164103)"`). The `adaptCourse / adaptNotice / adaptAssignment` functions split the name/code, convert `progress` from 0-100 to 0-1, invert `is_read` → `unread`, map `message_text`/`description_text` → `fullText` (plain text shown when a notice/assignment is expanded), map Canvas `submission_types` to display types via `SUBMISSION_TYPE_MAP`, and derive a per-course color from the ID. Add new backend fields here, not in the page components. ⚠️ `weight` is `points_possible` (배점, e.g. 100점), *not* a grade percentage — display copy is "배점 N점".
- **`USE_MOCK` toggles** in `api/index.js` and `api/lmsAuth.js` switch each module between real fetch and `mockData.js` seeds — useful for UI work without a running backend. Currently both `false`.
- **Auth is client-side only for now.** `auth/AccountStore.js` stores accounts in `localStorage` with SHA-256 + salt password hashes; there's no backend `/api/auth/*` yet. The LMS credentials entered at signup live next to it (currently plaintext — flagged in code comments).
- **LMS session calls** go through `api/lmsAuth.js` (`POST /api/lms/login`, etc.). Frontend never sees cookies / storage_state — only `userInfo` + `savedAt` metadata.
- **Chat is WebSocket-streamed.** `api/chat.js:openChatStream` sends `{messages}` once on open and dispatches typed events to callbacks; both sides assume the schema in `services/llm.py`.

### Environment / config

`backend/app/config.py` reads **the project-root `.env`** (`parents[2]` from config.py) — *not* `backend/.env`. `frontend/.env` is separate. Pydantic-settings ignores unknown keys. Derived properties to know:

- `settings.session_cache_abspath` — resolves relative `SESSION_CACHE_PATH` against project root. Always use this, not raw `SESSION_CACHE_PATH`.
- `settings.lms_mcp_url` / `study_mcp_url` / `notion_mcp_url` / `obsidian_mcp_url` — built from `backend_port`. Used by `deps.get_mcp_registry` (and `notion_services.py` for Notion). `lms_mcp_url` and `study_mcp_url` always have a client registered since the LMS and Study MCPs always mount. (Study storage reuses the existing `root_dir` property — `root_dir/.cache/study` — so no new settings key was added.)
- `settings.obsidian_base_url` — Obsidian Local REST API address (`OBSIDIAN_BASE_URL`), used by both the MCP server and the connectors-status ping. The plugin defaults are 27124=HTTPS (self-signed) / 27123=HTTP; the setting's default (`http://localhost:27124`) inherits an old hardcoding and may mismatch scheme↔port — set it explicitly in `.env`.
- `settings.cors_origins` — `localhost:{frontend_port}` only; update for prod.

Values containing `xxxx` are treated as placeholders (= not configured) — the single predicate is `config.py:is_configured`, shared by `routes/sync.py`, `routes/connectors.py`, `mcp_client/setup.py` (mount skip), and `api/deps.py:_build_registry` (registry skip; conditions must stay identical to setup.py so no MCP client is registered against an unmounted URL). `.env.example` samples like `secret_xxxx` deliberately match this rule. Don't re-implement the check locally.

SSU LMS regenerates data around 03:00 daily, so the default `SYNC_HOUR=4` exists for a reason — don't lower it. Frontend's `lmsAuth.js` mirrors `SESSION_REFRESH_INTERVAL=5400` and `SESSION_MAX_AGE=7d` from the backend's single source `backend/app/api/session_meta.py` (imported by `routes/lms.py` and `routes/connectors.py` — don't redeclare them per-route); keep frontend and backend in sync if you change one.

## Notable gotchas

- **CanvasClient Bearer-to-Canvas footgun** — covered above. Most "401 Invalid access token" bugs trace here. `tests/test_adapters_content.py` has a regression test for `_headers_for`.
- **`OBSIDIAN_VAULT_PATH` is a vault-relative path**, usually empty (vault root) or a sub-folder name (e.g., `LMS`) — never an absolute filesystem path. See `backend/app/mcp_client/README.md` §6 for the full set of MCP caveats.
- **Run uvicorn and pytest from `backend/`**, not the repo root — imports like `from app.config import settings` assume `backend/` is on `sys.path`.
- **N+1 in `list_courses`** — each course triggers exactly two extra Canvas calls (`_get_professor`, `_get_progress_and_materials`); a test asserts the count doesn't grow. If you add a route that only needs IDs, use `list_course_ids` instead.
- **`services/vault_service.py:sync_obsidian` pushes notices/assignments as Markdown** to `공지/{과목}/{제목}.md` / `과제/{과목}/{제목}.md`. `routes/sync.py:perform_sync` calls it (step 5) only when `is_configured(obsidian_mcp_auth_code)` — the same gate as `setup_mcp`'s mount. A sha256 manifest (`.cache/vault_manifest.json`) skips unchanged notes. SSU lecture files sit behind an LTI viewer, so file downloads are still out of scope — `sync_obsidian` only writes notice/assignment notes.
- **Tests must stay offline.** `test_connectors_status.py` monkeypatches the module-level ping functions and isolates `settings` per test; follow that pattern instead of hitting real Notion/Obsidian/LMS endpoints.
