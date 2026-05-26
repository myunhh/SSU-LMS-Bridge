"""McpRegistry 단위 테스트 — prefix 기반 dispatch / list_tools 통합.

외부 의존성(SSE 연결, MCP 서버) 없이 MCPClientBase 의 list_tools / call_tool 만
AsyncMock 으로 가짜로 두고 검증한다.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.mcp_client.base import MCPClientBase
from app.mcp_client.registry import McpRegistry


def _mock_client(tools: list[dict]) -> MCPClientBase:
    """list_tools / call_tool 만 mocking 된 가짜 MCPClientBase."""
    client = MCPClientBase(server_url="http://mock", headers={})
    client.list_tools = AsyncMock(return_value=[
        SimpleNamespace(
            name=t["name"],
            description=t.get("description", ""),
            inputSchema=t.get("inputSchema", {"type": "object", "properties": {}}),
        )
        for t in tools
    ])
    client.call_tool = AsyncMock(return_value="ok")
    return client


def test_prefix_with_separator_raises():
    """prefix 에 SEP('__') 가 들어가면 register 거부."""
    reg = McpRegistry()
    with pytest.raises(ValueError):
        reg.register("bad__prefix", _mock_client([]))


def test_register_collects_prefixes():
    reg = McpRegistry()
    reg.register("notion", _mock_client([]))
    reg.register("obsidian", _mock_client([]))
    assert set(reg.prefixes) == {"notion", "obsidian"}


async def test_list_tools_openai_prefixes_tool_names():
    """모든 MCP 의 tool 을 OpenAI 함수 스펙으로 평탄화하고 prefix__name 부여."""
    reg = McpRegistry()
    reg.register("notion", _mock_client([
        {"name": "query_notices", "description": "공지 조회",
         "inputSchema": {"type": "object", "properties": {"db_id": {"type": "string"}}}},
    ]))
    reg.register("obsidian", _mock_client([
        {"name": "write_file", "description": "파일 쓰기"},
    ]))

    tools = await reg.list_tools_openai()
    names = {t["function"]["name"] for t in tools}
    assert names == {"notion__query_notices", "obsidian__write_file"}

    # OpenAI/litellm function-calling 스펙 형식 검증
    for t in tools:
        assert t["type"] == "function"
        assert "parameters" in t["function"]
        assert "description" in t["function"]


async def test_list_tools_skips_failing_client():
    """한 클라이언트가 list_tools 실패해도 나머지는 정상 반환되어야 함."""
    good = _mock_client([{"name": "ok"}])
    bad = MCPClientBase(server_url="http://bad", headers={})
    bad.list_tools = AsyncMock(side_effect=RuntimeError("connection refused"))

    reg = McpRegistry()
    reg.register("good", good)
    reg.register("bad", bad)

    tools = await reg.list_tools_openai()
    names = [t["function"]["name"] for t in tools]
    assert names == ["good__ok"]


async def test_call_dispatches_to_correct_client():
    """prefixed_name 의 prefix 로 올바른 client 에 dispatch."""
    notion = _mock_client([])
    obsidian = _mock_client([])
    notion.call_tool = AsyncMock(return_value="from_notion")
    obsidian.call_tool = AsyncMock(return_value="from_obsidian")

    reg = McpRegistry()
    reg.register("notion", notion)
    reg.register("obsidian", obsidian)

    result = await reg.call("notion__query", {"x": 1})

    assert result == "from_notion"
    notion.call_tool.assert_awaited_once_with("query", {"x": 1})
    obsidian.call_tool.assert_not_awaited()


async def test_call_rejects_missing_prefix():
    reg = McpRegistry()
    with pytest.raises(ValueError, match="prefix 누락"):
        await reg.call("no_separator_here", {})


async def test_call_rejects_unknown_prefix():
    reg = McpRegistry()
    reg.register("notion", _mock_client([]))
    with pytest.raises(ValueError, match="등록되지 않은"):
        await reg.call("unknown__tool", {})
