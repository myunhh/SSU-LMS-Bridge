from contextlib import asynccontextmanager
from mcp import ClientSession
from mcp.client.sse import sse_client
from loguru import logger


class MCPClientBase:
    def __init__(self, server_url: str, headers: dict = None):
        self.server_url = server_url
        self.headers = headers or {}

    @asynccontextmanager
    async def session(self):
        async with sse_client(self.server_url, headers=self.headers) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                logger.info(f"[MCP] 연결: {self.server_url}")
                yield s

    async def list_resources(self) -> list:
        async with self.session() as s:
            result = await s.list_resources()
            return result.resources

    async def list_tools(self) -> list:
        async with self.session() as s:
            result = await s.list_tools()
            return result.tools

    async def read_resource(self, uri: str) -> str:
        async with self.session() as s:
            result = await s.read_resource(uri)
            return result.contents[0].text

    async def call_tool(self, name: str, arguments: dict) -> str:
        async with self.session() as s:
            result = await s.call_tool(name, arguments)
            return result.content[0].text
