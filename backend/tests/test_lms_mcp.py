"""LMS MCP 서버 오프라인 회귀 테스트 (네트워크 0).

핵심 보호 지점:
- 도구 목록 노출(6개, prefix 'lms', 이름에 '__' 없음, course_id 필수/선택 스키마)
- 세션 파일 없음(FileNotFoundError) → 한국어 안내 TextContent (예외로 죽지 않음)
- adapter monkeypatch 로 도구 호출 성공 경로 + 한글 JSON 직렬화
- course_id 문자열 → int 캐스팅
- list_notices 의 course_id 유무 분기
- 401(세션 만료)은 가드하지 않고 전파 (FileNotFoundError 만 가드)
- unknown tool → ValueError
- deps._build_registry 가 토큰 없이도 'lms' prefix 를 무조건 등록(setup 마운트 조건과 일치)

실제 디스패치 로직은 모듈 레벨 `_dispatch` 로 분리돼 있어 SSE/Server 내부 구조에
의존하지 않고 직접 호출해 검증한다.
"""
from unittest.mock import AsyncMock

import httpx
import pytest

from app.mcp_client import lms_server
from app.mcp_client.lms_server import NO_SESSION_MSG, _dispatch, _dump, create_lms_mcp_server
from app.models import Assignment, Course, Material, Notice

SF = "/tmp/does-not-matter.json"


# ── _dump 순수 함수 ───────────────────────────────────────────

def test_dump_single_model_korean_json():
    out = _dump(Course(id=1, name="고급프로그래밍 (2150164103)"))
    assert "고급프로그래밍" in out          # ensure_ascii=False 로 한글 유지
    assert "\\uace0" not in out             # 이스케이프되지 않았는지
    assert '"id": 1' in out


def test_dump_list_of_models():
    out = _dump([Course(id=1, name="A"), Course(id=2, name="B")])
    assert out.startswith("[") and out.endswith("]")


def test_dump_empty_list():
    assert _dump([]) == "[]"


# ── 도구 목록 노출 ─────────────────────────────────────────────

async def _list_tools(server):
    """SDK 가 등록한 list_tools 핸들러를 꺼내 호출."""
    import mcp.types as types
    handler = server.request_handlers[types.ListToolsRequest]
    result = await handler(types.ListToolsRequest(method="tools/list"))
    return result.root.tools


async def test_list_tools_exposes_six_readonly_tools():
    server = create_lms_mcp_server(session_file=SF)
    tools = await _list_tools(server)
    names = {t.name for t in tools}
    assert names == {
        "list_courses",
        "list_assignments",
        "list_deadlines",
        "list_notices",
        "list_materials",
        "list_discussions",
    }
    # prefix 는 registry 가 붙이므로 tool 이름 자체엔 '__' 가 없어야 함
    assert all("__" not in n for n in names)


async def test_tool_input_schemas_course_id_required_or_optional():
    server = create_lms_mcp_server(session_file=SF)
    tools = {t.name: t for t in await _list_tools(server)}

    # 인자 없는 도구
    assert tools["list_courses"].inputSchema.get("required", []) == []
    assert tools["list_deadlines"].inputSchema.get("required", []) == []

    # course_id 필수 도구
    for name in ("list_assignments", "list_materials", "list_discussions"):
        assert tools[name].inputSchema["required"] == ["course_id"]

    # list_notices 는 course_id optional (required 없음, 그러나 property 는 존재)
    assert "required" not in tools["list_notices"].inputSchema
    assert "course_id" in tools["list_notices"].inputSchema["properties"]


# ── 세션 없음 경로 (FileNotFoundError → 한국어 안내) ───────────

async def test_no_session_returns_korean_guidance(monkeypatch):
    """세션 파일 없으면 CanvasClient.init 이 FileNotFoundError → NO_SESSION_MSG 반환."""
    async def _raise(self):
        raise FileNotFoundError("세션 파일 없음")

    monkeypatch.setattr(lms_server.CanvasClient, "init", _raise)
    # adapter 는 호출되면 안 되지만(init 단계에서 실패), 안전하게 mock
    monkeypatch.setattr(
        lms_server.courses, "list_courses", AsyncMock(side_effect=AssertionError)
    )

    result = await _dispatch("list_courses", {}, SF)
    assert len(result) == 1
    assert result[0].text == NO_SESSION_MSG


# ── 성공 경로 (adapter monkeypatch) ───────────────────────────

@pytest.fixture
def _noop_client(monkeypatch):
    """CanvasClient.init/close 를 no-op 으로 두어 세션 파일 없이도 동작."""
    monkeypatch.setattr(lms_server.CanvasClient, "init", AsyncMock())
    monkeypatch.setattr(lms_server.CanvasClient, "close", AsyncMock())


async def test_list_courses_success(monkeypatch, _noop_client):
    monkeypatch.setattr(
        lms_server.courses,
        "list_courses",
        AsyncMock(return_value=[Course(id=1, name="고급프로그래밍 (2150164103)")]),
    )
    result = await _dispatch("list_courses", {}, SF)
    assert "고급프로그래밍" in result[0].text


async def test_list_assignments_casts_course_id_to_int(monkeypatch, _noop_client):
    """LLM 이 course_id 를 문자열로 줘도 int 로 캐스팅해 adapter 호출."""
    mock = AsyncMock(return_value=[
        Assignment(id=10, course_id=123, title="과제1"),
    ])
    monkeypatch.setattr(lms_server.assignments, "list_assignments", mock)

    result = await _dispatch("list_assignments", {"course_id": "123"}, SF)
    assert "과제1" in result[0].text
    # 두 번째 인자(course_id)가 int 123 으로 전달됐는지
    _, args, _kw = mock.mock_calls[0]
    assert args[1] == 123 and isinstance(args[1], int)


async def test_list_deadlines_uses_course_ids_then_all_deadlines(monkeypatch, _noop_client):
    """N+1 회피: list_course_ids 로 ID 만 모아 list_all_deadlines 호출."""
    ids_mock = AsyncMock(return_value=[1, 2])
    deadlines_mock = AsyncMock(return_value=[Assignment(id=1, course_id=1, title="마감")])
    monkeypatch.setattr(lms_server.courses, "list_course_ids", ids_mock)
    monkeypatch.setattr(lms_server.assignments, "list_all_deadlines", deadlines_mock)
    # list_courses(N+1) 는 절대 호출되면 안 됨
    monkeypatch.setattr(
        lms_server.courses, "list_courses", AsyncMock(side_effect=AssertionError)
    )

    result = await _dispatch("list_deadlines", {}, SF)
    assert "마감" in result[0].text
    ids_mock.assert_awaited_once()
    _, args, _kw = deadlines_mock.mock_calls[0]
    assert args[1] == [1, 2]


async def test_list_notices_with_course_id_calls_single_course(monkeypatch, _noop_client):
    single = AsyncMock(return_value=[Notice(id=1, course_id=5, title="과목공지")])
    all_mock = AsyncMock(side_effect=AssertionError)
    monkeypatch.setattr(lms_server.notices, "list_notices", single)
    monkeypatch.setattr(lms_server.notices, "list_all_notices", all_mock)

    result = await _dispatch("list_notices", {"course_id": "5"}, SF)
    assert "과목공지" in result[0].text
    _, args, _kw = single.mock_calls[0]
    assert args[1] == 5 and isinstance(args[1], int)


async def test_list_notices_without_course_id_calls_all(monkeypatch, _noop_client):
    ids_mock = AsyncMock(return_value=[7, 8])
    all_mock = AsyncMock(return_value=[Notice(id=2, course_id=7, title="통합공지")])
    single = AsyncMock(side_effect=AssertionError)
    monkeypatch.setattr(lms_server.courses, "list_course_ids", ids_mock)
    monkeypatch.setattr(lms_server.notices, "list_all_notices", all_mock)
    monkeypatch.setattr(lms_server.notices, "list_notices", single)

    result = await _dispatch("list_notices", {}, SF)
    assert "통합공지" in result[0].text
    ids_mock.assert_awaited_once()
    _, args, _kw = all_mock.mock_calls[0]
    assert args[1] == [7, 8]


async def test_list_materials_success(monkeypatch, _noop_client):
    monkeypatch.setattr(
        lms_server.materials,
        "list_materials",
        AsyncMock(return_value=[Material(id=1, course_id=3, title="1주차 PDF")]),
    )
    result = await _dispatch("list_materials", {"course_id": 3}, SF)
    assert "1주차 PDF" in result[0].text


async def test_list_discussions_success(monkeypatch, _noop_client):
    monkeypatch.setattr(
        lms_server.notices,
        "list_discussions",
        AsyncMock(return_value=[Notice(id=1, course_id=4, title="토론1")]),
    )
    result = await _dispatch("list_discussions", {"course_id": 4}, SF)
    assert "토론1" in result[0].text


# ── 401(세션 만료)은 가드하지 않고 전파 ───────────────────────

async def test_session_expired_401_propagates(monkeypatch, _noop_client):
    """adapter 가 httpx 401 을 던지면 _dispatch 는 그대로 전파(전역/ base.py 변환).

    FileNotFoundError(로그인 전)만 가드하고 401(세션 만료)은 전파하는 경계를 고정.
    """
    request = httpx.Request("GET", "https://canvas.ssu.ac.kr/api/v1/courses")
    response = httpx.Response(401, request=request)
    err = httpx.HTTPStatusError("401", request=request, response=response)
    monkeypatch.setattr(
        lms_server.courses, "list_courses", AsyncMock(side_effect=err)
    )

    with pytest.raises(httpx.HTTPStatusError):
        await _dispatch("list_courses", {}, SF)


# ── unknown tool ──────────────────────────────────────────────

async def test_unknown_tool_raises_value_error():
    with pytest.raises(ValueError, match="unknown tool"):
        await _dispatch("nope", {}, SF)


# ── 잘못된 course_id 타입 → ValueError (안전 전파) ────────────

async def test_invalid_course_id_raises_value_error(monkeypatch, _noop_client):
    monkeypatch.setattr(lms_server.assignments, "list_assignments", AsyncMock())
    with pytest.raises(ValueError):
        await _dispatch("list_assignments", {"course_id": "notanumber"}, SF)


# ── deps._build_registry: LMS 무조건 등록 (setup 마운트 조건과 일치) ──

def test_build_registry_registers_lms_without_tokens():
    """토큰 전무여도 'lms'/'study' prefix 가 등록돼야 한다(setup.py 무조건 마운트와 짝).

    Notion/Obsidian 은 미설정이라 skip 되고 토큰 없는 lms/study 만 남는다.
    """
    from app.api.deps import _build_registry

    _build_registry.cache_clear()
    registry = _build_registry(
        lms_url="http://localhost:8000/mcp/lms/sse",
        study_url="http://localhost:8000/mcp/study/sse",
        grades_url="http://localhost:8000/mcp/grades/sse",
        materials_url="http://localhost:8000/mcp/materials/sse",
        notion_url="http://localhost:8000/mcp/notion/sse",
        notion_token="",
        notion_root="",
        obsidian_url="http://localhost:8000/mcp/obsidian/sse",
        obsidian_auth="",
    )
    assert registry.prefixes == ["lms", "study", "grades"]   # materials 는 obsidian 미설정이라 skip


def test_build_registry_lms_has_empty_headers():
    """LMS 클라이언트는 토큰이 없으므로 headers 가 비어 있어야 한다."""
    from app.api.deps import _build_registry

    _build_registry.cache_clear()
    registry = _build_registry(
        lms_url="http://localhost:8000/mcp/lms/sse",
        study_url="http://localhost:8000/mcp/study/sse",
        grades_url="http://localhost:8000/mcp/grades/sse",
        materials_url="http://localhost:8000/mcp/materials/sse",
        notion_url="http://localhost:8000/mcp/notion/sse",
        notion_token="",
        notion_root="",
        obsidian_url="http://localhost:8000/mcp/obsidian/sse",
        obsidian_auth="",
    )
    lms_client = registry._clients["lms"]
    assert lms_client.headers == {}
    assert lms_client.server_url == "http://localhost:8000/mcp/lms/sse"
