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

토큰 / 인증코드가 비어 있는 MCP 는 마운트를 건너뛴다 (개발 편의).
"""
from fastapi import FastAPI
from loguru import logger

from app.config import Settings
from app.mcp_client.notion_server import create_notion_mcp_server
from app.mcp_client.obsidian_server import create_obsidian_mcp_server
from app.mcp_client.sse_app import build_mcp_sse_app


def setup_mcp(app: FastAPI, settings: Settings) -> None:
    """FastAPI 앱에 Notion / Obsidian MCP SSE 엔드포인트를 마운트한다."""

    # ── Notion ─────────────────────────────────────────────
    if settings.notion_token and settings.notion_root_page_id:
        notion_server = create_notion_mcp_server(
            token=settings.notion_token,
            root_page_id=settings.notion_root_page_id,
        )
        app.mount("/mcp/notion", build_mcp_sse_app(notion_server, "/mcp/notion"))
        logger.info(f"[MCP] Notion 마운트: {settings.notion_mcp_url}")
    else:
        logger.warning(
            "[MCP] NOTION_TOKEN / NOTION_ROOT_PAGE_ID 미설정 → Notion MCP 건너뜀"
        )

    # ── Obsidian ───────────────────────────────────────────
    # obsidian_vault_path 는 vault 내부 상대 경로 → 보통 빈 문자열("")이 정상이므로
    # 마운트 조건에서 제외하고, auth_code 만으로 활성화 여부를 판단한다.
    if settings.obsidian_mcp_auth_code:
        obsidian_server = create_obsidian_mcp_server(
            auth_code=settings.obsidian_mcp_auth_code,
            vault_path=settings.obsidian_vault_path,
        )
        app.mount("/mcp/obsidian", build_mcp_sse_app(obsidian_server, "/mcp/obsidian"))
        logger.info(f"[MCP] Obsidian 마운트: {settings.obsidian_mcp_url}")
    else:
        logger.warning(
            "[MCP] OBSIDIAN_MCP_AUTH_CODE 미설정 → Obsidian MCP 건너뜀"
        )
