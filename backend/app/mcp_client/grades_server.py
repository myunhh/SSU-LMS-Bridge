"""성적/GPA adapter 를 in-process MCP 서버로 노출 (grades__*).

LMS MCP 와 동일 패턴(토큰 없음 → setup.py 무조건 마운트, deps._build_registry 무조건
등록; 세션 라이프사이클은 도구 호출마다 _client_cm). 도구는 2개:
  - grades__list    : 과목별 현재 성적(백분율) 목록
  - grades__summary : 평균/최고/최저 + 대략적 GPA 추정(절대평가 가정 — 추정치)

⚠️ 성적 *생성*이 아니라 *조회·요약*만 한다. GPA 추정은 SSU 상대평가와 다를 수 있어
'추정치'임을 응답에 명시한다(note 필드). 실제 학점 산정은 LLM/사용자 판단에 맡긴다.

테스트 용이성: 디스패치를 모듈 레벨 `_dispatch` 로 분리하고, 순수 함수 `summarize` /
`_letter_gpa` 로 GPA 로직을 노출한다 (tests/test_grades_mcp.py).
"""
import json
from contextlib import asynccontextmanager

from mcp.server import Server
from mcp.types import TextContent, Tool

from app.adapter import grades
from app.adapter.canvas_client import CanvasClient

NO_SESSION_MSG = "LMS 세션이 없습니다. 먼저 로그인하세요. (POST /api/lms/login)"

# 절대평가 가정의 점수→(letter, 평점/4.5) 추정 테이블. SSU 상대평가와 다를 수 있다.
_GPA_TABLE = [
    (95, "A+", 4.5), (90, "A0", 4.0), (85, "B+", 3.5), (80, "B0", 3.0),
    (75, "C+", 2.5), (70, "C0", 2.0), (65, "D+", 1.5), (60, "D0", 1.0),
]


def _dump(models) -> str:
    if isinstance(models, list):
        data = [m.model_dump() for m in models]
    else:
        data = models.model_dump()
    return json.dumps(data, ensure_ascii=False, default=str)


def _letter_gpa(score: float | None) -> tuple[str | None, float | None]:
    """백분율 점수 → (letter, 평점) 추정. None 이면 (None, None), 60 미만은 F/0.0."""
    if score is None:
        return None, None
    for cut, letter, gpa in _GPA_TABLE:
        if score >= cut:
            return letter, gpa
    return "F", 0.0


def summarize(grade_list: list) -> dict:
    """CourseGrade 리스트 → 요약 통계(평균/최고/최저/대략적 GPA). 순수 함수."""
    scored = [g for g in grade_list if g.current_score is not None]
    if not scored:
        return {"courses": len(grade_list), "scored": 0,
                "note": "게시된 점수가 없습니다 (SSU 는 성적을 학기말에 공개하기도 함)."}
    hi = max(scored, key=lambda g: g.current_score)
    lo = min(scored, key=lambda g: g.current_score)
    gpas = [_letter_gpa(g.current_score)[1] for g in scored]
    return {
        "courses": len(grade_list),
        "scored": len(scored),
        "average_score": round(sum(g.current_score for g in scored) / len(scored), 2),
        "highest": {"course": hi.course_name, "score": hi.current_score},
        "lowest": {"course": lo.course_name, "score": lo.current_score},
        "gpa_estimate": round(sum(gpas) / len(gpas), 2),
        "note": "gpa_estimate 는 절대평가 가정의 추정치 — SSU 상대평가/실제 학점과 다를 수 있음.",
    }


@asynccontextmanager
async def _client_cm(session_file: str):
    client = CanvasClient(session_file=session_file)
    await client.init()  # 세션 파일 없으면 FileNotFoundError
    try:
        yield client
    finally:
        await client.close()


async def _dispatch(name: str, arguments: dict, session_file: str) -> list[TextContent]:
    arguments = arguments or {}
    try:
        async with _client_cm(session_file) as client:
            grade_list = await grades.list_grades(client)
    except FileNotFoundError:
        return [TextContent(type="text", text=NO_SESSION_MSG)]

    if name == "list":
        return [TextContent(type="text", text=_dump(grade_list))]
    if name == "summary":
        return [TextContent(type="text",
                            text=json.dumps(summarize(grade_list), ensure_ascii=False))]
    raise ValueError(f"unknown tool: {name}")


def create_grades_mcp_server(session_file: str) -> Server:
    """성적/GPA MCP 서버 생성 (session_file: CanvasClient 세션 파일 절대경로)."""
    server = Server("grades-mcp")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="list",
                description=(
                    "수강 과목별 '현재 성적'(백분율 점수)을 LMS 에서 실시간 조회. "
                    "반환: CourseGrade[] JSON (course_name·current_score 등). "
                    "⚠️ SSU 는 letter grade 를 비워두기도 함(점수 % 가 주 신호)."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="summary",
                description=(
                    "전 과목 성적 요약 — 과목수·평균 점수·최고/최저 과목·대략적 GPA 추정. "
                    "gpa_estimate 는 숭실대학교 점수 산정 기준 가정 추정치. "
                    "'평점이 어떻게 돼?' 같은 질문에 이걸 호출해 요약하라."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        return await _dispatch(name, arguments, session_file)

    return server
