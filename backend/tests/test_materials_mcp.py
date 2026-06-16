"""강의자료 RAG MCP 오프라인 회귀 테스트 (네트워크/파일 0).

- _extract_text: ipynb/평문 추출 (pdf/pptx 바이너리는 라이브 검증)
- _snippets: 키워드 주변 스니펫
- 도구 목록(3개, read.path/search.query 필수)
- _dispatch: list_files/read/search (Obsidian IO·추출 monkeypatch)
- unknown tool → ValueError
"""
import json

import pytest

from app.mcp_client import materials_server as M
from app.mcp_client.materials_server import (
    _dispatch,
    _extract_text,
    _snippets,
    create_materials_mcp_server,
)


def _cfg():
    return {"base": "https://obs", "headers": {"Authorization": "Bearer x"},
            "verify": False, "vault": "LMS-Bridge"}


# ── 순수: 추출 / 스니펫 ───────────────────────────────────────
def test_extract_ipynb():
    nb = json.dumps({"cells": [
        {"source": ["import numpy as np\n", "print('신경망')"]},
        {"source": "x = 1"},
    ]}).encode("utf-8")
    out = _extract_text("note.ipynb", nb)
    assert "신경망" in out and "import numpy" in out


def test_extract_plaintext_fallback():
    assert "안녕" in _extract_text("a.txt", "안녕 세계".encode())


def test_extract_corrupt_does_not_raise():
    out = _extract_text("x.pdf", b"not a real pdf")
    assert out.startswith("(본문 추출 실패")   # 예외 대신 안내 텍스트


def test_snippets():
    text = "앞부분 " * 5 + "퍼셉트론은 신경망의 기본 단위" + " 뒷부분" * 5
    snips = _snippets(text, "신경망")
    assert len(snips) == 1 and "신경망" in snips[0]
    assert _snippets("없음", "신경망") == []


# ── 도구 목록 ─────────────────────────────────────────────────
async def _list_tools(server):
    import mcp.types as types
    handler = server.request_handlers[types.ListToolsRequest]
    result = await handler(types.ListToolsRequest(method="tools/list"))
    return result.root.tools


async def test_tools_exposed():
    tools = await _list_tools(create_materials_mcp_server("code", "https://obs", "LMS-Bridge"))
    by = {t.name: t for t in tools}
    assert set(by) == {"list_files", "read", "search"}
    assert by["read"].inputSchema["required"] == ["path"]
    assert by["search"].inputSchema["required"] == ["query"]


# ── 디스패치 ──────────────────────────────────────────────────
async def test_list_files(monkeypatch):
    async def _list_dir(base, headers, verify, rel):
        if rel.endswith("강의자료"):
            return ["머신러닝 (2150163701)/", "자료구조 (2150163201)/"]
        if "머신러닝" in rel:
            return ["1주차_소개.pptx", "thumbs/"]
        return ["01_DS.pdf"]
    monkeypatch.setattr(M, "_list_dir", _list_dir)

    result = await _dispatch("list_files", {}, _cfg())
    data = json.loads(result[0].text)
    paths = {d["path"] for d in data}
    assert "강의자료/머신러닝 (2150163701)/1주차_소개.pptx" in paths
    assert "강의자료/자료구조 (2150163201)/01_DS.pdf" in paths


async def test_read_extracts_text(monkeypatch):
    async def _read_bytes(base, headers, verify, rel):
        assert rel == "LMS-Bridge/강의자료/머신러닝/1주차.ipynb"   # vault_path 포함
        return json.dumps({"cells": [{"source": "퍼셉트론 정리"}]}).encode("utf-8")
    monkeypatch.setattr(M, "_read_bytes", _read_bytes)

    result = await _dispatch("read", {"path": "강의자료/머신러닝/1주차.ipynb"}, _cfg())
    assert "퍼셉트론" in result[0].text


async def test_read_missing_file(monkeypatch):
    async def _read_bytes(*a):
        return None
    monkeypatch.setattr(M, "_read_bytes", _read_bytes)
    result = await _dispatch("read", {"path": "강의자료/x/없음.pdf"}, _cfg())
    assert "찾을 수 없" in result[0].text


async def test_search(monkeypatch):
    async def _list_dir(base, headers, verify, rel):
        if rel.endswith("강의자료"):
            return ["머신러닝/"]
        return ["a.txt", "b.txt"]
    async def _read_bytes(base, headers, verify, rel):
        return ("퍼셉트론 신경망" if rel.endswith("a.txt") else "관계없는 내용").encode("utf-8")
    monkeypatch.setattr(M, "_list_dir", _list_dir)
    monkeypatch.setattr(M, "_read_bytes", _read_bytes)

    result = await _dispatch("search", {"query": "신경망"}, _cfg())
    data = json.loads(result[0].text)
    assert data["matched"] == 1
    assert data["results"][0]["path"].endswith("a.txt")


async def test_search_requires_query():
    with pytest.raises(ValueError):
        await _dispatch("search", {"query": "  "}, _cfg())


async def test_unknown_tool():
    with pytest.raises(ValueError):
        await _dispatch("nope", {}, _cfg())
