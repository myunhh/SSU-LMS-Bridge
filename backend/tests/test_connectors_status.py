"""GET /api/connectors/status — 팀 공유 컨트랙트 B 검증.

검증 항목
---------
- 4개 커넥터(lms/notion/obsidian/llm)를 항상 전부 반환, HTTP 200 고정
- 각 항목은 {id, status, meta, last} 형태 (status ∈ connected|disconnected)
- placeholder('xxxx') 설정은 **네트워크 호출 없이** disconnected
- 개별 판정에서 예외가 나도 200 + disconnected 로 강등 (절대 전파 금지)

실제 네트워크 호출 금지 — _ping_notion / _ping_obsidian 은 모듈 레벨 함수라
monkeypatch 로 대체한다 (autouse fixture `no_network` 가 호출 여부를 기록).
"""
import json
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import connectors
from app.config import settings


@pytest.fixture()
def client():
    """connectors 라우터만 올린 경량 앱 (lifespan/스케줄러 미기동)."""
    app = FastAPI()
    app.include_router(connectors.router, prefix="/api")
    return TestClient(app)


@pytest.fixture(autouse=True)
def base_settings(monkeypatch, tmp_path):
    """모든 커넥터를 '미설정' 기본 상태로 초기화 (실제 .env 값과 격리)."""
    monkeypatch.setattr(settings, "session_cache_path", str(tmp_path / "session_state.json"))
    monkeypatch.setattr(settings, "notion_token", "")
    monkeypatch.setattr(settings, "notion_root_page_id", "")
    monkeypatch.setattr(settings, "obsidian_mcp_auth_code", "")
    monkeypatch.setattr(settings, "llm_api_key", "")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """네트워크 핑을 가짜로 대체하고 호출 횟수를 기록. 기본 응답은 False."""
    calls: list[str] = []

    async def _fake_notion_ping():
        calls.append("notion")
        return False

    async def _fake_obsidian_ping():
        calls.append("obsidian")
        return False

    monkeypatch.setattr(connectors, "_ping_notion", _fake_notion_ping)
    monkeypatch.setattr(connectors, "_ping_obsidian", _fake_obsidian_ping)
    return calls


def _items(resp) -> dict:
    """응답 형태(컨트랙트 B) 공통 검증 후 id → item dict 로 변환."""
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) == 4
    for item in data:
        assert set(item) == {"id", "status", "meta", "last"}
        assert item["status"] in ("connected", "disconnected")
        assert isinstance(item["meta"], str) and item["meta"]
        assert item["last"] is None or isinstance(item["last"], str)
    by_id = {item["id"]: item for item in data}
    assert set(by_id) == {"lms", "notion", "obsidian", "llm"}
    return by_id


def _write_session(saved_at: datetime):
    path = settings.session_cache_abspath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"saved_at": saved_at.isoformat(), "user_info": {"name": "테스트"}}),
        encoding="utf-8",
    )


# ── 형태 / 기본 상태 ──────────────────────────────────────────


def test_all_unconfigured_returns_four_disconnected(client, no_network):
    items = _items(client.get("/api/connectors/status"))
    assert all(i["status"] == "disconnected" for i in items.values())
    assert items["notion"]["meta"] == "NOTION_TOKEN 미설정"
    assert items["obsidian"]["meta"] == "Obsidian 미설정"
    assert items["llm"]["meta"] == "LLM_API_KEY 미설정"
    # 미설정 상태에서는 네트워크 핑 자체가 일어나면 안 된다
    assert no_network == []


# ── LMS ───────────────────────────────────────────────────────


def test_lms_connected_with_fresh_session(client):
    saved = datetime.now() - timedelta(hours=1)
    _write_session(saved)
    items = _items(client.get("/api/connectors/status"))
    assert items["lms"]["status"] == "connected"
    assert items["lms"]["last"] == saved.isoformat()


def test_lms_disconnected_when_session_older_than_7_days(client):
    _write_session(datetime.now() - timedelta(days=8))
    items = _items(client.get("/api/connectors/status"))
    assert items["lms"]["status"] == "disconnected"
    assert "만료" in items["lms"]["meta"]


def test_lms_corrupt_session_file_degrades_not_raises(client):
    """세션 파일이 깨진 JSON 이어도 500 없이 disconnected."""
    path = settings.session_cache_abspath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{깨진 json", encoding="utf-8")
    items = _items(client.get("/api/connectors/status"))
    assert items["lms"]["status"] == "disconnected"


# ── Notion ────────────────────────────────────────────────────


def test_notion_placeholder_disconnected_without_network(client, monkeypatch, no_network):
    """placeholder('xxxx') 값은 실값이 아님 → 핑 호출 없이 disconnected."""
    monkeypatch.setattr(settings, "notion_token", "secret_xxxx")
    monkeypatch.setattr(settings, "notion_root_page_id", "xxxx")
    items = _items(client.get("/api/connectors/status"))
    assert items["notion"]["status"] == "disconnected"
    assert "notion" not in no_network


def test_notion_connected_when_ping_ok(client, monkeypatch, no_network):
    monkeypatch.setattr(settings, "notion_token", "secret_real_token")
    monkeypatch.setattr(settings, "notion_root_page_id", "0123456789abcdef")

    async def _ok():
        no_network.append("notion")
        return True

    monkeypatch.setattr(connectors, "_ping_notion", _ok)
    items = _items(client.get("/api/connectors/status"))
    assert items["notion"]["status"] == "connected"
    assert no_network == ["notion"]


def test_notion_ping_failure_degrades_to_disconnected(client, monkeypatch):
    """핑에서 예외가 나도 200 + disconnected (절대 전파 금지)."""
    monkeypatch.setattr(settings, "notion_token", "secret_real_token")
    monkeypatch.setattr(settings, "notion_root_page_id", "0123456789abcdef")

    async def _boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(connectors, "_ping_notion", _boom)
    items = _items(client.get("/api/connectors/status"))
    assert items["notion"]["status"] == "disconnected"


# ── Obsidian ──────────────────────────────────────────────────


def test_obsidian_placeholder_disconnected_without_network(client, monkeypatch, no_network):
    """placeholder('xxxx') auth_code 는 실값이 아님 → 핑 호출 없이 disconnected (컨트랙트 B)."""
    monkeypatch.setattr(settings, "obsidian_mcp_auth_code", "xxxx")
    items = _items(client.get("/api/connectors/status"))
    assert items["obsidian"]["status"] == "disconnected"
    assert items["obsidian"]["meta"] == "Obsidian 미설정"
    assert "obsidian" not in no_network


def test_obsidian_connected_when_ping_ok_even_with_empty_vault_path(client, monkeypatch, no_network):
    """vault_path 는 보통 빈 문자열이 정상 — auth_code 만으로 판정해야 한다."""
    monkeypatch.setattr(settings, "obsidian_mcp_auth_code", "code123")
    monkeypatch.setattr(settings, "obsidian_vault_path", "")

    async def _ok():
        no_network.append("obsidian")
        return True

    monkeypatch.setattr(connectors, "_ping_obsidian", _ok)
    items = _items(client.get("/api/connectors/status"))
    assert items["obsidian"]["status"] == "connected"
    assert no_network == ["obsidian"]


def test_obsidian_ping_dead_server_disconnected(client, monkeypatch):
    monkeypatch.setattr(settings, "obsidian_mcp_auth_code", "code123")
    items = _items(client.get("/api/connectors/status"))
    # autouse no_network 의 기본 핑이 False 반환 → 응답 없음 처리
    assert items["obsidian"]["status"] == "disconnected"
    assert "응답 없음" in items["obsidian"]["meta"]


@pytest.mark.parametrize(
    "base_url",
    [
        "https://localhost:27124",
        "http://127.0.0.1:27123",
        "https://[::1]:27124",  # urlparse 가 브래킷을 벗겨 '::1' 반환 → 그대로 매칭
    ],
)
def test_obsidian_tls_verify_off_for_loopback(monkeypatch, base_url):
    """루프백 주소에만 자가서명 인증서 예외(verify=False) 허용."""
    monkeypatch.setattr(settings, "obsidian_base_url", base_url)
    assert connectors._obsidian_tls_verify() is False


@pytest.mark.parametrize(
    "base_url",
    [
        "https://10.0.0.5:27124",
        "https://obsidian.example.com:27124",
    ],
)
def test_obsidian_tls_verify_on_for_non_local(monkeypatch, base_url):
    """비로컬 주소는 인증서 검증 강제 (MITM 으로 auth_code 노출 방지)."""
    monkeypatch.setattr(settings, "obsidian_base_url", base_url)
    assert connectors._obsidian_tls_verify() is True


# ── LLM ───────────────────────────────────────────────────────


def test_llm_connected_with_model_in_meta(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "sk-test")
    items = _items(client.get("/api/connectors/status"))
    assert items["llm"]["status"] == "connected"
    assert settings.llm_model in items["llm"]["meta"]
