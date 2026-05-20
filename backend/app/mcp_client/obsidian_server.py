import httpx
from mcp.server import Server
from mcp.types import Resource, Tool, TextContent

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
                description="Obsidian Vault에 파일 저장",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "relative_path": {"type": "string"},
                        "content":       {"type": "string"},
                        "mime_type":     {"type": "string"},
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
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        async with httpx.AsyncClient() as client:
            if name == "write_file":
                full_path = f"{vault_path}/{arguments['relative_path']}"
                resp = await client.put(
                    f"{BASE}/vault/{full_path}",
                    headers={
                        **auth_headers,
                        "Content-Type": arguments.get("mime_type", "application/octet-stream"),
                    },
                    content=arguments["content"].encode()
                    if isinstance(arguments["content"], str)
                    else arguments["content"],
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

    return server
