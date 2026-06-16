"""성적/GPA MCP 오프라인 회귀 테스트 (네트워크 0).

- _letter_gpa / summarize 순수 로직 (절대평가 추정)
- 도구 목록(2개, course_id 없음)
- 세션 없음(FileNotFoundError) → 한국어 안내
- list / summary 성공 경로(grades.list_grades monkeypatch) + 한글 JSON
- 401 전파 / unknown tool → ValueError
"""
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.mcp_client import grades_server
from app.mcp_client.grades_server import (
    NO_SESSION_MSG,
    _dispatch,
    _letter_gpa,
    create_grades_mcp_server,
    summarize,
)
from app.models import CourseGrade

SF = "/tmp/does-not-matter.json"


# ── 순수 로직 ─────────────────────────────────────────────────
def test_letter_gpa_scale():
    assert _letter_gpa(96) == ("A+", 4.5)
    assert _letter_gpa(90) == ("A0", 4.0)
    assert _letter_gpa(61.65) == ("D0", 1.0)
    assert _letter_gpa(50) == ("F", 0.0)
    assert _letter_gpa(None) == (None, None)


def test_summarize_basic():
    g = [
        CourseGrade(course_id=1, course_name="A", current_score=90.0),
        CourseGrade(course_id=2, course_name="B", current_score=70.0),
        CourseGrade(course_id=3, course_name="C", current_score=None),  # 점수 없음 → 제외
    ]
    s = summarize(g)
    assert s["courses"] == 3 and s["scored"] == 2
    assert s["average_score"] == 80.0
    assert s["highest"]["course"] == "A" and s["lowest"]["course"] == "B"
    assert s["gpa_estimate"] == 3.0   # (4.0 + 2.0)/2
    assert "추정치" in s["note"]


def test_summarize_no_scores():
    s = summarize([CourseGrade(course_id=1, course_name="A", current_score=None)])
    assert s["scored"] == 0 and "게시된 점수가 없습니다" in s["note"]


# ── 도구 목록 ─────────────────────────────────────────────────
async def _list_tools(server):
    import mcp.types as types
    handler = server.request_handlers[types.ListToolsRequest]
    result = await handler(types.ListToolsRequest(method="tools/list"))
    return result.root.tools


async def test_tools_exposed():
    tools = await _list_tools(create_grades_mcp_server(SF))
    names = {t.name for t in tools}
    assert names == {"list", "summary"}
    assert all(t.inputSchema.get("required", []) == [] for t in tools)


# ── 세션 / 성공 경로 ──────────────────────────────────────────
async def test_no_session_returns_korean(monkeypatch):
    async def _raise(self):
        raise FileNotFoundError
    monkeypatch.setattr(grades_server.CanvasClient, "init", _raise)
    result = await _dispatch("list", {}, SF)
    assert result[0].text == NO_SESSION_MSG


@pytest.fixture()
def _noop_client(monkeypatch):
    monkeypatch.setattr(grades_server.CanvasClient, "init", AsyncMock())
    monkeypatch.setattr(grades_server.CanvasClient, "close", AsyncMock())


async def test_list_success(monkeypatch, _noop_client):
    monkeypatch.setattr(grades_server.grades, "list_grades", AsyncMock(return_value=[
        CourseGrade(course_id=1, course_name="머신러닝 (2150163701)", current_score=88.0),
    ]))
    result = await _dispatch("list", {}, SF)
    assert "머신러닝" in result[0].text and "88" in result[0].text


async def test_summary_success(monkeypatch, _noop_client):
    monkeypatch.setattr(grades_server.grades, "list_grades", AsyncMock(return_value=[
        CourseGrade(course_id=1, course_name="A", current_score=90.0),
        CourseGrade(course_id=2, course_name="B", current_score=80.0),
    ]))
    result = await _dispatch("summary", {}, SF)
    data = json.loads(result[0].text)
    assert data["average_score"] == 85.0 and data["scored"] == 2


async def test_session_401_propagates(monkeypatch, _noop_client):
    req = httpx.Request("GET", "https://x")
    err = httpx.HTTPStatusError("401", request=req, response=httpx.Response(401, request=req))
    monkeypatch.setattr(grades_server.grades, "list_grades", AsyncMock(side_effect=err))
    with pytest.raises(httpx.HTTPStatusError):
        await _dispatch("list", {}, SF)


async def test_unknown_tool(monkeypatch, _noop_client):
    monkeypatch.setattr(grades_server.grades, "list_grades", AsyncMock(return_value=[]))
    with pytest.raises(ValueError):
        await _dispatch("nope", {}, SF)
