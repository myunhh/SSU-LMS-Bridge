"""GET /api/sync/status 응답 스키마 회귀 테스트 (오프라인).

connectors 페이지의 '예약 동기화' 카드가 syncHour 를 읽으므로, 상태 응답이
{ running, lastSyncAt, syncHour } 를 항상 포함해야 한다. _state·settings 만 읽으므로
네트워크/Playwright 불필요. (라우트 함수 직접 await — test_sync_guard 패턴)
"""
from datetime import datetime

from app.api.routes import sync


async def test_sync_status_includes_required_keys():
    """running(bool)/lastSyncAt(None 초기)/syncHour 키를 모두 포함한다."""
    saved = dict(sync._state)
    sync._state["running"] = False
    sync._state["last_sync_at"] = None
    try:
        result = await sync.sync_status()
    finally:
        sync._state.clear()
        sync._state.update(saved)

    assert result["running"] is False
    assert result["lastSyncAt"] is None
    assert "syncHour" in result
    assert isinstance(result["syncHour"], int)


async def test_sync_status_reflects_settings_sync_hour(monkeypatch):
    """syncHour 는 settings.sync_hour 를 반영한다."""
    monkeypatch.setattr(sync.settings, "sync_hour", 7)
    result = await sync.sync_status()
    assert result["syncHour"] == 7


async def test_sync_status_lastsyncat_isoformat():
    """last_sync_at(datetime) 은 isoformat 문자열로 직렬화된다."""
    saved = dict(sync._state)
    moment = datetime(2026, 6, 13, 4, 0, 0)
    sync._state["last_sync_at"] = moment
    try:
        result = await sync.sync_status()
    finally:
        sync._state.clear()
        sync._state.update(saved)
    assert result["lastSyncAt"] == moment.isoformat()
