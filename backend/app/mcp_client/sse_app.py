"""MCP 서버를 Starlette sub-app(SSE transport)으로 노출하는 헬퍼.

mcp_client/notion_server.py · obsidian_server.py 의 factory 가 만든
`mcp.server.Server` 인스턴스를 받아 FastAPI 에 mount 가능한 Starlette 앱으로 감싼다.
mcp_client/base.py 의 SSE 클라이언트(`MCPClientBase`)가 그대로 붙는다.
"""
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route


def build_mcp_sse_app(server: Server, mount_prefix: str = "") -> Starlette:
    """MCP Server 를 SSE transport 로 노출하는 Starlette 앱을 빌드.

    Args:
        server: mcp.server.Server 인스턴스 (factory 가 반환한 것).
        mount_prefix: (현재 미사용) 과거 호환용 인자.

    반환된 앱은 두 엔드포인트를 갖는다.
    - GET  {prefix}/sse           — SSE 핸드셰이크 (read/write 스트림 개통)
    - POST {prefix}/messages/...  — 클라이언트가 보내는 JSON-RPC 메시지

    ⚠️ SseServerTransport 에는 **앱 내부 상대경로("/messages/")** 만 넘긴다.
       mcp SDK(server/sse.py)가 SSE endpoint 이벤트를 보낼 때 ASGI root_path
       (= 마운트 prefix, 예 "/mcp/notion") 를 자동으로 앞에 붙이므로, 여기서
       prefix 를 또 붙이면 "/mcp/notion/mcp/notion/messages/" 처럼 중복된다.
    """
    transport = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> Response:
        async with transport.connect_sse(
            request.scope, request.receive, request._send
        ) as (read, write):
            await server.run(read, write, server.create_initialization_options())
        return Response()

    return Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            # Mount 내부 매칭은 prefix 가 제거된 경로 기준이므로 "/messages/"
            Mount("/messages/", app=transport.handle_post_message),
        ]
    )
