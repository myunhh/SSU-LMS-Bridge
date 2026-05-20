from notion_client import AsyncClient
from mcp.server import Server
from mcp.types import Tool, TextContent

def create_notion_mcp_server(token: str, root_page_id: str) -> Server:
    server = Server("notion-mcp")
    client = AsyncClient(auth=token)
    _db_cache: dict[str, str] = {}

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="ensure_db",
                description="Notion DB 생성 또는 ID 반환",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title":      {"type": "string"},
                        "properties": {"type": "object"},
                    },
                    "required": ["title", "properties"],
                },
            ),
            Tool(
                name="upsert_notice",
                description="공지사항 upsert",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "db_id": {"type": "string"}, "title": {"type": "string"},
                        "course_name": {"type": "string"}, "date": {"type": "string"},
                        "pinned": {"type": "boolean"}, "unread": {"type": "boolean"},
                    },
                    "required": ["db_id", "title", "course_name", "date"],
                },
            ),
            Tool(
                name="upsert_assignment",
                description="과제 upsert",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "db_id": {"type": "string"}, "title": {"type": "string"},
                        "course_name": {"type": "string"}, "due": {"type": "string"},
                        "type": {"type": "string"}, "weight": {"type": "number"},
                        "submitted": {"type": "boolean"},
                    },
                    "required": ["db_id", "title", "course_name", "due"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if name == "ensure_db":
            title = arguments["title"]
            if title in _db_cache:
                return [TextContent(type="text", text=_db_cache[title])]
            children = await client.blocks.children.list(root_page_id)
            for block in children["results"]:
                if block["type"] == "child_database" and block["child_database"]["title"] == title:
                    _db_cache[title] = block["id"]
                    return [TextContent(type="text", text=block["id"])]
            db = await client.databases.create(
                parent={"page_id": root_page_id},
                title=[{"text": {"content": title}}],
                properties=arguments["properties"],
            )
            _db_cache[title] = db["id"]
            return [TextContent(type="text", text=db["id"])]

        elif name == "upsert_notice":
            db_id = arguments["db_id"]
            result = await client.databases.query(
                database_id=db_id,
                filter={"property": "제목", "title": {"equals": arguments["title"]}},
            )
            props = {
                "과목": {"select": {"name": arguments["course_name"]}},
                "날짜": {"date": {"start": arguments["date"][:10]}},
                "중요": {"checkbox": arguments.get("pinned", False)},
                "읽음": {"checkbox": not arguments.get("unread", True)},
            }
            if result["results"]:
                await client.pages.update(result["results"][0]["id"], properties=props)
                return [TextContent(type="text", text="updated")]
            await client.pages.create(
                parent={"database_id": db_id},
                properties={"제목": {"title": [{"text": {"content": arguments["title"]}}]}, **props},
            )
            return [TextContent(type="text", text="created")]

        elif name == "upsert_assignment":
            db_id = arguments["db_id"]
            result = await client.databases.query(
                database_id=db_id,
                filter={"property": "제목", "title": {"equals": arguments["title"]}},
            )
            props = {
                "과목":     {"select": {"name": arguments["course_name"]}},
                "마감일":   {"date": {"start": arguments["due"][:10]}},
                "유형":     {"select": {"name": arguments.get("type", "기타")}},
                "비중(%)":  {"number": arguments.get("weight", 0) / 100},
                "제출완료": {"checkbox": arguments.get("submitted", False)},
            }
            if result["results"]:
                await client.pages.update(result["results"][0]["id"], properties=props)
                return [TextContent(type="text", text="updated")]
            await client.pages.create(
                parent={"database_id": db_id},
                properties={"제목": {"title": [{"text": {"content": arguments["title"]}}]}, **props},
            )
            return [TextContent(type="text", text="created")]

    return server
