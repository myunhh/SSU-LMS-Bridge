"""POST /api/connectors/config — .env 화이트리스트 upsert 회귀 테스트 (오프라인).

가입 마법사가 입력한 Notion/Obsidian/LLM 키를 루트 .env 에 안전하게 저장한다.
- 화이트리스트 외 키는 422, 값 검증(빈값/개행/placeholder)은 400
- 기존 .env 의 주석·무관 줄 보존, 기존 키 in-place 교체, 누락 키 append
- llm_api_key 만 라이브 적용(settings), notion/obsidian 은 재시작 후 반영
- 시크릿 원문은 응답에 에코하지 않는다

실제 루트 .env 격리 — _env_path 를 tmp_path 로 monkeypatch (autouse).
네트워크 핑은 가짜로 교체 (status 라우트 병행 검증용).
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import connectors
from app.config import settings


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(connectors.router, prefix="/api")
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """실제 루트 .env 와 격리 + 커넥터 설정 초기화."""
    env_path = tmp_path / ".env"
    monkeypatch.setattr(connectors, "_env_path", lambda: env_path)
    monkeypatch.setattr(settings, "notion_token", "")
    monkeypatch.setattr(settings, "notion_root_page_id", "")
    monkeypatch.setattr(settings, "obsidian_mcp_auth_code", "")
    monkeypatch.setattr(settings, "obsidian_base_url", "http://localhost:27124")
    monkeypatch.setattr(settings, "obsidian_vault_path", "")
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "llm_model", "gemini-2.5-flash")
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "session_cache_path", str(tmp_path / "session_state.json"))
    return env_path


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    async def _f():
        return True
    monkeypatch.setattr(connectors, "_ping_notion", _f)
    monkeypatch.setattr(connectors, "_ping_obsidian", _f)


# ── 저장 ──────────────────────────────────────────────────────

def test_creates_env_file_when_absent(client, isolated_env):
    assert not isolated_env.exists()
    resp = client.post("/api/connectors/config", json={"notion_token": "secret_real"})
    assert resp.status_code == 200
    assert isolated_env.exists()
    assert "NOTION_TOKEN=secret_real" in isolated_env.read_text("utf-8")


def test_replaces_existing_key_and_preserves_others(client, isolated_env):
    isolated_env.write_text(
        "# 주석 줄\nLMS_USERNAME=20201234\nNOTION_TOKEN=old_value\nUNRELATED=keepme\n",
        encoding="utf-8",
    )
    resp = client.post("/api/connectors/config", json={"notion_token": "new_value"})
    assert resp.status_code == 200
    text = isolated_env.read_text("utf-8")
    assert "NOTION_TOKEN=new_value" in text
    assert "NOTION_TOKEN=old_value" not in text
    assert "# 주석 줄" in text
    assert "LMS_USERNAME=20201234" in text
    assert "UNRELATED=keepme" in text


def test_appends_missing_key(client, isolated_env):
    isolated_env.write_text("LMS_USERNAME=20201234\n", encoding="utf-8")
    resp = client.post("/api/connectors/config", json={"llm_api_key": "aizaKey"})
    assert resp.status_code == 200
    text = isolated_env.read_text("utf-8")
    assert "LMS_USERNAME=20201234" in text
    assert "LLM_API_KEY=aizaKey" in text


def test_saves_all_four_keys(client, isolated_env):
    resp = client.post("/api/connectors/config", json={
        "notion_token": "secret_t",
        "notion_root_page_id": "rootpage",
        "obsidian_mcp_auth_code": "obscode",
        "llm_api_key": "aizaKey",
    })
    assert resp.status_code == 200
    text = isolated_env.read_text("utf-8")
    for line in ("NOTION_TOKEN=secret_t", "NOTION_ROOT_PAGE_ID=rootpage",
                 "OBSIDIAN_MCP_AUTH_CODE=obscode", "LLM_API_KEY=aizaKey"):
        assert line in text


# ── #10 화이트리스트 확장 (obsidian_base_url / obsidian_vault_path / llm_provider / llm_model) ──

def test_saves_new_whitelist_keys(client, isolated_env):
    """#6 프론트가 보내는 4개 신규 키가 .env 에 정확한 대문자 키로 기록된다."""
    resp = client.post("/api/connectors/config", json={
        "obsidian_base_url": "http://localhost:27123",
        "obsidian_vault_path": "LMS",
        "llm_provider": "anthropic",
        "llm_model": "claude-haiku-4-5",
    })
    assert resp.status_code == 200
    text = isolated_env.read_text("utf-8")
    for line in ("OBSIDIAN_BASE_URL=http://localhost:27123",
                 "OBSIDIAN_VAULT_PATH=LMS",
                 "LLM_PROVIDER=anthropic",
                 "LLM_MODEL=claude-haiku-4-5"):
        assert line in text


def test_obsidian_vault_path_empty_string_allowed(client, isolated_env):
    """obsidian_vault_path 는 빈 문자열("")이 정상값(vault 루트) — 400 아님, 빈값으로 기록."""
    resp = client.post("/api/connectors/config", json={"obsidian_vault_path": ""})
    assert resp.status_code == 200
    text = isolated_env.read_text("utf-8")
    assert "OBSIDIAN_VAULT_PATH=" in text
    # 빈값이 기록됐는지: 줄이 정확히 "OBSIDIAN_VAULT_PATH=" 인지 확인
    assert any(ln == "OBSIDIAN_VAULT_PATH=" for ln in text.splitlines())
    assert resp.json()["saved"] == ["OBSIDIAN_VAULT_PATH"]


def test_other_new_key_blank_still_returns_400(client):
    """obsidian_vault_path 외 신규 키는 여전히 빈값 거부 (빈값 허용이 번지지 않음)."""
    resp = client.post("/api/connectors/config", json={"obsidian_base_url": "   "})
    assert resp.status_code == 400


def test_new_key_placeholder_returns_400(client):
    """신규 키도 placeholder('xxxx') 검증 대상 (obsidian_vault_path 제외)."""
    resp = client.post("/api/connectors/config", json={"llm_model": "model_xxxx"})
    assert resp.status_code == 400


def test_obsidian_keys_require_restart(client):
    """OBSIDIAN_BASE_URL / OBSIDIAN_VAULT_PATH 변경은 재시작 필요 (마운트 부팅 고정)."""
    resp = client.post("/api/connectors/config", json={"obsidian_base_url": "http://localhost:27123"})
    assert resp.json()["restart_required"] is True
    resp2 = client.post("/api/connectors/config", json={"obsidian_vault_path": "LMS"})
    assert resp2.json()["restart_required"] is True


def test_llm_provider_model_applied_live(client):
    """llm_provider / llm_model POST → settings 즉시 반영 + status meta 갱신."""
    resp = client.post("/api/connectors/config", json={
        "llm_provider": "anthropic",
        "llm_model": "claude-haiku-4-5",
    })
    assert resp.status_code == 200
    assert resp.json()["restart_required"] is False
    assert set(resp.json()["applied_now"]) == {"LLM_PROVIDER", "LLM_MODEL"}
    assert settings.llm_provider == "anthropic"
    assert settings.llm_model == "claude-haiku-4-5"


# ── 거부 ──────────────────────────────────────────────────────

def test_empty_body_returns_400(client):
    resp = client.post("/api/connectors/config", json={})
    assert resp.status_code == 400


def test_unknown_key_returns_422(client):
    resp = client.post("/api/connectors/config", json={"unknown_key": "x"})
    assert resp.status_code == 422


def test_newline_in_value_returns_400(client):
    resp = client.post("/api/connectors/config", json={"notion_token": "abc\ndef"})
    assert resp.status_code == 400


def test_placeholder_value_returns_400(client):
    resp = client.post("/api/connectors/config", json={"notion_token": "secret_xxxx"})
    assert resp.status_code == 400


def test_blank_value_returns_400(client):
    resp = client.post("/api/connectors/config", json={"notion_token": "   "})
    assert resp.status_code == 400


# ── restart_required / 라이브 적용 ────────────────────────────

def test_restart_required_true_for_notion(client):
    resp = client.post("/api/connectors/config", json={"notion_token": "secret_t"})
    assert resp.json()["restart_required"] is True


def test_restart_required_false_for_llm_only(client):
    resp = client.post("/api/connectors/config", json={"llm_api_key": "aizaKey"})
    assert resp.json()["restart_required"] is False


def test_llm_key_applied_live(client):
    """llm_api_key POST → settings 즉시 반영 + status 의 llm connected."""
    resp = client.post("/api/connectors/config", json={"llm_api_key": "aizaKey"})
    assert resp.status_code == 200
    assert settings.llm_api_key == "aizaKey"
    status = client.get("/api/connectors/status").json()
    llm = next(i for i in status if i["id"] == "llm")
    assert llm["status"] == "connected"


def test_notion_key_not_applied_live(client):
    """notion_token POST → settings 불변(라이브 미적용) + status 는 disconnected 유지."""
    resp = client.post("/api/connectors/config", json={"notion_token": "secret_t"})
    assert resp.status_code == 200
    assert settings.notion_token == ""  # 라이브 미적용
    status = client.get("/api/connectors/status").json()
    notion = next(i for i in status if i["id"] == "notion")
    assert notion["status"] == "disconnected"


def test_response_does_not_echo_secret(client):
    resp = client.post("/api/connectors/config", json={"notion_token": "secret_t"})
    body = resp.text
    assert "secret_t" not in body
    assert "NOTION_TOKEN" in resp.json()["saved"]
