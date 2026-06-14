"""perform_sync 가 수집한 Course.materials 를 SyncResult.materials 로 집계하는지 회귀 테스트 (오프라인).

기존 버그: materials=0 하드코딩으로 프론트 '자료 N건' 요약이 영구 비표시 (#39).
list_courses 가 이미 채워 온 Course.materials 합을 SyncResult.materials 로 흘려야 한다.
"""
import json
from datetime import datetime

import pytest

from app.adapter.auth import SSULMSAuthPlaywright
from app.api.routes import sync
from app.config import settings
from app.models import Course


@pytest.fixture(autouse=True)
def isolated_session_file(monkeypatch, tmp_path):
    """실제 .cache/session_state.json 과 격리 + 가짜 세션 파일 생성 (test_lms_routes 패턴)."""
    monkeypatch.setattr(settings, "session_cache_path", str(tmp_path / "session_state.json"))
    path = settings.session_cache_abspath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"saved_at": datetime.now().isoformat(), "user_info": {"name": "테스트"}}),
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def preserve_sync_state():
    """perform_sync 가 _state['last_sync_at'] 을 바꾸므로 테스트 후 복원."""
    saved = dict(sync._state)
    yield
    sync._state.clear()
    sync._state.update(saved)


class _FakeCanvasClient:
    def __init__(self, *args, **kwargs): ...
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False


async def test_perform_sync_aggregates_course_materials(monkeypatch):
    """materials=3,5 인 강의 2개 → SyncResult.materials == 8."""
    async def _true(self, *a, **k): return True
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", _true)
    monkeypatch.setattr(sync, "CanvasClient", _FakeCanvasClient)

    fake_courses = [
        Course(id=1, name="고급프로그래밍 (2150164103)", materials=3),
        Course(id=2, name="자료구조 (2150164104)", materials=5),
    ]
    async def _courses(client): return fake_courses
    async def _empty(client, ids): return []
    monkeypatch.setattr(sync, "list_courses", _courses)
    monkeypatch.setattr(sync, "list_all_deadlines", _empty)
    monkeypatch.setattr(sync, "list_all_notices", _empty)

    # Notion/Obsidian 미설정(placeholder) → push 분기 건너뜀 — 개발자 .env 와 무관하게 고정
    monkeypatch.setattr(settings, "notion_token", "secret_xxxx")
    monkeypatch.setattr(settings, "notion_root_page_id", "xxxx")
    monkeypatch.setattr(settings, "obsidian_mcp_auth_code", "xxxx")

    result = await sync.perform_sync()

    assert result.materials == 8          # 핵심 회귀 — 하드코딩 0 이면 실패
    assert result.courses == 2
    assert result.success is True
    assert result.errors == []
