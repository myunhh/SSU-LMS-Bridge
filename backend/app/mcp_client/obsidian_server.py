import base64

import httpx
from mcp.server import Server
from mcp.types import Resource, Tool, TextContent


_TEXT_MIME_PREFIXES = ("text/", "application/json", "application/xml", "application/yaml")


def _is_text_mime(mime: str) -> bool:
    return any(mime.startswith(p) for p in _TEXT_MIME_PREFIXES)

def create_obsidian_mcp_server(auth_code: str, vault_path: str) -> Server:
    server = Server("obsidian-mcp")
    auth_headers = {"Authorization": f"Bearer {auth_code}"}
    BASE = "http://localhost:27124"

    @server.list_resources()
    async def list_resources():
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE}/vault/{vault_path}/",
                headers=auth_headers, timeout=10,
            )
            files = resp.json().get("files", [])
        return [
            Resource(
                uri=f"mcp://obsidian/{f}",
                name=f.split("/")[-1],
                description=f"Vault 파일: {f}",
                mimeType="application/octet-stream",
            )
            for f in files
        ]

    @server.read_resource()
    async def read_resource(uri: str):
        path = uri.replace("mcp://obsidian/", "")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE}/vault/{path}",
                headers=auth_headers, timeout=15,
            )
        return [TextContent(type="text", text=resp.text)]

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="write_file",
                description=(
                    "Obsidian Vault에 파일 저장. "
                    "binary 파일(PDF, 이미지 등)은 content 를 base64 로 인코딩해 보내고 "
                    "encoding='base64' 를 지정하거나 mime_type 을 비텍스트 타입으로 지정. "
                    "텍스트(md/json/txt 등)는 그대로 전달."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "relative_path": {"type": "string"},
                        "content":       {"type": "string"},
                        "mime_type":     {"type": "string"},
                        "encoding":      {
                            "type": "string",
                            "enum": ["utf-8", "base64"],
                            "description": "content 의 인코딩. 없으면 mime_type 으로 추론.",
                        },
                    },
                    "required": ["relative_path", "content"],
                },
            ),
            Tool(
                name="list_files",
                description="Vault 파일 목록",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="file_count",
                description="Vault 파일 수",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="search_files",
                description=(
                    "Vault에서 키워드 검색. Obsidian Local REST API 의 /search/simple/ 사용. "
                    "파일명·본문 모두 매칭. 반환은 JSON 문자열(매칭 파일 + 컨텍스트 스니펫)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query":          {"type": "string"},
                        "context_length": {"type": "integer", "default": 100},
                    },
                    "required": ["query"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        async with httpx.AsyncClient() as client:
            if name == "write_file":
                full_path = f"{vault_path}/{arguments['relative_path']}"
                mime = arguments.get("mime_type", "application/octet-stream")
                encoding = arguments.get("encoding")
                content = arguments["content"]

                # 인코딩 결정: 명시값 우선, 없으면 mime_type 으로 추론.
                # 비텍스트(application/octet-stream, application/pdf 등)는 base64 로 가정.
                is_b64 = (
                    encoding == "base64"
                    or (encoding is None and not _is_text_mime(mime))
                )
                if is_b64 and isinstance(content, str):
                    body = base64.b64decode(content)
                elif isinstance(content, str):
                    body = content.encode("utf-8")
                else:
                    body = content

                resp = await client.put(
                    f"{BASE}/vault/{full_path}",
                    headers={**auth_headers, "Content-Type": mime},
                    content=body,
                    timeout=30,
                )
                ok = resp.status_code in (200, 201, 204)
                return [TextContent(type="text", text="saved" if ok else "failed")]

            elif name == "list_files":
                resp = await client.get(
                    f"{BASE}/vault/{vault_path}/",
                    headers=auth_headers, timeout=10,
                )
                files = resp.json().get("files", [])
                return [TextContent(type="text", text="\n".join(files))]

            elif name == "file_count":
                resp = await client.get(
                    f"{BASE}/vault/{vault_path}/",
                    headers=auth_headers, timeout=10,
                )
                count = len(resp.json().get("files", []))
                return [TextContent(type="text", text=str(count))]

            elif name == "search_files":
                resp = await client.post(
                    f"{BASE}/search/simple/",
                    headers=auth_headers,
                    params={
                        "query": arguments["query"],
                        "contextLength": arguments.get("context_length", 100),
                    },
                    timeout=15,
                )
                return [TextContent(type="text", text=resp.text)]

    return server
