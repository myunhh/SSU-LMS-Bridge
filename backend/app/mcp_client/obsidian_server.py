import base64
from urllib.parse import urlparse

import httpx
from mcp.server import Server
from mcp.types import TextContent, Tool

_TEXT_MIME_PREFIXES = ("text/", "application/json", "application/xml", "application/yaml")
# 루프백 주소는 Local REST API 플러그인의 자가서명 인증서를 쓰므로 TLS 검증을 끈다
# (connectors._obsidian_tls_verify 와 동일 규칙 — 비로컬 주소는 검증을 강제).
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _is_text_mime(mime: str) -> bool:
    return any(mime.startswith(p) for p in _TEXT_MIME_PREFIXES)

def create_obsidian_mcp_server(
    auth_code: str,
    vault_path: str,
    base_url: str = "http://localhost:27124",
) -> Server:
    """Obsidian Local REST API 를 감싸는 MCP 서버 생성.

    base_url: Local REST API 주소 (settings.obsidian_base_url).
        기본값을 둔 이유 — setup.py 의 기존 2-인자 호출과의 호환.
        플러그인 기본값은 27124=HTTPS(자가서명) / 27123=HTTP 이므로 환경에 맞게 조정.
    vault_path: vault 내부 상대 경로 (보통 빈 문자열이 정상).
    """
    server = Server("obsidian-mcp")
    auth_headers = {"Authorization": f"Bearer {auth_code}"}
    base = base_url.rstrip("/")
    # 자가서명 HTTPS(루프백) 는 검증을 끄지 않으면 CERTIFICATE_VERIFY_FAILED 로 막힌다.
    _verify_tls = urlparse(base_url).hostname not in _LOCAL_HOSTS

    def _vault_url(*segments: str, is_dir: bool = False) -> str:
        """빈 segment 를 걸러 이중 슬래시(/vault//…)를 방지한 vault URL 조립.

        디렉터리 목록 조회는 Local REST API 규약상 끝에 '/' 가 필요하다 (is_dir=True).
        """
        parts = [s.strip("/") for s in segments if s and s.strip("/")]
        url = "/".join([base, "vault", *parts])
        return f"{url}/" if is_dir else url

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
        async with httpx.AsyncClient(verify=_verify_tls) as client:
            if name == "write_file":
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
                    _vault_url(vault_path, arguments["relative_path"]),
                    headers={**auth_headers, "Content-Type": mime},
                    content=body,
                    timeout=30,
                )
                ok = resp.status_code in (200, 201, 204)
                return [TextContent(type="text", text="saved" if ok else "failed")]

            elif name == "list_files":
                resp = await client.get(
                    _vault_url(vault_path, is_dir=True),
                    headers=auth_headers, timeout=10,
                )
                resp.raise_for_status()
                files = resp.json().get("files", [])
                return [TextContent(type="text", text="\n".join(files))]

            elif name == "file_count":
                resp = await client.get(
                    _vault_url(vault_path, is_dir=True),
                    headers=auth_headers, timeout=10,
                )
                resp.raise_for_status()
                count = len(resp.json().get("files", []))
                return [TextContent(type="text", text=str(count))]

            elif name == "search_files":
                resp = await client.post(
                    f"{base}/search/simple/",
                    headers=auth_headers,
                    params={
                        "query": arguments["query"],
                        "contextLength": arguments.get("context_length", 100),
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                return [TextContent(type="text", text=resp.text)]

            # 알 수 없는 tool 이름 — None 반환 시 MCPClientBase.call_tool 의
            # result.content[0] 접근에서 IndexError 로 이어지므로 명시적으로 거부한다.
            raise ValueError(f"unknown tool: {name}")

    return server
