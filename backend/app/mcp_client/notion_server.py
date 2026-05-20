import json
from datetime import datetime, timedelta

from notion_client import AsyncClient
from mcp.server import Server
from mcp.types import Tool, TextContent


# ── Notion property 추출 헬퍼 ────────────────────────────────
def _title(prop: dict | None) -> str:
    if not prop or prop.get("type") != "title":
        return ""
    return "".join(i.get("plain_text", "") for i in prop.get("title", []))


def _select(prop: dict | None) -> str:
    if not prop or prop.get("type") != "select":
        return ""
    sel = prop.get("select")
    return sel.get("name", "") if sel else ""


def _date(prop: dict | None) -> str:
    if not prop or prop.get("type") != "date":
        return ""
    d = prop.get("date")
    return d.get("start", "") if d else ""


def _checkbox(prop: dict | None, default: bool = False) -> bool:
    if not prop or prop.get("type") != "checkbox":
        return default
    return bool(prop.get("checkbox", default))


def _number(prop: dict | None) -> float | None:
    if not prop or prop.get("type") != "number":
        return None
    return prop.get("number")


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
            Tool(
                name="query_notices",
                description=(
                    "공지사항 DB 조회. 최신순. "
                    "only_unread=true 면 안 읽은 것만, course_name 지정 시 해당 과목만. "
                    "반환은 JSON 배열 문자열."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "db_id":       {"type": "string"},
                        "limit":       {"type": "integer", "default": 20},
                        "only_unread": {"type": "boolean", "default": False},
                        "course_name": {"type": "string"},
                    },
                    "required": ["db_id"],
                },
            ),
            Tool(
                name="query_assignments",
                description=(
                    "과제 DB 조회. 마감일 오름차순. "
                    "only_upcoming=true 면 오늘부터 days_ahead 일까지의 과제만, "
                    "only_unsubmitted=true 면 미제출만, course_name 지정 시 해당 과목만. "
                    "반환은 JSON 배열 문자열."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "db_id":            {"type": "string"},
                        "limit":            {"type": "integer", "default": 20},
                        "only_upcoming":    {"type": "boolean", "default": False},
                        "days_ahead":       {"type": "integer", "default": 7},
                        "only_unsubmitted": {"type": "boolean", "default": False},
                        "course_name":      {"type": "string"},
                    },
                    "required": ["db_id"],
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

        elif name == "query_notices":
            filters = []
            if arguments.get("only_unread"):
                filters.append({"property": "읽음", "checkbox": {"equals": False}})
            if arguments.get("course_name"):
                filters.append({"property": "과목", "select": {"equals": arguments["course_name"]}})

            query: dict = {
                "database_id": arguments["db_id"],
                "sorts": [{"property": "날짜", "direction": "descending"}],
                "page_size": min(arguments.get("limit", 20), 100),
            }
            if len(filters) == 1:
                query["filter"] = filters[0]
            elif filters:
                query["filter"] = {"and": filters}

            result = await client.databases.query(**query)
            notices = [
                {
                    "id":     page["id"],
                    "title":  _title(page["properties"].get("제목")),
                    "course": _select(page["properties"].get("과목")),
                    "date":   _date(page["properties"].get("날짜")),
                    "pinned": _checkbox(page["properties"].get("중요")),
                    "read":   _checkbox(page["properties"].get("읽음")),
                    "url":    page.get("url", ""),
                }
                for page in result["results"]
            ]
            return [TextContent(type="text", text=json.dumps(notices, ensure_ascii=False))]

        elif name == "query_assignments":
            filters = []
            if arguments.get("only_unsubmitted"):
                filters.append({"property": "제출완료", "checkbox": {"equals": False}})
            if arguments.get("course_name"):
                filters.append({"property": "과목", "select": {"equals": arguments["course_name"]}})
            if arguments.get("only_upcoming"):
                today = datetime.now().date().isoformat()
                end = (datetime.now() + timedelta(days=arguments.get("days_ahead", 7))).date().isoformat()
                filters.append({"property": "마감일", "date": {"on_or_after": today}})
                filters.append({"property": "마감일", "date": {"on_or_before": end}})

            query = {
                "database_id": arguments["db_id"],
                "sorts": [{"property": "마감일", "direction": "ascending"}],
                "page_size": min(arguments.get("limit", 20), 100),
            }
            if len(filters) == 1:
                query["filter"] = filters[0]
            elif filters:
                query["filter"] = {"and": filters}

            result = await client.databases.query(**query)
            assignments = [
                {
                    "id":        page["id"],
                    "title":     _title(page["properties"].get("제목")),
                    "course":    _select(page["properties"].get("과목")),
                    "due":       _date(page["properties"].get("마감일")),
                    "type":      _select(page["properties"].get("유형")),
                    "weight":    _number(page["properties"].get("비중(%)")),
                    "submitted": _checkbox(page["properties"].get("제출완료")),
                    "url":       page.get("url", ""),
                }
                for page in result["results"]
            ]
            return [TextContent(type="text", text=json.dumps(assignments, ensure_ascii=False))]

    return server
