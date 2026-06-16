"""material_service — 강의자료 원본 파일 다운로드 회귀 테스트 (오프라인).

검증 항목
---------
- 순수 함수: _safe / _stem / _ext_of(file_name 우선·매직 폴백) / _is_video_bytes / classify_content
- 오케스트레이터 download_material_files:
  (a) 신규 file 항목 → 다운로드+저장, 매니페스트에 content_id/확장자 기록
  (b) 기존 Obsidian 파일 존재 → LTI 런치 없이 exists (출석 보호)
  (c) 매니페스트 hit(video) → 런치/다운로드 없이 skip
  (d) 영상/외부/대용량 분류가 각 카운터로 집계되고 매니페스트에 박제(재런치 방지)
  (e) docx(PK 매직이지만 file_name=.docx)는 .docx 로 저장(.pptx 오저장 방지)
- perform_sync 연동: download_files=False 또는 Obsidian 미설정 시 미호출

네트워크/브라우저 금지 — _playwright_context·_resolve_content_data·_download_original·
_existing_stems·MCPClientBase.session 을 가짜로 패치하고 MANIFEST_PATH 를 tmp 로 격리.
"""
import json
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.api.routes import sync
from app.config import settings
from app.mcp_client.base import MCPClientBase
from app.models import Course, Material, Notice
from app.services import material_service as M


# ── 순수 함수 ────────────────────────────────────────────────
def test_safe_and_stem():
    assert M._safe("1주차/특강") == "1주차_특강"
    assert M._safe("  .숨김 ") == "숨김"
    assert M._safe("") == "무제"
    assert M._stem("3주차", "OT 영상") == "3주차_OT 영상"


def test_ext_of_prefers_filename_then_magic():
    assert M._ext_of("note.PPTX", b"PK\x03\x04xx") == ".pptx"
    assert M._ext_of("data.docx", b"PK\x03\x04xx") == ".docx"   # PK 라도 docx 보존
    assert M._ext_of("", b"%PDF-1.7") == ".pdf"
    assert M._ext_of("", b"PK\x03\x04xx") == ".pptx"            # 매직 폴백
    assert M._ext_of("", b"\x00\x00unknown") == ".bin"


def test_is_video_bytes():
    assert M._is_video_bytes(b"\x00\x00\x00 ftypisom") is True
    assert M._is_video_bytes(b"%PDF-1.7") is False


def test_classify_content():
    assert M.classify_content({"content_id": "c1", "content_type": "file"}) == ("file", "c1")
    assert M.classify_content({"content_id": "c1", "content_type": "pdf"}) == ("file", "c1")
    assert M.classify_content({"content_id": "c1", "content_type": "movie"}) == ("video", "c1")
    assert M.classify_content({"content_type": "embed"}) == ("external", None)


# ── 오케스트레이터 픽스처 ────────────────────────────────────
class FakeSession:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return SimpleNamespace(isError=False, content=[SimpleNamespace(text="saved")])


@pytest.fixture()
def fake_env(monkeypatch, tmp_path):
    """브라우저/네트워크/MCP/매니페스트를 전부 가짜로 격리."""
    state = {"session": FakeSession(), "launches": [], "existing": set()}

    # 매니페스트 tmp 격리
    monkeypatch.setattr(M, "MANIFEST_PATH", tmp_path / "material_files_manifest.json")

    # 세션 파일(가짜)
    sf = tmp_path / "session_state.json"
    sf.write_text(json.dumps({"cookies": [], "origins": []}), encoding="utf-8")
    state["session_file"] = str(sf)

    # MCP 세션
    @asynccontextmanager
    async def _fake_mcp_session(self):
        yield state["session"]
    monkeypatch.setattr(MCPClientBase, "session", _fake_mcp_session)

    # Playwright 컨텍스트 — 더미 ctx
    @asynccontextmanager
    async def _fake_ctx(storage):
        yield SimpleNamespace(name="dummy-ctx")
    monkeypatch.setattr(M, "_playwright_context", _fake_ctx)

    # 기존 파일(Obsidian) 조회
    async def _fake_existing(course_folder):
        return set(state["existing"])
    monkeypatch.setattr(M, "_existing_stems", _fake_existing)

    return state


def _materials():
    # 같은 과목(course_id=1)의 여러 항목 — Assignment 는 대상 아님(필터로 제외)
    return [
        Material(id=10, course_id=1, module_name="1주차", title="PPT자료",
                 item_type="ExternalTool", url="https://lms/items/10"),
        Material(id=11, course_id=1, module_name="1주차", title="영상자료",
                 item_type="ExternalTool", url="https://lms/items/11"),
        Material(id=12, course_id=1, module_name="2주차", title="외부링크",
                 item_type="ExternalTool", url="https://lms/items/12"),
        Material(id=13, course_id=1, module_name="2주차", title="과제임",
                 item_type="Assignment", url="https://lms/items/13"),
    ]


def _name_map():
    return {1: "운영체제 (123)"}


async def test_new_items_classified_and_saved(fake_env, monkeypatch):
    """(a)(d) 신규: PPT 저장 · 영상/외부 분류 · Assignment 제외 · 매니페스트 박제."""
    async def _resolve(ctx, url):
        return {
            "https://lms/items/10": {"content_id": "cidP", "content_type": "file",
                                     "file_name": "01_OT.pptx"},
            "https://lms/items/11": {"content_id": "cidV", "content_type": "movie"},
            "https://lms/items/12": {"content_type": "embed"},  # content_id 없음
        }[url]
    monkeypatch.setattr(M, "_resolve_content_data", _resolve)

    async def _download(hc, cid):
        return ("ok", b"PK\x03\x04" + b"x" * 20000)  # 정상 pptx(>10KB)
    monkeypatch.setattr(M, "_download_original", _download)

    res = await M.download_material_files(
        _materials(), _name_map(), fake_env["session_file"], "http://mock/sse", "code")

    assert res == {"saved": 1, "exists": 0, "video": 1, "external": 1, "big": 0, "failed": 0}
    # 저장 경로/확장자
    paths = [c[1]["relative_path"] for c in fake_env["session"].calls]
    assert paths == ["강의자료/운영체제 (123)/1주차_PPT자료.pptx"]
    # 매니페스트 박제 — 재실행 시 런치 안 하도록 status 기록
    mani = M.load_manifest()
    assert mani["1:10"]["status"] == "file" and mani["1:10"]["content_id"] == "cidP"
    assert mani["1:11"]["status"] == "video"
    assert mani["1:12"]["status"] == "external"
    assert "1:13" not in mani  # Assignment 은 대상 아님


async def test_existing_obsidian_file_skips_launch(fake_env, monkeypatch):
    """(b) 이미 Obsidian 에 있는 파일은 LTI 런치 없이 exists (출석 보호)."""
    fake_env["existing"] = {"1주차_PPT자료"}  # stem 이 이미 존재

    launched = {"n": 0}
    async def _resolve(ctx, url):
        launched["n"] += 1
        return {"content_id": "x", "content_type": "file", "file_name": "x.pptx"}
    monkeypatch.setattr(M, "_resolve_content_data", _resolve)
    async def _download(hc, cid):
        return ("ok", b"PK\x03\x04" + b"x" * 20000)
    monkeypatch.setattr(M, "_download_original", _download)

    res = await M.download_material_files(
        [_materials()[0]], _name_map(), fake_env["session_file"], "http://mock/sse", "code")

    assert res["exists"] == 1 and res["saved"] == 0
    assert launched["n"] == 0  # 런치 안 함
    assert M.load_manifest()["1:10"]["preexisting"] is True


async def test_manifest_hit_skips_relaunch(fake_env, monkeypatch):
    """(c) 매니페스트에 video 로 박제된 항목은 재런치/재다운로드 없이 skip."""
    M.save_manifest({"1:11": {"status": "video", "content_id": "cidV"}})

    launched = {"n": 0}
    async def _resolve(ctx, url):
        launched["n"] += 1
        return {}
    monkeypatch.setattr(M, "_resolve_content_data", _resolve)

    res = await M.download_material_files(
        [_materials()[1]], _name_map(), fake_env["session_file"], "http://mock/sse", "code")

    assert res["video"] == 1
    assert launched["n"] == 0


async def test_docx_extension_preserved(fake_env, monkeypatch):
    """(e) file_name 이 .docx 면 PK 매직이라도 .docx 로 저장(.pptx 오저장 방지)."""
    async def _resolve(ctx, url):
        return {"content_id": "cidD", "content_type": "file", "file_name": "outline.docx"}
    monkeypatch.setattr(M, "_resolve_content_data", _resolve)
    async def _download(hc, cid):
        return ("ok", b"PK\x03\x04" + b"x" * 20000)
    monkeypatch.setattr(M, "_download_original", _download)

    await M.download_material_files(
        [_materials()[0]], _name_map(), fake_env["session_file"], "http://mock/sse", "code")
    path = fake_env["session"].calls[0][1]["relative_path"]
    assert path.endswith("1주차_PPT자료.docx")


async def test_big_file_skipped_and_recorded(fake_env, monkeypatch):
    """대용량(녹화영상) → big 카운트 + 매니페스트 박제, 저장 안 함."""
    async def _resolve(ctx, url):
        return {"content_id": "cidBig", "content_type": "file", "file_name": "lecture.pptx"}
    monkeypatch.setattr(M, "_resolve_content_data", _resolve)
    async def _download(hc, cid):
        return ("big", None)
    monkeypatch.setattr(M, "_download_original", _download)

    res = await M.download_material_files(
        [_materials()[0]], _name_map(), fake_env["session_file"], "http://mock/sse", "code")
    assert res["big"] == 1 and res["saved"] == 0
    assert len(fake_env["session"].calls) == 0
    assert M.load_manifest()["1:10"]["status"] == "big"


# ── perform_sync 연동 ────────────────────────────────────────
@pytest.fixture()
def isolated_session_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "session_cache_path", str(tmp_path / "session_state.json"))
    path = settings.session_cache_abspath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"saved_at": datetime.now().isoformat(), "user_info": {"name": "테스트"}}),
        encoding="utf-8",
    )


@pytest.fixture()
def preserve_sync_state():
    saved = dict(sync._state)
    yield
    sync._state.clear()
    sync._state.update(saved)


class _FakeCanvasClient:
    def __init__(self, *a, **k): ...
    async def __aenter__(self): return self
    async def __aexit__(self, *e): return False


def _patch_collectors(monkeypatch):
    from app.adapter.auth import SSULMSAuthPlaywright

    async def _true(self, *a, **k): return True
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", _true)
    monkeypatch.setattr(sync, "CanvasClient", _FakeCanvasClient)

    async def _courses(client):
        return [Course(id=1, name="운영체제 (123)", materials=1)]
    async def _empty(client, ids): return []
    async def _notices(client, ids):
        return [Notice(id=1, course_id=1, title="공지", posted_at="2026-06-01T00:00:00Z")]
    async def _materials(client, ids):
        return [Material(id=10, course_id=1, module_name="1주차", title="PPT",
                         item_type="ExternalTool", url="https://lms/items/10")]
    monkeypatch.setattr(sync, "list_courses", _courses)
    monkeypatch.setattr(sync, "list_all_deadlines", _empty)
    monkeypatch.setattr(sync, "list_all_notices", _notices)
    monkeypatch.setattr(sync, "list_all_materials", _materials)
    monkeypatch.setattr(settings, "notion_token", "secret_xxxx")
    monkeypatch.setattr(settings, "notion_root_page_id", "xxxx")


async def test_perform_sync_calls_download_when_enabled(
    monkeypatch, isolated_session_file, preserve_sync_state
):
    """download_files=True + Obsidian 설정 → download_material_files 호출."""
    _patch_collectors(monkeypatch)
    monkeypatch.setattr(settings, "obsidian_mcp_auth_code", "real_code")
    monkeypatch.setattr(settings, "download_files", True)

    async def _noop_obsidian(*a, **k): return {"saved": 0, "skipped": 0, "failed": 0}
    monkeypatch.setattr(sync, "sync_obsidian", _noop_obsidian)

    called = {"n": 0, "materials": None}
    async def _spy(materials, name_map, session_file, url, code):
        called["n"] += 1
        called["materials"] = materials
        return {"saved": 1, "exists": 0, "video": 0, "external": 0, "big": 0, "failed": 0}
    monkeypatch.setattr(sync, "download_material_files", _spy)

    result = await sync.perform_sync()
    assert called["n"] == 1
    assert len(called["materials"]) == 1  # 수집된 Material 전달
    assert result.success is True


async def test_perform_sync_skips_download_when_disabled(
    monkeypatch, isolated_session_file, preserve_sync_state
):
    """download_files=False → 미호출 (Obsidian 설정돼 있어도)."""
    _patch_collectors(monkeypatch)
    monkeypatch.setattr(settings, "obsidian_mcp_auth_code", "real_code")
    monkeypatch.setattr(settings, "download_files", False)

    async def _noop_obsidian(*a, **k): return {"saved": 0, "skipped": 0, "failed": 0}
    monkeypatch.setattr(sync, "sync_obsidian", _noop_obsidian)

    called = {"n": 0}
    async def _spy(*a, **k):
        called["n"] += 1
        return {}
    monkeypatch.setattr(sync, "download_material_files", _spy)

    await sync.perform_sync()
    assert called["n"] == 0


async def test_perform_sync_download_failure_collected_not_raised(
    monkeypatch, isolated_session_file, preserve_sync_state
):
    """다운로드 단계 예외는 errors 로 수거되고 sync 를 깨지 않는다."""
    _patch_collectors(monkeypatch)
    monkeypatch.setattr(settings, "obsidian_mcp_auth_code", "real_code")
    monkeypatch.setattr(settings, "download_files", True)

    async def _noop_obsidian(*a, **k): return {"saved": 0, "skipped": 0, "failed": 0}
    monkeypatch.setattr(sync, "sync_obsidian", _noop_obsidian)

    async def _boom(*a, **k):
        raise RuntimeError("Chromium 없음")
    monkeypatch.setattr(sync, "download_material_files", _boom)

    result = await sync.perform_sync()
    assert any("강의자료 파일" in e for e in result.errors)
    assert result.success is False
