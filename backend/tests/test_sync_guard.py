"""perform_sync 동시 실행 가드(409) 회귀 테스트 (오프라인).

가드는 perform_sync 진입 직후 — 세션 파일 확인·첫 await 이전 — 에 동작하므로
settings/세션 파일 격리나 네트워크/Playwright mock 없이 검증할 수 있다.
"""
import pytest
from fastapi import HTTPException

from app.api.routes import sync


async def test_perform_sync_raises_409_when_already_running():
    """(a) running=True 면 SyncSessionError(409) 를 raise 한다."""
    sync._state["running"] = True
    try:
        with pytest.raises(sync.SyncSessionError) as ei:
            await sync.perform_sync()
        assert ei.value.status_code == 409
        assert "이미 진행 중" in ei.value.detail
    finally:
        sync._state["running"] = False


async def test_guard_preserves_running_flag_of_inflight_sync():
    """(b) 가드 raise 가 진행 중인 다른 실행의 running 플래그를 되돌리면 안 된다."""
    sync._state["running"] = True
    try:
        with pytest.raises(sync.SyncSessionError):
            await sync.perform_sync()
        assert sync._state["running"] is True
    finally:
        sync._state["running"] = False


async def test_trigger_sync_converts_guard_to_http_409():
    """(c) POST /api/sync 핸들러는 가드를 HTTPException(409) 으로 변환한다."""
    sync._state["running"] = True
    try:
        with pytest.raises(HTTPException) as ei:
            await sync.trigger_sync()
        assert ei.value.status_code == 409
    finally:
        sync._state["running"] = False
