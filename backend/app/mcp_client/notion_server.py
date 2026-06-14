import json
from datetime import datetime, timedelta

from mcp.server import Server
from mcp.types import TextContent, Tool
from notion_client import AsyncClient


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


def _safe_select(name: str) -> str:
    """Notion select 옵션 이름으로 안전하게 정규화.

    ⚠️ Notion select 옵션은 쉼표(,)를 허용하지 않는다
    ('Invalid select option, commas not allowed'). 과목명에 쉼표가 든
    강의(예: 'CTE for IT, Engineering&Natura ...')는 쉼표를 공백으로 바꿔
    저장한다. 저장·중복비교·조회가 모두 이 함수를 거쳐 일관되게 한다.
    """
    return (name or "").replace(",", " ")


def _date_prop(value: str | None) -> dict:
    """ISO 날짜 문자열(앞 10자)을 Notion date property 로. 빈 값이면 날짜 미설정.

    ⚠️ 빈 문자열을 {"date": {"start": ""}} 로 보내면 Notion 이
    'start should be a valid ISO 8601 date string' 으로 거부한다(마감일·날짜
    없는 LMS 항목에서 발생). 빈 값은 {"date": None}(미설정)으로 보낸다.
    """
    v = (value or "")[:10]
    return {"date": {"start": v}} if v else {"date": None}


def _title_filter(title: str) -> dict:
    """upsert 중복 판정 1단계 — **제목으로만** 조회하는 Notion 필터.

    ⚠️ 과목(select) equals 필터를 query 에 넣으면 안 된다: 해당 과목 옵션이
    DB 에 아직 없을 때 Notion 이 'select option ... not found' 로 query 를
    거부한다(과목 옵션은 page 생성 시 자동 추가되므로 신규 과목의 첫 항목에서
    바로 그 일이 생긴다). 그래서 제목으로만 조회한 뒤 과목 일치는
    _page_matches_course 로 코드에서 비교한다.
    """
    return {"property": "제목", "title": {"equals": title}}


def _page_matches_course(page: dict, course_name: str) -> bool:
    """중복 판정 2단계 — 조회된 page 의 과목이 course_name 과 같은지 코드 비교.

    course_name 이 비면 제목 단독 일치로 본다. 비어 있지 않으면 과목까지
    같아야 중복으로 판정해 '휴강 안내'처럼 여러 과목에 같은 제목이 있을 때
    다른 과목 페이지를 덮어쓰지 않는다.
    """
    if not course_name:
        return True
    # 저장 시 _safe_select 로 쉼표를 치환하므로 비교 쪽도 동일하게 정규화한다.
    return _select(page["properties"].get("과목")) == _safe_select(course_name)


async def _find_child_database(client: AsyncClient, root_page_id: str, title: str) -> str | None:
    """루트 페이지 블록을 페이지네이션하며 같은 제목의 child_database 를 찾는다.

    Notion API 는 한 번에 최대 100개 블록만 반환하므로 has_more/next_cursor 를
    따라가야 한다 — 안 그러면 100블록 초과 페이지에서 기존 DB 를 못 찾고
    ensure_db 가 매번 새 DB 를 만든다. 못 찾으면 None.
    (notion-client 의 pick 헬퍼가 start_cursor=None 을 걸러주므로 첫 호출도 안전)
    """
    cursor = None
    while True:
        children = await client.blocks.children.list(
            root_page_id, start_cursor=cursor, page_size=100
        )
        for block in children["results"]:
            if block["type"] == "child_database" and block["child_database"]["title"] == title:
                return block["id"]
        if not children.get("has_more") or not children.get("next_cursor"):
            return None
        cursor = children["next_cursor"]


# Notion REST API 버전 고정.
# notion-client 2.7+/3.0 의 기본 버전은 2025-09-03(data_sources 모델)이라
# databases.query 가 SDK 에서 제거되고 databases.create body 형식도 바뀐다.
# 이 서버는 2.x(databases) 모델을 쓰므로 안정 버전으로 고정하고, SDK 의
# databases/pages 메서드 대신 client.request 로 REST 를 직접 호출해
# SDK 버전 차이에 영향받지 않게 한다 (blocks 는 버전 안정적이라 SDK 유지).
NOTION_API_VERSION = "2022-06-28"


def create_notion_mcp_server(token: str, root_page_id: str) -> Server:
    server = Server("notion-mcp")
    client = AsyncClient(auth=token, notion_version=NOTION_API_VERSION)
    # DB 이름→id 프로세스 메모리 캐시. 프로세스 재시작 시 초기화된다
    # (archive/삭제된 DB 를 가리키면 upsert 가 실패하므로 그때는 재시작 필요).
    _db_cache: dict[str, str] = {}

    # ── databases/pages REST 직접 호출 헬퍼 (SDK 모델 버전 비의존) ──
    async def _create_db(parent: dict, title: list, properties: dict) -> dict:
        return await client.request(
            path="databases", method="POST",
            body={"parent": parent, "title": title, "properties": properties},
        )

    async def _query_db(database_id: str, **body) -> dict:
        return await client.request(
            path=f"databases/{database_id}/query", method="POST", body=body,
        )

    async def _create_page(parent: dict, properties: dict) -> dict:
        return await client.request(
            path="pages", method="POST",
            body={"parent": parent, "properties": properties},
        )

    async def _update_page(page_id: str, properties: dict) -> dict:
        return await client.request(
            path=f"pages/{page_id}", method="PATCH", body={"properties": properties},
        )

    async def _upsert(db_id: str, title: str, course_name: str, props: dict) -> str:
        """upsert_notice/upsert_assignment 공용 골격 — 제목+과목으로 중복을 찾아
        있으면 update, 없으면 create 한다. 호출자는 항목별 props 만 조립해 넘긴다.

        중복 판정은 _title_filter(제목으로만 조회) → _page_matches_course(과목 코드
        비교) 2단계다 — 과목(select) equals 를 query 에 넣으면 신규 과목의 첫 항목에서
        'select option ... not found' 로 거부되기 때문(_title_filter 주석 참고).
        제목은 create 시에만 쓰고 update 는 props 만 갱신한다(제목 일치로 찾았으므로).
        반환은 'created'/'updated'.
        """
        result = await _query_db(db_id, filter=_title_filter(title))
        existing = next(
            (p["id"] for p in result["results"] if _page_matches_course(p, course_name)),
            None,
        )
        if existing:
            await _update_page(existing, props)
            return "updated"
        await _create_page(
            {"type": "database_id", "database_id": db_id},
            {"제목": {"title": [{"text": {"content": title}}]}, **props},
        )
        return "created"

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
            db_id = await _find_child_database(client, root_page_id, title)
            if db_id:
                _db_cache[title] = db_id
                return [TextContent(type="text", text=db_id)]
            db = await _create_db(
                # parent.type 명시 필수 — 없으면 Notion API 가
                # "body.parent.type should be defined" 검증 오류로 거부한다.
                {"type": "page_id", "page_id": root_page_id},
                [{"text": {"content": title}}],
                arguments["properties"],
            )
            _db_cache[title] = db["id"]
            return [TextContent(type="text", text=db["id"])]

        elif name == "upsert_notice":
            # course_name 은 inputSchema 상 required 지만 LLM 직접 호출 대비 .get 방어
            course_name = arguments.get("course_name", "")
            props = {
                "과목": {"select": {"name": _safe_select(course_name)}},
                "날짜": _date_prop(arguments.get("date")),
                "중요": {"checkbox": arguments.get("pinned", False)},
                "읽음": {"checkbox": not arguments.get("unread", True)},
            }
            status = await _upsert(arguments["db_id"], arguments["title"], course_name, props)
            return [TextContent(type="text", text=status)]

        elif name == "upsert_assignment":
            # course_name 은 inputSchema 상 required 지만 LLM 직접 호출 대비 .get 방어
            course_name = arguments.get("course_name", "")
            props = {
                "과목":     {"select": {"name": _safe_select(course_name)}},
                "마감일":   _date_prop(arguments.get("due")),
                "유형":     {"select": {"name": arguments.get("type", "기타")}},
                # ⚠️ weight 는 배점(points_possible, 예: 100점)이지 비중(%)이 아니다 (#8).
                # /100 하면 100점 → 100% 로 데이터가 왜곡되므로 원래 값을 그대로 저장.
                "배점":     {"number": arguments.get("weight", 0)},
                "제출완료": {"checkbox": arguments.get("submitted", False)},
            }
            status = await _upsert(arguments["db_id"], arguments["title"], course_name, props)
            return [TextContent(type="text", text=status)]

        elif name == "query_notices":
            filters = []
            if arguments.get("only_unread"):
                filters.append({"property": "읽음", "checkbox": {"equals": False}})
            if arguments.get("course_name"):
                filters.append({"property": "과목", "select": {"equals": _safe_select(arguments["course_name"])}})

            query: dict = {
                "database_id": arguments["db_id"],
                "sorts": [{"property": "날짜", "direction": "descending"}],
                "page_size": min(arguments.get("limit", 20), 100),
            }
            if len(filters) == 1:
                query["filter"] = filters[0]
            elif filters:
                query["filter"] = {"and": filters}

            result = await _query_db(**query)
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
                filters.append({"property": "과목", "select": {"equals": _safe_select(arguments["course_name"])}})
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

            result = await _query_db(**query)
            assignments = [
                {
                    "id":        page["id"],
                    "title":     _title(page["properties"].get("제목")),
                    "course":    _select(page["properties"].get("과목")),
                    "due":       _date(page["properties"].get("마감일")),
                    "type":      _select(page["properties"].get("유형")),
                    "weight":    _number(page["properties"].get("배점")),
                    "submitted": _checkbox(page["properties"].get("제출완료")),
                    "url":       page.get("url", ""),
                }
                for page in result["results"]
            ]
            return [TextContent(type="text", text=json.dumps(assignments, ensure_ascii=False))]

        # 알 수 없는 tool 이름 — None 반환 시 SDK 가 'Unexpected return type from
        # tool: NoneType' 라는 암호 같은 isError 결과를 만들므로 명시적으로 거부한다.
        # (obsidian_server.py 와 동일한 정책)
        raise ValueError(f"unknown tool: {name}")

    return server
