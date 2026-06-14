"""sync_obsidian — 단일 SSE 세션 + manifest skip + 경로 새니타이즈 회귀 테스트 (오프라인).

검증 항목
---------
- (a) push 전체가 단일 세션으로 처리되고 write_file 인자(relative_path/mime_type)가 정확한지
- (b) 동일 입력 2회 → 2회차는 manifest 로 전건 skip (write_file 호출 0)
- (c) 부분 실패(예외 + "failed" 반환)는 failed 로 집계되고 나머지는 계속 진행
- (d) 제목의 '/' 가 추가 폴더로 새지 않게 새니타이즈
- (e) perform_sync 연동 — obsidian 미설정 시 미호출, 설정 시 호출 + 실패가 errors 로 수거

네트워크 금지 — MCPClientBase.session 을 asynccontextmanager 가짜로 패치하고
MANIFEST_PATH 를 tmp_path 로 격리한다.
"""
import json
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.adapter.auth import SSULMSAuthPlaywright
from app.api.routes import sync
from app.config import settings
from app.mcp_client.base import MCPClientBase
from app.models import Course, Notice
from app.services import vault_service
from app.services.vault_service import sync_obsidian


def _tool_result(text: str):
    return SimpleNamespace(isError=False, content=[SimpleNamespace(text=text)])


class FakeSession:
    """가짜 ClientSession — write_file 호출 기록 + 지정 경로만 실패/예외."""

    def __init__(self, fail_paths: set[str] | None = None, raise_paths: set[str] | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.fail_paths = fail_paths or set()
        self.raise_paths = raise_paths or set()

    async def call_tool(self, name: str, arguments: dict):
        self.calls.append((name, arguments))
        path = arguments.get("relative_path", "")
        if path in self.raise_paths:
            raise RuntimeError("Obsidian REST 일시 오류")
        if path in self.fail_paths:
            return _tool_result("failed")
        return _tool_result("saved")


@pytest.fixture()
def fake_mcp(monkeypatch, tmp_path):
    """MCPClientBase.session 가짜 교체 + manifest 격리."""
    state = {"session": FakeSession(), "opened": 0}

    @asynccontextmanager
    async def _fake_session(self):
        state["opened"] += 1
        yield state["session"]

    monkeypatch.setattr(MCPClientBase, "session", _fake_session)
    monkeypatch.setattr(vault_service, "MANIFEST_PATH", tmp_path / "vault_manifest.json")
    return state


_NOTICES = [
    {"title": "공지1", "course_name": "고급프로그래밍", "date": "2026-06-01", "pinned": True,
     "unread": True, "text": "본문1"},
    {"title": "공지2", "course_name": "자료구조", "date": "2026-06-02", "pinned": False,
     "unread": False, "text": "본문2"},
]
_ASSIGNMENTS = [
    {"title": "과제1", "course_name": "고급프로그래밍", "due": "2026-06-10", "type": "report",
     "weight": 100, "submitted": False, "text": "보고서 제출"},
]


async def test_sync_obsidian_single_session_and_paths(fake_mcp):
    """(a) 단일 세션 + write_file 인자(경로/mime) 검증."""
    result = await sync_obsidian(_NOTICES, _ASSIGNMENTS, "http://mock/sse", "code")

    assert fake_mcp["opened"] == 1
    calls = fake_mcp["session"].calls
    assert len(calls) == 3  # 공지 2 + 과제 1
    names = {c[0] for c in calls}
    assert names == {"write_file"}
    paths = [c[1]["relative_path"] for c in calls]
    assert "공지/고급프로그래밍/공지1.md" in paths
    assert "과제/고급프로그래밍/과제1.md" in paths
    assert all(c[1]["mime_type"] == "text/markdown" for c in calls)
    assert result == {"saved": 3, "skipped": 0, "failed": 0}


async def test_sync_obsidian_skips_unchanged_on_second_run(fake_mcp):
    """(b) 동일 입력 2회 → 2회차는 전건 skip (write_file 호출 0)."""
    await sync_obsidian(_NOTICES, _ASSIGNMENTS, "http://mock/sse", "code")
    fake_mcp["session"].calls.clear()

    result = await sync_obsidian(_NOTICES, _ASSIGNMENTS, "http://mock/sse", "code")
    assert result["saved"] == 0
    assert result["skipped"] == 3
    assert len(fake_mcp["session"].calls) == 0


async def test_sync_obsidian_partial_failure(fake_mcp):
    """(c) 한 건 예외 + 한 건 "failed" → failed=2, 나머지는 저장·manifest 미기록."""
    fake_mcp["session"].raise_paths = {"공지/고급프로그래밍/공지1.md"}
    fake_mcp["session"].fail_paths = {"공지/자료구조/공지2.md"}

    result = await sync_obsidian(_NOTICES, _ASSIGNMENTS, "http://mock/sse", "code")
    assert result["failed"] == 2
    assert result["saved"] == 1
    # 모든 항목이 시도됐는지
    assert len(fake_mcp["session"].calls) == 3
    # 실패 건은 manifest 에 기록되지 않아 다음 실행에서 재시도된다
    manifest = vault_service.load_manifest()
    assert "공지/고급프로그래밍/공지1.md" not in manifest
    assert "과제/고급프로그래밍/과제1.md" in manifest


async def test_sync_obsidian_sanitizes_slash_in_title(fake_mcp):
    """(d) 제목의 '/' 가 추가 폴더로 새지 않는다."""
    notices = [{"title": "중간고사/필독", "course_name": "운영체제", "date": "2026-06-01",
                "pinned": False, "unread": True, "text": "x"}]
    await sync_obsidian(notices, [], "http://mock/sse", "code")
    path = fake_mcp["session"].calls[0][1]["relative_path"]
    assert path == "공지/운영체제/중간고사_필독.md"
    # 폴더 깊이는 정확히 3 segment (공지/과목/파일)
    assert path.count("/") == 2


# ── 강의자료(주차별 목록) push ───────────────────────────────

_MATERIALS = [
    {"course_name": "운영체제", "module_name": "1주차", "title": "OT 영상", "type": "강의자료",
     "url": "https://lms/x/1", "position": 1},
    {"course_name": "운영체제", "module_name": "1주차", "title": "강의노트", "type": "파일",
     "url": "https://lms/x/2", "position": 2},
    {"course_name": "운영체제", "module_name": "2주차", "title": "스케줄링", "type": "강의자료",
     "url": "https://lms/x/3", "position": 1},
    {"course_name": "자료구조", "module_name": "1주차", "title": "트리", "type": "강의자료",
     "url": "https://lms/x/4", "position": 1},
]


async def test_sync_obsidian_materials_grouped_by_course_and_week(fake_mcp):
    """강의자료는 과목당 1파일(강의자료/{과목}.md)에 주차별 목록 + 딥링크로 저장된다."""
    result = await sync_obsidian([], [], "http://mock/sse", "code", materials=_MATERIALS)
    calls = fake_mcp["session"].calls
    paths = [c[1]["relative_path"] for c in calls]
    # 과목당 정확히 1파일 (2과목 → 2파일)
    assert paths == ["강의자료/운영체제.md", "강의자료/자료구조.md"]
    assert result == {"saved": 2, "skipped": 0, "failed": 0}
    # 운영체제 노트: 주차 그룹 + position 정렬 + 링크·유형
    os_md = next(c[1]["content"] for c in calls if c[1]["relative_path"] == "강의자료/운영체제.md")
    assert "## 1주차" in os_md and "## 2주차" in os_md
    assert os_md.index("## 1주차") < os_md.index("## 2주차")
    assert os_md.index("OT 영상") < os_md.index("강의노트")  # position 1 < 2
    assert "[OT 영상](https://lms/x/1) · 강의자료" in os_md
    assert "[강의노트](https://lms/x/2) · 파일" in os_md


def test_materials_markdown_is_deterministic():
    """동일 입력 → 동일 바이트 (manifest 해시 skip 이 동작하려면 결정적이어야 함)."""
    md1 = vault_service._materials_markdown("운영체제", _MATERIALS[:3])
    md2 = vault_service._materials_markdown("운영체제", _MATERIALS[:3])
    assert md1 == md2
    assert md1.startswith("# 운영체제 강의자료")


def test_materials_markdown_renders_link_or_plain():
    """url 있으면 링크, 없으면 평문 — 둘 다 유형 라벨을 붙인다."""
    items = [
        {"module_name": "1주차", "title": "링크자료", "type": "강의자료", "url": "https://x", "position": 1},
        {"module_name": "1주차", "title": "링크없음", "type": "파일", "url": "", "position": 2},
    ]
    md = vault_service._materials_markdown("과목", items)
    assert "[링크자료](https://x) · 강의자료" in md
    assert "- 링크없음 · 파일" in md


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
    def __init__(self, *args, **kwargs): ...
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False


def _patch_sync_collectors(monkeypatch):
    async def _true(self, *a, **k): return True
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", _true)
    monkeypatch.setattr(sync, "CanvasClient", _FakeCanvasClient)

    async def _courses(client):
        return [Course(id=1, name="고급프로그래밍 (2150164103)", materials=0)]
    async def _no_deadlines(client, ids): return []
    async def _notices(client, ids):
        return [Notice(id=1, course_id=1, title="공지A", posted_at="2026-06-01T00:00:00Z")]
    async def _no_materials(client, ids): return []
    monkeypatch.setattr(sync, "list_courses", _courses)
    monkeypatch.setattr(sync, "list_all_deadlines", _no_deadlines)
    monkeypatch.setattr(sync, "list_all_notices", _notices)
    monkeypatch.setattr(sync, "list_all_materials", _no_materials)
    # Notion 은 항상 미설정으로 고정 (이 테스트는 Obsidian 경로만 본다)
    monkeypatch.setattr(settings, "notion_token", "secret_xxxx")
    monkeypatch.setattr(settings, "notion_root_page_id", "xxxx")


async def test_perform_sync_skips_obsidian_when_unconfigured(
    monkeypatch, isolated_session_file, preserve_sync_state
):
    """obsidian 미설정 → sync_obsidian 미호출."""
    _patch_sync_collectors(monkeypatch)
    monkeypatch.setattr(settings, "obsidian_mcp_auth_code", "xxxx")

    called = {"n": 0}
    async def _spy(*a, **k):
        called["n"] += 1
        return {"saved": 0, "skipped": 0, "failed": 0}
    monkeypatch.setattr(sync, "sync_obsidian", _spy)

    result = await sync.perform_sync()
    assert called["n"] == 0
    assert result.success is True


async def test_perform_sync_calls_obsidian_and_collects_failures(
    monkeypatch, isolated_session_file, preserve_sync_state
):
    """obsidian 설정 → 호출 + failed 가 errors 로 수거되고 예외 전파 안 함."""
    _patch_sync_collectors(monkeypatch)
    monkeypatch.setattr(settings, "obsidian_mcp_auth_code", "real_code")

    called = {"n": 0}
    async def _spy(*a, **k):
        called["n"] += 1
        return {"saved": 0, "skipped": 0, "failed": 2}
    monkeypatch.setattr(sync, "sync_obsidian", _spy)

    result = await sync.perform_sync()
    assert called["n"] == 1
    assert any("obsidian" in e for e in result.errors)
    assert result.success is False  # failed 가 errors 로 드러남
