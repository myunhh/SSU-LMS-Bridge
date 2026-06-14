"""perform_sync 의 Notion payload 조립 회귀 테스트 (오프라인).

기존 버그: notice payload 의 pinned 가 항상 False 하드코딩이라 (#?) Notice.pinned
(discussion_topics.pinned 원천)가 Notion '중요' 체크박스로 흐르지 않았다.
이 테스트는 perform_sync 가 Notice.pinned 를 payload['pinned'] 로 정확히 옮기는지
(네트워크/Playwright 없이) 검증한다.
"""
import json
from datetime import datetime

import pytest

from app.adapter.auth import SSULMSAuthPlaywright
from app.api.routes import sync
from app.config import settings
from app.models import Assignment, Course, Notice


@pytest.fixture(autouse=True)
def isolated_session_file(monkeypatch, tmp_path):
    """실제 .cache/session_state.json 과 격리 + 가짜 세션 파일 생성."""
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


async def test_perform_sync_maps_notice_pinned_into_notion_payload(monkeypatch):
    """Notice(pinned=True/False) → Notion payload['pinned'] 1:1 매핑."""
    async def _true(self, *a, **k): return True
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", _true)
    monkeypatch.setattr(sync, "CanvasClient", _FakeCanvasClient)

    fake_courses = [Course(id=1, name="고급프로그래밍 (2150164103)", materials=0)]
    fake_notices = [
        Notice(
            id=10, course_id=1, title="고정 공지",
            posted_at="2026-06-01T00:00:00Z", is_read=False, pinned=True,
        ),
        Notice(
            id=11, course_id=1, title="일반 공지",
            posted_at="2026-06-02T00:00:00Z", is_read=True, pinned=False,
        ),
    ]

    async def _courses(client): return fake_courses
    async def _no_deadlines(client, ids): return []
    async def _notices(client, ids): return fake_notices
    monkeypatch.setattr(sync, "list_courses", _courses)
    monkeypatch.setattr(sync, "list_all_deadlines", _no_deadlines)
    monkeypatch.setattr(sync, "list_all_notices", _notices)

    # Notion 설정됨 → push 분기 진입 (실제 MCP 는 캡처용 가짜로 교체)
    monkeypatch.setattr(settings, "notion_token", "secret_real")
    monkeypatch.setattr(settings, "notion_root_page_id", "rootpage123")
    # Obsidian 은 미설정으로 고정 (push 분기 영향 차단)
    monkeypatch.setattr(settings, "obsidian_mcp_auth_code", "xxxx")

    captured: dict = {}

    async def _fake_sync_notion(notices, assignments, notion_mcp_url, notion_token):
        captured["notices"] = notices
        captured["assignments"] = assignments
        return {"notices_added": 0, "assignments_added": 0, "failed": 0}

    monkeypatch.setattr(sync, "sync_notion", _fake_sync_notion)

    result = await sync.perform_sync()

    assert result.success is True
    by_title = {n["title"]: n["pinned"] for n in captured["notices"]}
    assert by_title == {"고정 공지": True, "일반 공지": False}


async def test_perform_sync_maps_submission_type_and_weight_into_notion_payload(monkeypatch):
    """과제 payload — submission_type 한글 라벨 매핑(#12) + 배점 원값 보존(#8).

    - type: 원시 Canvas 코드(online_upload 등) → 한글 라벨(과제(보고서)/에세이/퀴즈/토론),
      미등록 코드/빈 값은 '기타' 폴백.
    - weight: points_possible 를 그대로(예: 100점 → 100). /100 같은 왜곡 없음.
    """
    async def _true(self, *a, **k): return True
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", _true)
    monkeypatch.setattr(sync, "CanvasClient", _FakeCanvasClient)

    fake_courses = [Course(id=1, name="고급프로그래밍 (2150164103)", materials=0)]
    fake_assignments = [
        Assignment(
            id=20, course_id=1, title="보고서 과제", due_at="2026-06-10T00:00:00Z",
            points_possible=100, submission_types=["online_upload"],
        ),
        Assignment(
            id=21, course_id=1, title="에세이 과제", due_at="2026-06-11T00:00:00Z",
            points_possible=30, submission_types=["online_text_entry"],
        ),
        Assignment(
            id=22, course_id=1, title="퀴즈 과제", due_at="2026-06-12T00:00:00Z",
            points_possible=10, submission_types=["online_quiz"],
        ),
        Assignment(
            id=23, course_id=1, title="토론 과제", due_at="2026-06-13T00:00:00Z",
            points_possible=20, submission_types=["discussion_topic"],
        ),
        # 미등록 코드 / submission_types 없음 → '기타' 폴백
        Assignment(
            id=24, course_id=1, title="알수없는 과제", due_at="2026-06-14T00:00:00Z",
            points_possible=0, submission_types=["external_tool"],
        ),
        Assignment(
            id=25, course_id=1, title="타입없는 과제", due_at="2026-06-15T00:00:00Z",
            points_possible=50, submission_types=[],
        ),
    ]

    async def _courses(client): return fake_courses
    async def _deadlines(client, ids): return fake_assignments
    async def _no_notices(client, ids): return []
    monkeypatch.setattr(sync, "list_courses", _courses)
    monkeypatch.setattr(sync, "list_all_deadlines", _deadlines)
    monkeypatch.setattr(sync, "list_all_notices", _no_notices)

    monkeypatch.setattr(settings, "notion_token", "secret_real")
    monkeypatch.setattr(settings, "notion_root_page_id", "rootpage123")
    monkeypatch.setattr(settings, "obsidian_mcp_auth_code", "xxxx")

    captured: dict = {}

    async def _fake_sync_notion(notices, assignments, notion_mcp_url, notion_token):
        captured["assignments"] = assignments
        return {"notices_added": 0, "assignments_added": 0, "failed": 0}

    monkeypatch.setattr(sync, "sync_notion", _fake_sync_notion)

    result = await sync.perform_sync()
    assert result.success is True

    by_title = {a["title"]: a for a in captured["assignments"]}
    # #12 — 한글 라벨 매핑
    assert by_title["보고서 과제"]["type"] == "과제(보고서)"
    assert by_title["에세이 과제"]["type"] == "에세이"
    assert by_title["퀴즈 과제"]["type"] == "퀴즈"
    assert by_title["토론 과제"]["type"] == "토론"
    assert by_title["알수없는 과제"]["type"] == "기타"
    assert by_title["타입없는 과제"]["type"] == "기타"
    # #8 — 배점은 points_possible 원값 그대로 (/100 같은 왜곡 없음)
    assert by_title["보고서 과제"]["weight"] == 100
    assert by_title["에세이 과제"]["weight"] == 30
