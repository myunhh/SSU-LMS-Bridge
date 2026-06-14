"""sync_notion — 단일 SSE 세션 + 항목별 실패 허용 회귀 테스트 (오프라인).

검증 항목
---------
- (a) push 전체가 단일 세션(SSE 연결 1회)으로 처리되는지
- (b) upsert 한 건이 예외를 던져도 나머지 항목이 모두 처리되고 failed 카운트가 반환되는지
- (c) ensure_db 예외는 그대로 전파되는지 (DB 확보 실패 = 전체 push 무의미)
- (+) 기존 call_tool 단발 경로가 call_tool_in 헬퍼로 위임되는지 (registry/채팅 경로 호환)

네트워크 금지 — MCPClientBase.session 을 asynccontextmanager 가짜로 패치한다
(test_mcp_registry.py 의 인스턴스/클래스 레벨 mock 패턴).
"""
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.mcp_client.base import MCPClientBase
from app.services.notion_services import sync_notion


def _tool_result(text: str):
    """ClientSession.call_tool 결과 모양 (isError + content[0].text)."""
    return SimpleNamespace(isError=False, content=[SimpleNamespace(text=text)])


class FakeSession:
    """가짜 ClientSession — 호출 기록 + 지정한 제목의 upsert 만 실패시킨다."""

    def __init__(self, fail_titles: set[str] | None = None, fail_ensure_db: bool = False):
        self.calls: list[tuple[str, dict]] = []
        self.fail_titles = fail_titles or set()
        self.fail_ensure_db = fail_ensure_db

    async def call_tool(self, name: str, arguments: dict):
        self.calls.append((name, arguments))
        if name == "ensure_db":
            if self.fail_ensure_db:
                raise RuntimeError("Notion API 인증 오류")
            return _tool_result(f"db-{arguments['title']}")
        if arguments.get("title") in self.fail_titles:
            raise RuntimeError("Notion API 일시 오류")
        return _tool_result("created")


@pytest.fixture()
def fake_mcp(monkeypatch):
    """MCPClientBase.session 을 가짜 세션으로 교체하고 (세션 객체, 연결 횟수 기록) 반환."""
    state = {"session": FakeSession(), "opened": 0}

    @asynccontextmanager
    async def _fake_session(self):
        state["opened"] += 1
        yield state["session"]

    monkeypatch.setattr(MCPClientBase, "session", _fake_session)
    return state


_NOTICES = [
    {"title": "공지1", "course_name": "고급프로그래밍", "date": "2026-06-01"},
    {"title": "공지2", "course_name": "고급프로그래밍", "date": "2026-06-02"},
    {"title": "공지3", "course_name": "자료구조", "date": "2026-06-03"},
]
_ASSIGNMENTS = [
    {"title": "과제1", "course_name": "고급프로그래밍", "due": "2026-06-10"},
    {"title": "과제2", "course_name": "자료구조", "due": "2026-06-11"},
]


async def test_sync_notion_opens_single_session(fake_mcp):
    """(a) ensure_db 2회 + upsert N+M 건을 모두 단일 SSE 세션으로 처리해야 한다."""
    result = await sync_notion(
        notices=_NOTICES,
        assignments=_ASSIGNMENTS,
        notion_mcp_url="http://mock/sse",
        notion_token="tok",
    )

    assert fake_mcp["opened"] == 1  # 항목마다 재연결 금지
    # 호출 수: ensure_db 2 + 공지 3 + 과제 2
    assert len(fake_mcp["session"].calls) == 7
    assert result == {"notices_added": 3, "assignments_added": 2, "failed": 0}


async def test_sync_notion_continues_after_single_upsert_failure(fake_mcp):
    """(b) 한 건 실패해도 나머지 항목은 모두 처리되고 failed 카운트가 반환된다."""
    fake_mcp["session"].fail_titles = {"공지2", "과제1"}

    result = await sync_notion(
        notices=_NOTICES,
        assignments=_ASSIGNMENTS,
        notion_mcp_url="http://mock/sse",
        notion_token="tok",
    )

    # 실패 건 이후의 항목도 빠짐없이 시도됐는지 (ensure_db 2 + 공지 3 + 과제 2)
    assert len(fake_mcp["session"].calls) == 7
    assert result == {"notices_added": 2, "assignments_added": 1, "failed": 2}


async def test_sync_notion_propagates_ensure_db_failure(fake_mcp):
    """(c) DB 확보 실패는 전체 push 가 무의미 → 예외 그대로 전파 (perform_sync 가 수거)."""
    fake_mcp["session"].fail_ensure_db = True

    with pytest.raises(RuntimeError, match="인증 오류"):
        await sync_notion(
            notices=_NOTICES,
            assignments=_ASSIGNMENTS,
            notion_mcp_url="http://mock/sse",
            notion_token="tok",
        )

    # ensure_db 에서 멈췄으므로 upsert 는 한 건도 시도되지 않아야 한다
    assert [name for name, _ in fake_mcp["session"].calls] == ["ensure_db"]


async def test_call_tool_delegates_to_call_tool_in(fake_mcp):
    """단발 call_tool 경로(registry/채팅)가 공유 헬퍼 call_tool_in 으로 위임되는지."""
    mcp = MCPClientBase(server_url="http://mock/sse")
    result = await mcp.call_tool("ensure_db", {"title": "공지사항"})
    assert result == "db-공지사항"
    assert fake_mcp["opened"] == 1


# ──────────────────────────────────────────────────────────────────────────────
# upsert_assignment 가 실제로 만드는 Notion property — 배점 왜곡 회귀 (#8)
# ──────────────────────────────────────────────────────────────────────────────
# notion_server.py 의 call_tool 핸들러를 가짜 notion-client AsyncClient 로 직접
# 구동해, weight(points_possible) 가 '배점' number 에 /100 없이 원값 그대로
# 저장되는지, 옛 '비중(%)' 라벨이 더는 안 쓰이는지 검증한다 (네트워크 없음).
from mcp.types import CallToolRequest, CallToolRequestParams  # noqa: E402

from app.mcp_client import notion_server as ns  # noqa: E402
from app.services.notion_services import ASSIGNMENT_DB_PROPS  # noqa: E402


class _FakeNotionClient:
    """notion_server 가 쓰는 client.request 를 가로채 pages 생성/수정 properties 를 캡처.

    notion_server 는 databases/pages 를 SDK 메서드가 아니라 client.request(REST 직접)
    로 호출한다(notion-client 버전 비의존). 그래서 가짜도 request 한 곳만 구현한다.
    """

    def __init__(self, existing: bool = False, course: str = ""):
        self.captured: dict = {}
        self._existing = existing
        self._course = course  # 기존 page 의 과목 (제목 query 후 코드 비교에 쓰임)

    async def request(self, path, method, body=None, **kw):
        body = body or {}
        if path == "databases" and method == "POST":          # _create_db
            return {"id": "db-new"}
        if path.endswith("/query") and method == "POST":      # _query_db
            # 제목으로만 조회되므로 과목은 page properties 로 돌려준다
            # (notion_server 의 _page_matches_course 가 코드에서 비교).
            page = {
                "id": "page-existing",
                "properties": {"과목": {"type": "select", "select": {"name": self._course}}},
            }
            return {"results": [page] if self._existing else []}
        if path == "pages" and method == "POST":              # _create_page
            self.captured["create"] = body["properties"]
            return {"id": "page-created"}
        if method == "PATCH":                                  # _update_page (pages/{id})
            self.captured["update"] = body["properties"]
            return {"id": path.split("/")[-1]}
        raise AssertionError(f"unexpected request: {method} {path}")


def _build_server_with(fake_client, monkeypatch):
    """create_notion_mcp_server 가 우리 가짜 클라이언트를 쓰도록 패치 후 서버/핸들러 반환."""
    monkeypatch.setattr(ns, "AsyncClient", lambda auth, notion_version=None: fake_client)
    server = ns.create_notion_mcp_server("tok", "root")
    return server.request_handlers[CallToolRequest]


def _upsert_req(**arguments):
    return CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name="upsert_assignment", arguments=arguments),
    )


async def test_upsert_assignment_stores_raw_points_as_배점_not_percent(monkeypatch):
    """(#8) weight=100(배점 100점)이 /100 왜곡 없이 '배점' number 에 그대로 저장된다."""
    fake = _FakeNotionClient(existing=False)
    handler = _build_server_with(fake, monkeypatch)

    await handler(_upsert_req(
        db_id="db1", title="보고서 과제", course_name="고급프로그래밍",
        due="2026-06-10T00:00:00Z", type="과제(보고서)", weight=100, submitted=False,
    ))

    props = fake.captured["create"]
    # 배점은 원값 그대로 (옛 버그: 100 / 100 = 1.0)
    assert props["배점"] == {"number": 100}
    # 옛 '비중(%)' 라벨은 더는 쓰이지 않는다
    assert "비중(%)" not in props
    # 유형 라벨은 전달된 한글 라벨 그대로
    assert props["유형"] == {"select": {"name": "과제(보고서)"}}


async def test_upsert_assignment_update_path_uses_배점(monkeypatch):
    """기존 페이지 update 경로도 '배점' number 를 원값으로 갱신한다 (#8)."""
    fake = _FakeNotionClient(existing=True, course="자료구조")
    handler = _build_server_with(fake, monkeypatch)

    await handler(_upsert_req(
        db_id="db1", title="에세이 과제", course_name="자료구조",
        due="2026-06-11T00:00:00Z", type="에세이", weight=30,
    ))

    props = fake.captured["update"]
    assert props["배점"] == {"number": 30}
    assert "비중(%)" not in props


def test_assignment_db_props_uses_배점_plain_number():
    """ASSIGNMENT_DB_PROPS 가 '배점' 일반 number(=percent 포맷 아님)로 정의돼 있어야 한다 (#8)."""
    assert "배점" in ASSIGNMENT_DB_PROPS
    assert "비중(%)" not in ASSIGNMENT_DB_PROPS
    # percent 포맷이 아니라 일반 number (format 키 없음)
    assert ASSIGNMENT_DB_PROPS["배점"] == {"number": {}}


# ──────────────────────────────────────────────────────────────────────────────
# #9 upsert_notice/upsert_assignment 공용 _upsert 골격 회귀
# ──────────────────────────────────────────────────────────────────────────────
# 두 핸들러가 동일한 query→중복판정→create/update 골격을 거치는지,
# create/update 반환과 query 필터(제목 단독)·과목 비교가 보존되는지 검증한다.
def _notice_req(**arguments):
    return CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name="upsert_notice", arguments=arguments),
    )


def _text(result) -> str:
    """call_tool 핸들러 결과(CallToolResult)에서 첫 TextContent 의 text 추출."""
    return result.root.content[0].text


async def test_upsert_notice_create_path_returns_created(monkeypatch):
    """신규 공지는 _create_page 로 들어가고 'created' 를 돌려준다 (#9)."""
    fake = _FakeNotionClient(existing=False)
    handler = _build_server_with(fake, monkeypatch)

    result = await handler(_notice_req(
        db_id="db1", title="휴강 안내", course_name="고급프로그래밍",
        date="2026-06-01", pinned=True, unread=True,
    ))

    assert _text(result) == "created"
    props = fake.captured["create"]
    # 골격이 조립한 공지 property 가 그대로 전달됐는지
    assert props["과목"] == {"select": {"name": "고급프로그래밍"}}
    assert props["중요"] == {"checkbox": True}
    assert props["읽음"] == {"checkbox": False}  # unread=True → 읽음 False
    # create 시에만 제목을 함께 넣는다
    assert props["제목"] == {"title": [{"text": {"content": "휴강 안내"}}]}


async def test_upsert_notice_update_path_returns_updated_without_title(monkeypatch):
    """과목까지 일치하는 기존 공지는 update 로 가고 'updated', props 에 제목은 없다 (#9)."""
    fake = _FakeNotionClient(existing=True, course="자료구조")
    handler = _build_server_with(fake, monkeypatch)

    result = await handler(_notice_req(
        db_id="db1", title="시험 공지", course_name="자료구조", date="2026-06-05",
    ))

    assert _text(result) == "updated"
    props = fake.captured["update"]
    # update 는 props 만 갱신 — 제목 일치로 찾았으므로 제목은 다시 안 보낸다
    assert "제목" not in props
    assert props["과목"] == {"select": {"name": "자료구조"}}


async def test_upsert_assignment_create_path_returns_created(monkeypatch):
    """신규 과제도 같은 골격을 거쳐 'created' 를 돌려준다 (#9, upsert_notice 와 대칭)."""
    fake = _FakeNotionClient(existing=False)
    handler = _build_server_with(fake, monkeypatch)

    result = await handler(_upsert_req(
        db_id="db1", title="보고서 과제", course_name="고급프로그래밍",
        due="2026-06-10T00:00:00Z", type="과제(보고서)", weight=100,
    ))

    assert _text(result) == "created"
    assert "제목" in fake.captured["create"]


async def test_upsert_course_mismatch_creates_new_page(monkeypatch):
    """제목은 같지만 과목이 다르면 중복이 아니라 새 page 를 만든다 (_page_matches_course 보존, #9)."""
    # query 는 '국어'(다른 과목) page 1건을 돌려주지만, 요청 과목은 '영어'.
    fake = _FakeNotionClient(existing=True, course="국어")
    handler = _build_server_with(fake, monkeypatch)

    result = await handler(_notice_req(
        db_id="db1", title="공통 공지", course_name="영어", date="2026-06-01",
    ))

    # 과목 불일치 → update 가 아니라 create
    assert _text(result) == "created"
    assert "create" in fake.captured
    assert "update" not in fake.captured
