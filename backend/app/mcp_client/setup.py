"""FastAPI 앱에 Notion / Obsidian MCP 서버를 SSE 로 마운트.

설계
----
- 같은 백엔드 프로세스 안에 MCP 서버를 띄우고, 그 SSE 엔드포인트에
  같은 프로세스의 클라이언트(`mcp_client.base.MCPClientBase`)가 붙는다.
- 외부에서 별도 노드 프로세스를 띄우거나 stdio 자식 프로세스를 관리할
  필요가 없어 의존성이 단순하다.
- 클라이언트가 붙을 URL 은 `Settings.notion_mcp_url` / `obsidian_mcp_url`
  프로퍼티가 백엔드 포트로부터 조립해서 제공한다.
  → `services/notion_services.py` · `services/vault_service.py` 가 이 URL 로
     SSE 연결을 연다.

마운트 경로
-----------
- `/mcp/notion/sse`        ← SSE 핸드셰이크
- `/mcp/notion/messages/`  ← 클라이언트 → 서버 JSON-RPC
- `/mcp/obsidian/sse`
- `/mcp/obsidian/messages/`

토큰 / 인증코드가 비어 있거나 placeholder('xxxx', .env.example 견본값)인 MCP 는
마운트를 건너뛴다 — routes/sync.py · routes/connectors.py 와 같은
`config.is_configured` 규칙 (커넥터 위젯은 disconnected 인데 LLM 채팅에는
notion__* tool 이 노출되는 불일치 방지).
"""
from fastapi import FastAPI
from loguru import logger

from app.config import Settings, is_configured
from app.mcp_client.grades_server import create_grades_mcp_server
from app.mcp_client.lms_server import create_lms_mcp_server
from app.mcp_client.materials_server import create_materials_mcp_server
from app.mcp_client.notion_server import create_notion_mcp_server
from app.mcp_client.obsidian_server import create_obsidian_mcp_server
from app.mcp_client.sse_app import build_mcp_sse_app
from app.mcp_client.study_server import create_study_mcp_server


def setup_mcp(app: FastAPI, settings: Settings) -> None:
    """FastAPI 앱에 LMS / Notion / Obsidian MCP SSE 엔드포인트를 마운트한다."""

    # ── LMS ────────────────────────────────────────────────
    # LMS 는 토큰 설정이 없으므로 is_configured 가드 없이 항상 마운트한다.
    # 세션 미존재는 도구 호출 시점에 한국어 안내(NO_SESSION_MSG)로 처리하므로
    # 마운트는 안전하다. (deps.py:_build_registry 의 lms 등록도 동일하게 무조건 —
    # 마운트/등록 두 조건이 일치해야 미마운트 URL 에 클라이언트가 붙는 불일치를 막는다.)
    lms_server = create_lms_mcp_server(session_file=str(settings.session_cache_abspath))
    app.mount("/mcp/lms", build_mcp_sse_app(lms_server, "/mcp/lms"))
    logger.info(f"[MCP] LMS 마운트: {settings.lms_mcp_url}")

    # ── Study (학습 도우미) ─────────────────────────────────
    # LMS 와 동일하게 토큰 설정이 없으므로 is_configured 가드 없이 항상 마운트한다.
    # 저장소는 로컬 JSON 파일뿐이라 세션/외부 의존도 없다(study_server.py).
    # (deps.py:_build_registry 의 study 등록도 무조건 — 마운트/등록 두 조건이 짝이라야
    #  미마운트 URL 에 클라이언트가 붙는 불일치를 막는다. LMS 와 동일 규약.)
    study_server = create_study_mcp_server()
    app.mount("/mcp/study", build_mcp_sse_app(study_server, "/mcp/study"))
    logger.info(f"[MCP] Study 마운트: {settings.study_mcp_url}")

    # ── Grades (성적/GPA) ──────────────────────────────────
    # LMS 와 동일 — 토큰 없는 세션 기반 MCP 라 무조건 마운트(deps 등록도 무조건).
    grades_server = create_grades_mcp_server(session_file=str(settings.session_cache_abspath))
    app.mount("/mcp/grades", build_mcp_sse_app(grades_server, "/mcp/grades"))
    logger.info(f"[MCP] Grades 마운트: {settings.grades_mcp_url}")

    # ── Materials (강의자료 RAG) ───────────────────────────
    # Obsidian 에 받아둔 파일을 읽으므로 obsidian 설정 시에만 마운트(obsidian 과 동일 게이트,
    # deps 등록 조건도 동일해야 미마운트 URL 에 클라이언트가 붙는 불일치를 막는다).
    if is_configured(settings.obsidian_mcp_auth_code):
        materials_server = create_materials_mcp_server(
            auth_code=settings.obsidian_mcp_auth_code,
            base_url=settings.obsidian_base_url,
            vault_path=settings.obsidian_vault_path,
        )
        app.mount("/mcp/materials", build_mcp_sse_app(materials_server, "/mcp/materials"))
        logger.info(f"[MCP] Materials 마운트: {settings.materials_mcp_url}")
    else:
        logger.warning(
            "[MCP] OBSIDIAN_MCP_AUTH_CODE 미설정 → 강의자료 RAG(Materials) MCP 건너뜀"
        )

    # ── Notion ─────────────────────────────────────────────
    if is_configured(settings.notion_token, settings.notion_root_page_id):
        notion_server = create_notion_mcp_server(
            token=settings.notion_token,
            root_page_id=settings.notion_root_page_id,
        )
        app.mount("/mcp/notion", build_mcp_sse_app(notion_server, "/mcp/notion"))
        logger.info(f"[MCP] Notion 마운트: {settings.notion_mcp_url}")
    else:
        logger.warning(
            "[MCP] NOTION_TOKEN / NOTION_ROOT_PAGE_ID 미설정(또는 placeholder) → Notion MCP 건너뜀"
        )

    # ── Obsidian ───────────────────────────────────────────
    # obsidian_vault_path 는 vault 내부 상대 경로 → 보통 빈 문자열("")이 정상이므로
    # 마운트 조건에서 제외하고, auth_code 만으로 활성화 여부를 판단한다.
    if is_configured(settings.obsidian_mcp_auth_code):
        obsidian_server = create_obsidian_mcp_server(
            auth_code=settings.obsidian_mcp_auth_code,
            vault_path=settings.obsidian_vault_path,
            # 상태 핑(routes/connectors.py)과 같은 URL 을 쓰도록 settings 로 일원화
            # — .env 의 OBSIDIAN_BASE_URL 변경이 MCP 도구 호출에도 반영된다.
            base_url=settings.obsidian_base_url,
        )
        app.mount("/mcp/obsidian", build_mcp_sse_app(obsidian_server, "/mcp/obsidian"))
        logger.info(f"[MCP] Obsidian 마운트: {settings.obsidian_mcp_url}")
    else:
        logger.warning(
            "[MCP] OBSIDIAN_MCP_AUTH_CODE 미설정(또는 placeholder) → Obsidian MCP 건너뜀"
        )
