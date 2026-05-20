"""여러 MCP 클라이언트를 prefix 로 묶어 LLM 의 단일 tool 목록으로 노출.

LLM 의 function-calling 규격(OpenAI 호환, litellm 이 그대로 받음)에는
하나의 tools 배열에 모든 도구 이름이 평탄하게 들어가야 한다.
이 모듈은 Notion / Obsidian MCP 의 tool 이름이 충돌하지 않도록
"prefix__name" 형태로 노출하고, 역방향 dispatch(이름 → 해당 MCP) 도 처리한다.
"""
from typing import Any

from loguru import logger

from app.mcp_client.base import MCPClientBase


class McpRegistry:
    SEP = "__"

    def __init__(self) -> None:
        self._clients: dict[str, MCPClientBase] = {}

    def register(self, prefix: str, client: MCPClientBase) -> None:
        if self.SEP in prefix:
            raise ValueError(f"prefix 에는 '{self.SEP}' 를 쓸 수 없음: {prefix}")
        self._clients[prefix] = client
        logger.info(f"[MCP] registry 등록: {prefix} → {client.server_url}")

    @property
    def prefixes(self) -> list[str]:
        return list(self._clients.keys())

    async def list_tools_openai(self) -> list[dict[str, Any]]:
        """모든 MCP 의 tool 을 OpenAI/litellm function-calling 스펙으로 평탄화.

        각 tool 의 name 은 'prefix__tool' 로 변환. inputSchema 는 그대로 parameters 에 매핑.
        """
        result: list[dict[str, Any]] = []
        for prefix, client in self._clients.items():
            try:
                tools = await client.list_tools()
            except Exception as e:
                logger.warning(f"[MCP] {prefix} list_tools 실패: {e}")
                continue
            for t in tools:
                result.append({
                    "type": "function",
                    "function": {
                        "name": f"{prefix}{self.SEP}{t.name}",
                        "description": t.description or "",
                        "parameters": t.inputSchema or {"type": "object", "properties": {}},
                    },
                })
        return result

    async def call(self, prefixed_name: str, arguments: dict[str, Any]) -> str:
        """LLM 이 호출한 prefixed tool 을 해당 MCP 로 dispatch."""
        if self.SEP not in prefixed_name:
            raise ValueError(f"prefix 누락된 tool 이름: {prefixed_name}")
        prefix, name = prefixed_name.split(self.SEP, 1)
        client = self._clients.get(prefix)
        if client is None:
            raise ValueError(f"등록되지 않은 MCP prefix: {prefix}")
        return await client.call_tool(name, arguments)
