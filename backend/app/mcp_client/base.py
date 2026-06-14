from contextlib import asynccontextmanager

from loguru import logger
from mcp import ClientSession
from mcp.client.sse import sse_client


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

    async def list_tools(self) -> list:
        async with self.session() as s:
            result = await s.list_tools()
            return result.tools

    @staticmethod
    async def call_tool_in(s: ClientSession, name: str, arguments: dict) -> str:
        """이미 열린 세션 위에서 tool 호출 + 결과 텍스트 추출.

        단발 호출(call_tool)과 단일 세션 다발 호출(services/notion_services.py 의
        sync_notion)이 공유하는 결과 추출 로직 — isError/빈 content 검사 등을
        보강할 때 이 한 곳만 고치면 양쪽 경로에 반영된다.

        MCP SDK 는 서버 핸들러에서 예외가 나도 raise 하지 않고
        CallToolResult(isError=True, content=[오류문자열]) 을 돌려주므로,
        여기서 RuntimeError 로 변환해야 호출부(llm.py 의 tool 루프,
        sync_notion 의 errors 수집)가 실패를 실패로 인지한다 — 안 그러면
        오류 메시지 텍스트가 db_id 같은 정상 결과로 둔갑한다.
        """
        result = await s.call_tool(name, arguments)
        if result.isError:
            text = result.content[0].text if result.content else "(내용 없음)"
            raise RuntimeError(f"MCP tool '{name}' 실패: {text}")
        return result.content[0].text if result.content else ""

    async def call_tool(self, name: str, arguments: dict) -> str:
        async with self.session() as s:
            return await self.call_tool_in(s, name, arguments)
