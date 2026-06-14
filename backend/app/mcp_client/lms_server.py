"""LMS adapter 를 in-process MCP 서버로 노출.

설계
----
Notion / Obsidian MCP 와 동일한 패턴(factory → Starlette sub-app → SSE → 같은
프로세스 클라이언트)을 따르되, LMS 만의 두 가지 차이를 해결한다:
  (a) 토큰이 없으니 setup.py 에서 무조건 마운트한다(세션 미존재는 도구 호출 시점에
      한국어 안내로 처리하므로 마운트는 안전).
  (b) CanvasClient 세션 파일 라이프사이클을 도구 핸들러가 직접 관리한다 — MCP tool
      핸들러는 FastAPI DI(get_canvas_client) 밖이므로 호출마다 새 CanvasClient 를
      만들어 init() → adapter 실행 → finally close() 한다.

세션 라이프사이클 / 오류 경계
-----------------------------
- 세션 파일 없음(=로그인 전): CanvasClient.init() 이 FileNotFoundError 를 던지면
  공통 래퍼(`_run`)가 잡아 한국어 안내 TextContent 를 반환한다 — 예외로 죽지 않음.
- 세션 만료(=401): adapter 가 던지는 httpx 401 은 가드하지 **않고** 그대로 전파한다.
  base.py `call_tool_in` 이 RuntimeError("MCP tool '...' 실패: ...") 로 변환 →
  llm.py tool 루프가 `tool_result`(ERROR ...)로 받아 LLM 이 "재로그인 필요"를
  답하게 한다. (로그인 전=FileNotFoundError 친절 안내 vs 세션 만료=401 전파 —
  adapter 의 is_session_unauthorized 전파 정책과 일관.)

테스트 용이성
-------------
SSE/Server 내부 구조에 의존하지 않고 100% 오프라인 단위 테스트가 가능하도록,
실제 디스패치 로직을 모듈 레벨 `_dispatch(name, arguments, session_file)` 로 분리하고
factory 의 @server.call_tool() 데코레이터가 거기에 위임한다. `_dump` 도 순수 함수로
모듈 레벨에 노출한다.
"""
import json
from contextlib import asynccontextmanager

from mcp.server import Server
from mcp.types import TextContent, Tool

from app.adapter import assignments, courses, materials, notices
from app.adapter.canvas_client import CanvasClient

# 세션 파일이 없을 때(=로그인 전) 도구가 예외 대신 반환하는 한국어 안내.
NO_SESSION_MSG = "LMS 세션이 없습니다. 먼저 로그인하세요. (POST /api/lms/login)"


def _dump(models) -> str:
    """Pydantic 모델(또는 모델 리스트) → JSON 문자열.

    LLM 소비용이라 ensure_ascii=False 로 한글을 유지한다. datetime 등 비직렬화
    필드 방어로 default=str (Course/Notice/Assignment/Material 은 모두 단순
    필드라 실제로는 안전하지만 방어적으로 둔다).
    """
    if isinstance(models, list):
        data = [m.model_dump() for m in models]
    else:
        data = models.model_dump()
    return json.dumps(data, ensure_ascii=False, default=str)


@asynccontextmanager
async def _client_cm(session_file: str):
    """도구 호출 단위 CanvasClient 라이프사이클 (get_canvas_client 패턴 이식).

    세션 파일이 없으면 init() 이 FileNotFoundError 를 던지고, 그 경우 _run 이
    한국어 안내로 변환한다. 정상이면 yield 후 finally 에서 반드시 close().
    """
    client = CanvasClient(session_file=session_file)
    await client.init()  # 세션 파일 없으면 FileNotFoundError
    try:
        yield client
    finally:
        await client.close()


async def _run(session_file: str, coro_factory) -> list[TextContent]:
    """adapter 호출 공통 래퍼.

    - FileNotFoundError(로그인 전)만 가드해 한국어 안내 TextContent 반환.
    - 401(세션 만료) 등 그 외 예외는 전파시켜 base.py 가 RuntimeError 로 변환하게 한다.
    """
    try:
        async with _client_cm(session_file) as client:
            models = await coro_factory(client)
    except FileNotFoundError:
        return [TextContent(type="text", text=NO_SESSION_MSG)]
    return [TextContent(type="text", text=_dump(models))]


async def _dispatch(name: str, arguments: dict, session_file: str) -> list[TextContent]:
    """tool 이름별 adapter 호출 디스패치 (factory 의 call_tool 데코레이터가 위임).

    course_id 는 LLM 이 문자열로 줄 수 있어 int() 로 캐스팅한다(잘못된 값은
    ValueError → tool_result ERROR 로 안전 전파).
    """
    arguments = arguments or {}

    if name == "list_courses":
        return await _run(session_file, lambda c: courses.list_courses(c))

    if name == "list_assignments":
        course_id = int(arguments["course_id"])
        return await _run(
            session_file, lambda c: assignments.list_assignments(c, course_id)
        )

    if name == "list_deadlines":
        async def _deadlines(c):
            course_ids = await courses.list_course_ids(c)
            return await assignments.list_all_deadlines(c, course_ids)

        return await _run(session_file, _deadlines)

    if name == "list_notices":
        if arguments.get("course_id") is not None:
            course_id = int(arguments["course_id"])
            return await _run(session_file, lambda c: notices.list_notices(c, course_id))

        async def _all_notices(c):
            course_ids = await courses.list_course_ids(c)
            return await notices.list_all_notices(c, course_ids)

        return await _run(session_file, _all_notices)

    if name == "list_materials":
        course_id = int(arguments["course_id"])
        return await _run(session_file, lambda c: materials.list_materials(c, course_id))

    if name == "list_discussions":
        course_id = int(arguments["course_id"])
        return await _run(session_file, lambda c: notices.list_discussions(c, course_id))

    # 알 수 없는 tool 이름 — None 반환 시 SDK 가 'Unexpected return type' 오류를
    # 내므로 명시적으로 거부한다 (notion/obsidian_server.py 와 동일 정책).
    raise ValueError(f"unknown tool: {name}")


_NO_ARG_SCHEMA = {"type": "object", "properties": {}}
_COURSE_ID_REQUIRED_SCHEMA = {
    "type": "object",
    "properties": {"course_id": {"type": "integer"}},
    "required": ["course_id"],
}


def create_lms_mcp_server(session_file: str) -> Server:
    """LMS adapter 를 노출하는 MCP 서버 생성.

    session_file: CanvasClient 세션 파일 절대경로(라이프스팬 동안 고정).
        도구 호출 시점마다 이 경로로 새 CanvasClient 를 만든다.
    """
    server = Server("lms-mcp")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="list_courses",
                description=(
                    "수강 강의 목록을 LMS 에서 실시간 직접 조회 "
                    "(교수/진도율/자료수 포함). 반환: Course[] JSON 배열 문자열."
                ),
                inputSchema=_NO_ARG_SCHEMA,
            ),
            Tool(
                name="list_assignments",
                description=(
                    "특정 과목의 과제 목록을 LMS 에서 실시간 직접 조회 "
                    "(제출 여부 포함). 반환: Assignment[] JSON."
                ),
                inputSchema=_COURSE_ID_REQUIRED_SCHEMA,
            ),
            Tool(
                name="list_deadlines",
                description=(
                    "전 과목 과제 마감일을 LMS 에서 실시간 직접 조회, 마감일 오름차순 "
                    "JSON 배열. (전 과목 마감 한 번에 보고 싶을 때 이걸 우선 사용.)"
                ),
                inputSchema=_NO_ARG_SCHEMA,
            ),
            Tool(
                name="list_notices",
                description=(
                    "공지사항을 LMS 에서 실시간 직접 조회. course_id 지정 시 해당 과목, "
                    "생략 시 전 과목 통합. 반환: Notice[] JSON."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"course_id": {"type": "integer"}},
                },
            ),
            Tool(
                name="list_materials",
                description=(
                    "특정 과목의 주차별 강의 자료(모듈 아이템) 목록을 LMS 에서 실시간 "
                    "직접 조회. 반환: Material[] JSON."
                ),
                inputSchema=_COURSE_ID_REQUIRED_SCHEMA,
            ),
            Tool(
                name="list_discussions",
                description=(
                    "특정 과목의 토론 목록을 LMS 에서 실시간 직접 조회 "
                    "(공지 탭과 겹치지 않는 일반 토론). 반환: Notice[] JSON."
                ),
                inputSchema=_COURSE_ID_REQUIRED_SCHEMA,
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        return await _dispatch(name, arguments, session_file)

    return server
