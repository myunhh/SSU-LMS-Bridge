# backend/app/api/deps.py
# 공통 의존성 주입 — LMSAuth 싱글턴, CanvasClient 팩토리
"""공통 의존성 주입.

MCP / Chat 관련만 우선 정의. LMSAuth / CanvasClient 팩토리는 담당자 영역.
"""
from functools import lru_cache

from fastapi import Depends

from app.config import Settings, get_settings
from app.mcp_client.base import MCPClientBase
from app.mcp_client.registry import McpRegistry
from app.services.llm import ChatService


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
