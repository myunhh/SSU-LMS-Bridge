"""mcp_client/{notion,obsidian}_server.py 의 헬퍼 함수 단위 테스트.

내부 함수지만 query_notices / query_assignments / write_file 같은 tool 의
정확성이 이 헬퍼들에 의해 결정되므로 핵심 회귀 보호 지점.
"""
from mcp.types import ListResourcesRequest, ListToolsRequest, ReadResourceRequest

from app.mcp_client.notion_server import (
    _checkbox,
    _date,
    _date_prop,
    _find_child_database,
    _number,
    _page_matches_course,
    _safe_select,
    _select,
    _title,
    _title_filter,
)
from app.mcp_client.obsidian_server import _is_text_mime

# ── Notion property 추출 ─────────────────────────────────────

def test_title_concatenates_plain_text_pieces():
    prop = {"type": "title", "title": [
        {"plain_text": "안녕 "},
        {"plain_text": "세상"},
    ]}
    assert _title(prop) == "안녕 세상"


def test_title_returns_empty_for_none_or_wrong_type():
    assert _title(None) == ""
    assert _title({"type": "rich_text"}) == ""
    assert _title({"type": "title", "title": []}) == ""


def test_select_returns_name():
    assert _select({"type": "select", "select": {"name": "운영체제"}}) == "운영체제"


def test_select_handles_null_value():
    """Notion 에서 미설정 select 는 {"select": None}."""
    assert _select({"type": "select", "select": None}) == ""
    assert _select(None) == ""
    assert _select({"type": "date"}) == ""


def test_date_returns_start_only_not_end():
    prop = {"type": "date", "date": {"start": "2026-05-21", "end": "2026-05-25"}}
    assert _date(prop) == "2026-05-21"


def test_date_handles_null():
    assert _date({"type": "date", "date": None}) == ""
    assert _date(None) == ""


def test_checkbox_returns_bool():
    assert _checkbox({"type": "checkbox", "checkbox": True}) is True
    assert _checkbox({"type": "checkbox", "checkbox": False}) is False


def test_checkbox_default_when_missing():
    assert _checkbox(None) is False
    assert _checkbox(None, default=True) is True
    assert _checkbox({"type": "title"}, default=True) is True


def test_number_returns_value_or_none():
    assert _number({"type": "number", "number": 30}) == 30
    assert _number({"type": "number", "number": 0}) == 0
    assert _number({"type": "number", "number": None}) is None
    assert _number(None) is None
    assert _number({"type": "select"}) is None


# ── 중복 판정 (제목 query + 과목 코드 비교) ──────────────────
# ⚠️ query 에는 제목만 넣는다 — 과목(select) equals 필터는 해당 옵션이 DB 에
#    아직 없으면 Notion 이 'option not found' 로 query 를 거부하기 때문.

def test_title_filter_uses_title_only():
    """query 필터는 제목 단독 — select 옵션 부재로 인한 Notion 거부 회피."""
    assert _title_filter("휴강 안내") == {"property": "제목", "title": {"equals": "휴강 안내"}}


def _page_with_course(course: str) -> dict:
    return {"properties": {"과목": {"type": "select", "select": {"name": course}}}}


def test_page_matches_course_requires_same_course():
    """과목이 지정되면 page 의 과목까지 같아야 중복 — '휴강 안내'가 여러 과목에
    있어도 다른 과목 페이지를 덮어쓰지 않게 한다."""
    assert _page_matches_course(_page_with_course("운영체제"), "운영체제") is True
    assert _page_matches_course(_page_with_course("자료구조"), "운영체제") is False


def test_page_matches_course_empty_course_matches_any():
    """course_name 이 비면 제목 단독 일치로 본다."""
    assert _page_matches_course(_page_with_course("운영체제"), "") is True


# ── _date_prop (빈 마감일/날짜 → 날짜 미설정) ────────────────

def test_date_prop_valid_iso_uses_first_10_chars():
    assert _date_prop("2026-05-09T23:59:00") == {"date": {"start": "2026-05-09"}}


def test_date_prop_empty_or_none_unsets_date():
    """빈 값을 {date:{start:''}} 로 보내면 Notion 이 거부하므로 {date:None} 로."""
    assert _date_prop("") == {"date": None}
    assert _date_prop(None) == {"date": None}


# ── _safe_select (Notion select 옵션의 쉼표 금지 회피) ───────

def test_safe_select_replaces_commas():
    """쉼표 든 과목명은 Notion select 가 거부하므로 공백으로 치환한다."""
    assert _safe_select("CTE for IT, Engineering&Natura") == "CTE for IT  Engineering&Natura"
    assert _safe_select("자료구조") == "자료구조"
    assert _safe_select("") == ""


# ── _find_child_database 페이지네이션 (ensure_db 중복 DB 생성 방지) ──

def _child_db_block(block_id: str, title: str) -> dict:
    return {"type": "child_database", "id": block_id, "child_database": {"title": title}}


class _FakeBlocksChildren:
    """blocks.children.list 를 미리 준비한 페이지 목록으로 흉내내는 fake."""

    def __init__(self, pages: list[dict]):
        self._pages = pages
        self.calls: list[dict] = []

    async def list(self, block_id, start_cursor=None, page_size=None):
        self.calls.append(
            {"block_id": block_id, "start_cursor": start_cursor, "page_size": page_size}
        )
        return self._pages[len(self.calls) - 1]


class _FakeNotionClient:
    def __init__(self, pages: list[dict]):
        self.children = _FakeBlocksChildren(pages)
        self.blocks = type("Blocks", (), {"children": self.children})()


async def test_find_child_database_follows_pagination_to_second_page():
    """100블록 초과 루트 페이지: 2페이지에 있는 기존 DB 를 찾아야 중복 생성을 막는다."""
    client = _FakeNotionClient([
        {
            "results": [{"type": "paragraph", "id": "p1"}],
            "has_more": True,
            "next_cursor": "cursor-2",
        },
        {
            "results": [_child_db_block("db-과제", "과제")],
            "has_more": False,
            "next_cursor": None,
        },
    ])
    assert await _find_child_database(client, "root-page", "과제") == "db-과제"
    # 2번째 호출에 next_cursor 가 start_cursor 로 전달돼야 한다
    assert len(client.children.calls) == 2
    assert client.children.calls[0]["start_cursor"] is None
    assert client.children.calls[1]["start_cursor"] == "cursor-2"
    assert all(c["block_id"] == "root-page" for c in client.children.calls)


async def test_find_child_database_returns_none_when_absent():
    """어느 페이지에도 없으면 None — 무한 루프 없이 has_more=False 에서 종료."""
    client = _FakeNotionClient([
        {
            "results": [_child_db_block("db-공지", "공지사항")],
            "has_more": True,
            "next_cursor": "cursor-2",
        },
        {"results": [{"type": "paragraph", "id": "p1"}], "has_more": False, "next_cursor": None},
    ])
    assert await _find_child_database(client, "root-page", "과제") is None
    assert len(client.children.calls) == 2


async def test_find_child_database_stops_when_next_cursor_missing():
    """방어: has_more=True 인데 next_cursor 가 없으면(None/누락) 루프를 멈추고 None."""
    client = _FakeNotionClient([
        {"results": [], "has_more": True, "next_cursor": None},
    ])
    assert await _find_child_database(client, "root-page", "과제") is None
    assert len(client.children.calls) == 1


async def test_find_child_database_first_page_hit_makes_single_call():
    """1페이지에서 찾으면 추가 호출 없이 즉시 반환."""
    client = _FakeNotionClient([
        {
            "results": [_child_db_block("db-공지", "공지사항")],
            "has_more": True,
            "next_cursor": "cursor-2",
        },
    ])
    assert await _find_child_database(client, "root-page", "공지사항") == "db-공지"
    assert len(client.children.calls) == 1


# ── Obsidian mime 추론 (write_file binary 처리의 핵심) ───────

def test_is_text_mime_for_text_prefix():
    assert _is_text_mime("text/markdown") is True
    assert _is_text_mime("text/plain") is True
    assert _is_text_mime("text/html") is True


def test_is_text_mime_for_structured_text_formats():
    assert _is_text_mime("application/json") is True
    assert _is_text_mime("application/xml") is True
    assert _is_text_mime("application/yaml") is True


def test_is_text_mime_for_binary_returns_false():
    """이 케이스가 False 여야 vault_service.py 의 base64 인코딩 흐름이 정상 디코드된다."""
    assert _is_text_mime("application/octet-stream") is False
    assert _is_text_mime("application/pdf") is False
    assert _is_text_mime("image/png") is False
    assert _is_text_mime("image/jpeg") is False


# ── MCP resource 채널 제거 회귀 보호 (#15 데드코드 정리) ──────
#
# 채팅은 tool 만 사용하고 resource 경로(list_resources/read_resource)는
# 클라이언트·서버 양쪽 모두 미사용이라 삭제했다. tool 경로만 남았는지 고정한다.

def test_mcp_client_base_has_no_resource_methods():
    """base.py 의 데드 resource 메서드 삭제 고정 — tool 경로만 남는다."""
    from app.mcp_client.base import MCPClientBase

    assert not hasattr(MCPClientBase, "list_resources")
    assert not hasattr(MCPClientBase, "read_resource")
    assert hasattr(MCPClientBase, "list_tools")
    assert hasattr(MCPClientBase, "call_tool")


def test_obsidian_server_registers_no_resource_handlers():
    """obsidian MCP 서버는 tool 핸들러만 등록 — resource 핸들러는 제거됨."""
    from app.mcp_client.obsidian_server import create_obsidian_mcp_server

    server = create_obsidian_mcp_server("dummy-auth", "")
    # tool 경로는 살아있고, resource 경로는 핸들러가 등록되지 않았다.
    assert server.request_handlers.get(ListToolsRequest) is not None
    assert server.request_handlers.get(ListResourcesRequest) is None
    assert server.request_handlers.get(ReadResourceRequest) is None
