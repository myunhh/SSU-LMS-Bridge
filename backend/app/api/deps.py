# backend/app/api/deps.py
# 공통 의존성 주입
# ──────────────────────────────────────────────────────────────────────────────
# - get_canvas_client : 요청마다 CanvasClient 를 init() → yield → close().
#       세션 파일이 없으면(=로그인 전) 503 으로 변환해 프론트가 "재로그인 필요" 처리 가능.
# - get_mcp_registry  : Notion / Obsidian MCP 클라이언트를 prefix 로 묶은 registry.
# - get_chat_service  : LLM(litellm) + MCP tool-use 채팅 서비스.
# ──────────────────────────────────────────────────────────────────────────────
from functools import lru_cache
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status

from app.adapter.canvas_client import CanvasClient
from app.config import Settings, get_settings, settings
from app.mcp_client.base import MCPClientBase
from app.mcp_client.registry import McpRegistry
from app.services.llm import ChatService


# ── Canvas / LMS ──────────────────────────────────────────────
async def get_canvas_client() -> AsyncGenerator[CanvasClient, None]:
    client = CanvasClient(session_file=str(settings.session_cache_abspath))
    try:
        await client.init()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LMS 세션이 없습니다. 먼저 로그인하세요.",
        ) from e
    try:
        yield client
    finally:
        await client.close()


# ── MCP / Chat ────────────────────────────────────────────────
@lru_cache
def _build_registry(
    notion_url: str,
    notion_token: str,
    obsidian_url: str,
    obsidian_auth: str,
) -> McpRegistry:
    """순수 입력 → registry. lru_cache 로 프로세스당 1개만 만들기 위한 분리."""
    registry = McpRegistry()
    if notion_token:
        registry.register(
            "notion",
            MCPClientBase(
                server_url=notion_url,
                headers={"Authorization": f"Bearer {notion_token}"},
            ),
        )
    if obsidian_auth:
        registry.register(
            "obsidian",
            MCPClientBase(
                server_url=obsidian_url,
                headers={"Authorization": f"Bearer {obsidian_auth}"},
            ),
        )
    return registry


def get_mcp_registry(settings: Settings = Depends(get_settings)) -> McpRegistry:
    return _build_registry(
        notion_url=settings.notion_mcp_url,
        notion_token=settings.notion_token,
        obsidian_url=settings.obsidian_mcp_url,
        obsidian_auth=settings.obsidian_mcp_auth_code,
    )


def get_chat_service(
    settings: Settings = Depends(get_settings),
    registry: McpRegistry = Depends(get_mcp_registry),
) -> ChatService:
    return ChatService(settings, registry)
