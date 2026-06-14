"""예약 세션 갱신 작업(session_refresh) 등록 + 래퍼 동작 회귀 테스트 (오프라인).

기존 한계: session_keeper_loop 가 FastAPI 어디에도 연결되지 않아 nextRefreshIn 이
실재하지 않는 주기 갱신을 전제했다. 이제 main.py 가 IntervalTrigger 로 등록한다.

- 등록: scheduler 에 session_refresh 잡이 SESSION_REFRESH_INTERVAL 주기로 존재
- 래퍼(run_scheduled_session_refresh): 세션 없음/sync 진행 중이면 load_session 미호출,
  False/예외여도 전파하지 않음, 정상 경로에서만 1회 호출
"""
import json
from datetime import datetime

import pytest
from apscheduler.triggers.interval import IntervalTrigger
from fastapi.testclient import TestClient

from app.adapter.auth import SSULMSAuthPlaywright
from app.api.routes import lms, sync
from app.api.session_meta import SESSION_REFRESH_INTERVAL
from app.config import settings

# ── 등록 테스트 ──────────────────────────────────────────────

def test_session_refresh_job_registered():
    """lifespan 구동 시 session_refresh 잡이 IntervalTrigger 로 등록된다."""
    from app import main

    with TestClient(main.app):
        job = main.scheduler.get_job("session_refresh")
        assert job is not None
        assert isinstance(job.trigger, IntervalTrigger)
        assert job.trigger.interval.total_seconds() == SESSION_REFRESH_INTERVAL


# ── 래퍼 단위 테스트 ─────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_session_file(monkeypatch, tmp_path):
    """실제 .cache/session_state.json 과 격리 (test_lms_routes 패턴)."""
    monkeypatch.setattr(settings, "session_cache_path", str(tmp_path / "session_state.json"))


def _write_session():
    path = settings.session_cache_abspath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"saved_at": datetime.now().isoformat(), "user_info": {"name": "테스트"}}),
        encoding="utf-8",
    )


class _Spy:
    def __init__(self, result=True, raises=None):
        self.calls = 0
        self._result = result
        self._raises = raises

    async def __call__(self, *args, **kwargs):
        self.calls += 1
        if self._raises:
            raise self._raises
        return self._result


async def test_refresh_skips_when_no_session_file(monkeypatch):
    """세션 파일 없음 → load_session 미호출, 예외 없음."""
    spy = _Spy()
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", spy)
    await lms.run_scheduled_session_refresh()
    assert spy.calls == 0


async def test_refresh_skips_when_sync_running(monkeypatch):
    """sync 진행 중 → load_session 미호출 (세션 파일 동시 갱신 회피)."""
    _write_session()
    spy = _Spy()
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", spy)
    sync._state["running"] = True
    try:
        await lms.run_scheduled_session_refresh()
    finally:
        sync._state["running"] = False
    assert spy.calls == 0


async def test_refresh_swallows_false(monkeypatch):
    """load_session False(만료) — 예외 전파 없이 종료."""
    _write_session()
    spy = _Spy(result=False)
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", spy)
    await lms.run_scheduled_session_refresh()  # raise 하지 않아야 함
    assert spy.calls == 1


async def test_refresh_swallows_exception(monkeypatch):
    """load_session 인프라 예외 — 삼키고 종료 (예약 작업이라 밖으로 안 던짐)."""
    _write_session()
    spy = _Spy(raises=RuntimeError("chromium 없음"))
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", spy)
    await lms.run_scheduled_session_refresh()  # raise 하지 않아야 함
    assert spy.calls == 1


async def test_refresh_calls_load_session_on_happy_path(monkeypatch):
    """세션 존재 + sync 미진행 → load_session 정확히 1회 호출."""
    _write_session()
    spy = _Spy(result=True)
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", spy)
    await lms.run_scheduled_session_refresh()
    assert spy.calls == 1
