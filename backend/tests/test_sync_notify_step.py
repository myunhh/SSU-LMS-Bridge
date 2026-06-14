"""perform_sync step5 (이메일 알림 분기) 회귀 테스트 — 전부 오프라인 (#14).

sync.py step5 는 방금 수집한 과제로 '마감 임박' 디제스트만 발송한다(추가 네트워크
호출 0회, 신규 공지 diff 는 주기 스캔 job 담당). 이 분기가 미커버였다.

검증 항목
---------
- smtp_configured()=True 일 때만 분기 진입, upcoming_deadlines 가 **assign_payload**
  (perform_sync 가 조립한 과제 dict 리스트)로 호출되는지 — payload 단일 출처 확인.
- within_hours 인자가 settings.notify_deadline_hours 로 전달되는지.
- send_email 이 예외를 던져도 perform_sync 가 SyncResult 를 정상 반환(예외 미전파).
  알림은 부가 기능이라 본 sync 흐름을 깨면 안 된다는 계약(step5 try/except)을 못 박는다.
- send_email 호출 인자(render_digest 가 만든 subject/body)가 실제로 전달되는지.
- smtp 미설정이면 분기를 아예 건너뛰는지(upcoming_deadlines/send_email 미호출).

test_sync_payload.py 의 격리 패턴(가짜 세션 파일 + _state 복원 + 가짜 CanvasClient)
재사용. Playwright/네트워크 없음.
"""
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.adapter.auth import SSULMSAuthPlaywright
from app.api.routes import sync
from app.config import settings
from app.models import Assignment, Course


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


def _iso(dt: datetime) -> str:
    """aware datetime → Canvas 스타일 'Z' 접미 ISO 문자열."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _patch_lms_collection(monkeypatch, *, courses, assignments=None, notices=None):
    """세션 검증/CanvasClient/어댑터를 가짜로 — Playwright·네트워크 차단."""
    async def _true(self, *a, **k): return True
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", _true)
    monkeypatch.setattr(sync, "CanvasClient", _FakeCanvasClient)

    async def _courses(client): return courses
    async def _deadlines(client, ids): return assignments or []
    async def _notices(client, ids): return notices or []
    monkeypatch.setattr(sync, "list_courses", _courses)
    monkeypatch.setattr(sync, "list_all_deadlines", _deadlines)
    monkeypatch.setattr(sync, "list_all_notices", _notices)

    # Notion·Obsidian push 분기는 이 테스트 범위 밖 → 미설정 고정으로 차단.
    monkeypatch.setattr(settings, "notion_token", "xxxx")
    monkeypatch.setattr(settings, "notion_root_page_id", "xxxx")
    monkeypatch.setattr(settings, "obsidian_mcp_auth_code", "xxxx")


async def test_step5_calls_upcoming_deadlines_with_assign_payload(monkeypatch):
    """step5 분기 — upcoming_deadlines 가 perform_sync 의 assign_payload 로 호출되고
    within_hours=settings.notify_deadline_hours 가 전달되는지, send_email 인자도 확인."""
    # 마감 임박(곧 마감, 미제출) 과제 하나 → 디제스트가 실제로 생성되도록.
    now = datetime.now(UTC)
    soon = _iso(now + timedelta(hours=3))
    fake_courses = [Course(id=1, name="고급프로그래밍 (2150164103)", materials=0)]
    fake_assignments = [
        Assignment(
            id=20, course_id=1, title="임박 과제", due_at=soon,
            points_possible=100, submission_types=["online_upload"], submitted=False,
        ),
    ]
    _patch_lms_collection(monkeypatch, courses=fake_courses, assignments=fake_assignments)

    # SMTP 설정됨 → step5 진입. notify_deadline_hours 도 비표준값으로 바꿔 전달 확인.
    monkeypatch.setattr(sync.notify_service, "smtp_configured", lambda: True)
    monkeypatch.setattr(settings, "notify_deadline_hours", 48)

    captured: dict = {}
    real_upcoming = sync.notify_service.upcoming_deadlines

    def _spy_upcoming(assignments, *, within_hours=24, now=None):
        captured["assignments"] = assignments
        captured["within_hours"] = within_hours
        # 실제 로직에 위임해 디제스트가 정상 생성되게 한다.
        return real_upcoming(assignments, within_hours=within_hours, now=now)

    monkeypatch.setattr(sync.notify_service, "upcoming_deadlines", _spy_upcoming)

    sent: dict = {}

    def _spy_send(subject, body):
        sent["subject"] = subject
        sent["body"] = body
        return True

    monkeypatch.setattr(sync.notify_service, "send_email", _spy_send)

    result = await sync.perform_sync()

    assert result.success is True
    # (a) upcoming_deadlines 가 assign_payload(과제 dict 리스트)로 호출됐다.
    assert "assignments" in captured
    payload = captured["assignments"]
    assert isinstance(payload, list) and len(payload) == 1
    item = payload[0]
    assert isinstance(item, dict)
    # perform_sync 의 assign_payload 형태(snake_case 키, 한글 라벨 매핑) 확인
    assert item["title"] == "임박 과제"
    assert item["course_name"] == "고급프로그래밍 (2150164103)"
    assert item["due"] == soon
    assert item["type"] == "과제(보고서)"
    assert item["weight"] == 100
    assert item["submitted"] is False
    # within_hours 가 settings.notify_deadline_hours 로 전달됐다.
    assert captured["within_hours"] == 48
    # send_email 이 render_digest 결과(제목/본문)로 호출됐다.
    assert "임박 과제" in sent["body"]
    assert "마감 임박" in sent["subject"]


async def test_step5_send_email_exception_does_not_break_sync(monkeypatch):
    """send_email 이 예외를 던져도 perform_sync 가 SyncResult 를 정상 반환(예외 미전파).

    알림은 부가 기능 — 발송 실패가 본 sync 흐름을 깨면 안 된다(step5 try/except 계약).
    """
    now = datetime.now(UTC)
    soon = _iso(now + timedelta(hours=2))
    fake_courses = [Course(id=1, name="DB설계 (2150164104)", materials=0)]
    fake_assignments = [
        Assignment(
            id=30, course_id=1, title="발송실패 유발 과제", due_at=soon,
            points_possible=50, submission_types=["online_text_entry"], submitted=False,
        ),
    ]
    _patch_lms_collection(monkeypatch, courses=fake_courses, assignments=fake_assignments)

    monkeypatch.setattr(sync.notify_service, "smtp_configured", lambda: True)

    calls = {"send": 0}

    def _boom(subject, body):
        calls["send"] += 1
        raise RuntimeError("SMTP 연결 실패(테스트)")

    monkeypatch.setattr(sync.notify_service, "send_email", _boom)

    # 예외가 perform_sync 밖으로 전파되면 여기서 터진다.
    result = await sync.perform_sync()

    # SyncResult 정상 반환 + 알림 실패는 errors 에 섞이지 않는다(부가 기능, 경고 로그만).
    assert calls["send"] == 1  # 실제로 발송이 시도됐다(예외 발생 경로)
    assert result.success is True
    assert result.errors == []
    assert result.assignments == 1
    # 동시 실행 가드 플래그가 finally 에서 해제됐는지(예외 경로에서도)
    assert sync._state["running"] is False


async def test_step5_skipped_when_smtp_unconfigured(monkeypatch):
    """SMTP 미설정이면 step5 분기를 통째로 건너뛴다 — upcoming_deadlines/send_email 미호출."""
    now = datetime.now(UTC)
    soon = _iso(now + timedelta(hours=1))
    fake_courses = [Course(id=1, name="자료구조 (2150164105)", materials=0)]
    fake_assignments = [
        Assignment(
            id=40, course_id=1, title="임박 과제", due_at=soon,
            points_possible=10, submission_types=["online_quiz"], submitted=False,
        ),
    ]
    _patch_lms_collection(monkeypatch, courses=fake_courses, assignments=fake_assignments)

    # 미설정 → 분기 진입 안 함.
    monkeypatch.setattr(sync.notify_service, "smtp_configured", lambda: False)

    touched = {"upcoming": 0, "send": 0}

    def _spy_upcoming(*a, **k):
        touched["upcoming"] += 1
        return []

    def _spy_send(*a, **k):
        touched["send"] += 1
        return True

    monkeypatch.setattr(sync.notify_service, "upcoming_deadlines", _spy_upcoming)
    monkeypatch.setattr(sync.notify_service, "send_email", _spy_send)

    result = await sync.perform_sync()

    assert result.success is True
    assert touched == {"upcoming": 0, "send": 0}
