"""GET /api/mcp/status — in-process MCP 4종 상태 + 도구 목록 회귀 테스트 (오프라인).

검증
----
- 형태: 항상 4개(lms/study/notion/obsidian), 각 항목 {id,name,status,meta,tools,toolList,url}
- lms/study connected(도구수+toolList), notion/obsidian 미마운트 → disconnected
- toolList 의 {name, description} 가 응답에 그대로 실린다
- _tool_summary: 여러 줄 description → 첫 문장 한 줄 요약
- _ping_mcp 예외도 200 + 4개 disconnected (컨트랙트 유지)

실 네트워크/SSE 금지 — _ping_mcp 를 monkeypatch 로 대체한다.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import mcp


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(mcp.router, prefix="/api")
    return TestClient(app)


def _tools(n: int) -> list[dict]:
    return [{"name": f"tool{i}", "description": f"도구 {i} 설명"} for i in range(n)]


def _items(resp) -> dict:
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) == 4
    for item in data:
        assert set(item) == {"id", "name", "status", "meta", "tools", "toolList", "url"}
        assert item["status"] in ("connected", "disconnected")
        assert isinstance(item["tools"], int)
        assert isinstance(item["toolList"], list)
        assert item["tools"] == len(item["toolList"])
        assert item["url"].endswith("/sse")
    by_id = {item["id"]: item for item in data}
    assert set(by_id) == {"lms", "study", "notion", "obsidian"}
    return by_id


def test_per_server_tool_counts_and_toollist(client, monkeypatch):
    """lms/study connected(도구목록 포함), notion/obsidian 미마운트 → disconnected."""
    async def _fake_ping(url):
        if "/mcp/lms/" in url:
            return _tools(6)
        if "/mcp/study/" in url:
            return _tools(8)
        return None  # notion/obsidian 미마운트
    monkeypatch.setattr(mcp, "_ping_mcp", _fake_ping)

    items = _items(client.get("/api/mcp/status"))
    assert items["lms"]["status"] == "connected" and items["lms"]["tools"] == 6
    assert items["study"]["tools"] == 8
    # 도구 목록이 그대로 실리는지 (name/description)
    assert items["lms"]["toolList"][0] == {"name": "tool0", "description": "도구 0 설명"}
    assert items["notion"]["status"] == "disconnected"
    assert items["notion"]["tools"] == 0 and items["notion"]["toolList"] == []
    assert "미마운트" in items["notion"]["meta"]


def test_all_connected(client, monkeypatch):
    async def _fake_ping(url):
        return _tools(4)
    monkeypatch.setattr(mcp, "_ping_mcp", _fake_ping)
    items = _items(client.get("/api/mcp/status"))
    assert all(i["status"] == "connected" for i in items.values())
    assert all(i["tools"] == 4 for i in items.values())


def test_ping_exception_demoted_not_raised(client, monkeypatch):
    """_ping_mcp 가 예외를 던져도 200 + 4개 disconnected (컨트랙트 유지)."""
    async def _boom(url):
        raise RuntimeError("SSE 핸드셰이크 실패")
    monkeypatch.setattr(mcp, "_ping_mcp", _boom)
    items = _items(client.get("/api/mcp/status"))
    assert all(i["status"] == "disconnected" for i in items.values())


def test_tool_summary_first_sentence():
    """여러 줄/장문 description → 첫 문장 한 줄 요약."""
    assert mcp._tool_summary("저장한다. 두 번째 문장.") == "저장한다."
    assert mcp._tool_summary("퀴즈를 저장한다。 부연 설명") == "퀴즈를 저장한다。"
    assert mcp._tool_summary("  여러\n줄\n설명  ") == "여러 줄 설명"
    long = "가" * 200
    assert mcp._tool_summary(long).endswith("…") and len(mcp._tool_summary(long)) == 121
    assert mcp._tool_summary(None) == ""
