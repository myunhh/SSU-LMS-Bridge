"""LMS 인증/동기화 라우트 — 자격증명 실패 vs 인프라 오류 구분 회귀 테스트 (오프라인).

auth.py 의 포괄 except 가 인프라 오류(Chromium 미설치, 네트워크 단절 등)를
자격증명 오류(401)로 둔갑시키던 문제의 회귀 방지:
    - login/load_session 이 False  → 401 (자격증명 불일치 / 세션 만료)
    - login/load_session 이 raise  → 502 (lms 라우트) / 503 (sync 라우트)

Playwright 실구동 금지 — SSULMSAuthPlaywright 의 메서드를 monkeypatch 한다
(test_connectors_status.py 의 경량 앱 + settings 격리 패턴).
"""
import json
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapter.auth import SSULMSAuthPlaywright
from app.api.routes import lms, sync
from app.config import settings


@pytest.fixture()
def client():
    """lms + sync 라우터만 올린 경량 앱 (lifespan/스케줄러 미기동)."""
    app = FastAPI()
    app.include_router(lms.router, prefix="/api")
    app.include_router(sync.router, prefix="/api")
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolated_session_file(monkeypatch, tmp_path):
    """실제 .cache/session_state.json 과 격리."""
    monkeypatch.setattr(settings, "session_cache_path", str(tmp_path / "session_state.json"))


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """각 테스트가 깨끗한 rate limit 상태에서 시작하도록 모듈 카운터 초기화 (#6)."""
    lms.reset_login_rate_limit()
    yield
    lms.reset_login_rate_limit()


def _write_session():
    path = settings.session_cache_abspath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"saved_at": datetime.now().isoformat(), "user_info": {"name": "테스트"}}),
        encoding="utf-8",
    )


async def _false(self, *args, **kwargs):
    return False


async def _boom(self, *args, **kwargs):
    raise RuntimeError("chromium 실행 실패 (playwright install 누락)")


# ── POST /api/lms/login ───────────────────────────────────────


def test_login_false_returns_401(client, monkeypatch):
    """자격증명 불일치(False)는 기존대로 401."""
    monkeypatch.setattr(SSULMSAuthPlaywright, "login", _false)
    resp = client.post("/api/lms/login", json={"studentId": "20201234", "password": "pw"})
    assert resp.status_code == 401
    assert "일치하지 않습니다" in resp.json()["detail"]


def test_login_infra_error_returns_502(client, monkeypatch):
    """인프라 오류(raise)는 401 이 아니라 502 — 사용자가 비밀번호를 의심하지 않게."""
    monkeypatch.setattr(SSULMSAuthPlaywright, "login", _boom)
    resp = client.post("/api/lms/login", json={"studentId": "20201234", "password": "pw"})
    assert resp.status_code == 502
    assert "서버 오류" in resp.json()["detail"]


# ── POST /api/lms/session/refresh ─────────────────────────────


def test_refresh_no_session_file_returns_401(client):
    resp = client.post("/api/lms/session/refresh")
    assert resp.status_code == 401


def test_refresh_false_returns_401(client, monkeypatch):
    """세션 만료(False)는 기존대로 401."""
    _write_session()
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", _false)
    resp = client.post("/api/lms/session/refresh")
    assert resp.status_code == 401


def test_refresh_infra_error_returns_502(client, monkeypatch):
    _write_session()
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", _boom)
    resp = client.post("/api/lms/session/refresh")
    assert resp.status_code == 502
    assert "서버 오류" in resp.json()["detail"]


# ── POST /api/sync (세션 검증 단계) ────────────────────────────


def test_sync_load_session_false_returns_401(client, monkeypatch):
    """세션 만료(False) → 401 '세션 만료' 유지."""
    _write_session()
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", _false)
    resp = client.post("/api/sync")
    assert resp.status_code == 401
    assert "만료" in resp.json()["detail"]


def test_sync_load_session_infra_error_returns_503(client, monkeypatch):
    """인프라 오류(raise)는 광역 except 에 삼켜지지 않고 503 으로 응답해야 한다."""
    _write_session()
    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", _boom)
    resp = client.post("/api/sync")
    assert resp.status_code == 503
    assert "서버 오류" in resp.json()["detail"]
    # finally 에서 running 플래그가 정리됐는지 (다음 동기화가 409 로 막히면 안 됨)
    assert sync._state["running"] is False


# ── POST /api/lms/login rate limit (#6) ───────────────────────


def _login(client, sid="20201234"):
    return client.post("/api/lms/login", json={"studentId": sid, "password": "pw"})


def test_login_rate_limit_window_returns_429(client, monkeypatch):
    """윈도 내 허용 횟수(max_attempts) 초과 시 → 429.

    login 을 False(401) 로 두면 자격증명 실패로 횟수만 채워진다. 단 backoff 가
    먼저 발동하지 않도록 failure_threshold 를 윈도 상한보다 높게 둔다.
    """
    monkeypatch.setattr(SSULMSAuthPlaywright, "login", _false)
    monkeypatch.setattr(settings, "login_rate_limit_max_attempts", 3)
    monkeypatch.setattr(settings, "login_rate_limit_window_seconds", 60)
    monkeypatch.setattr(settings, "login_rate_limit_failure_threshold", 100)

    # 허용 횟수(3회)까지는 401 (rate limit 통과 후 자격증명 실패).
    for _ in range(3):
        assert _login(client).status_code == 401
    # 4회째 — 윈도 상한 초과 → 429.
    resp = _login(client)
    assert resp.status_code == 429
    assert "너무 많습니다" in resp.json()["detail"]
    assert "Retry-After" in resp.headers


def test_login_rate_limit_per_student_isolated(client, monkeypatch):
    """학번이 다르면 키가 분리되어 한쪽 초과가 다른쪽을 막지 않는다."""
    monkeypatch.setattr(SSULMSAuthPlaywright, "login", _false)
    monkeypatch.setattr(settings, "login_rate_limit_max_attempts", 2)
    monkeypatch.setattr(settings, "login_rate_limit_failure_threshold", 100)

    assert _login(client, "A").status_code == 401
    assert _login(client, "A").status_code == 401
    assert _login(client, "A").status_code == 429  # A 초과
    # 다른 학번 B 는 아직 카운터가 비어 있어 통과.
    assert _login(client, "B").status_code == 401


def test_login_backoff_after_consecutive_failures(client, monkeypatch):
    """연속 실패가 failure_threshold 에 도달하면 backoff 로 429 (윈도와 별개)."""
    monkeypatch.setattr(SSULMSAuthPlaywright, "login", _false)
    # 윈도 상한은 넉넉히, 연속 실패 임계만 낮춰 backoff 경로를 정확히 친다.
    monkeypatch.setattr(settings, "login_rate_limit_max_attempts", 100)
    monkeypatch.setattr(settings, "login_rate_limit_failure_threshold", 3)
    monkeypatch.setattr(settings, "login_rate_limit_backoff_seconds", 300)

    for _ in range(3):
        assert _login(client).status_code == 401  # 3회 연속 실패 → backoff 발동
    # 이후 시도는 backoff 차단 → 429.
    resp = _login(client)
    assert resp.status_code == 429
    assert "너무 많습니다" in resp.json()["detail"]


def test_login_success_resets_failure_counter(client, monkeypatch):
    """성공하면 연속 실패 카운터가 초기화돼 backoff 가 풀린다."""
    monkeypatch.setattr(settings, "login_rate_limit_max_attempts", 100)
    monkeypatch.setattr(settings, "login_rate_limit_failure_threshold", 3)

    # 실패 2회 누적 (임계 3 미만 → 아직 backoff 안 됨).
    monkeypatch.setattr(SSULMSAuthPlaywright, "login", _false)
    assert _login(client).status_code == 401
    assert _login(client).status_code == 401

    # 성공 1회 → 카운터 리셋.
    async def _true(self, *args, **kwargs):
        self.user_info = {"name": "테스트"}
        return True

    monkeypatch.setattr(SSULMSAuthPlaywright, "login", _true)
    assert _login(client).status_code == 200

    # 다시 실패해도 카운터가 1부터라 임계(3) 전까지 backoff 가 안 걸린다.
    monkeypatch.setattr(SSULMSAuthPlaywright, "login", _false)
    assert _login(client).status_code == 401
    assert _login(client).status_code == 401  # 누적 2 — 여전히 401, 429 아님


def test_login_infra_error_does_not_trigger_backoff(client, monkeypatch):
    """인프라 오류(502)는 서버 측 문제이므로 연속 실패 backoff 에 반영 안 함."""
    monkeypatch.setattr(SSULMSAuthPlaywright, "login", _boom)
    monkeypatch.setattr(settings, "login_rate_limit_max_attempts", 100)
    monkeypatch.setattr(settings, "login_rate_limit_failure_threshold", 2)

    # 502 가 여러 번 나도 backoff(429) 로 바뀌지 않는다 — 계속 502.
    for _ in range(4):
        assert _login(client).status_code == 502
