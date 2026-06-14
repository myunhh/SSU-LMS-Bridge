"""load_session 이 lms·canvas 두 호스트를 모두 방문해 쿠키를 연장하는지 회귀 테스트 (오프라인).

기존 한계: load_session 이 lms.ssu.ac.kr/main.php 만 방문해 Canvas 쿠키
(_normandy_session 등)는 갱신되지 않았다 (#?). 이제 lms 방문 후 canvas 호스트도
best-effort 로 방문한다 — Canvas 방문 실패는 비치명적(반환 계약 불변).

Playwright 실구동 금지 — app.adapter.auth.async_playwright 를 monkeypatch 한다.
"""
import json
from datetime import datetime

import pytest

from app.adapter import auth as auth_mod
from app.adapter.auth import SSULMSAuthPlaywright

# ── Playwright 대역 (goto/save 이벤트 기록) ──────────────────────

class _FakePage:
    def __init__(self, events: list, *, fail_canvas: bool = False, expired: bool = False):
        self._events = events
        self._fail_canvas = fail_canvas
        self._expired = expired
        # main.php 접속 후의 최종 URL (만료 시 SSO 로그인 URL 로 둔갑)
        self.url = "https://lms.ssu.ac.kr/main.php"

    async def goto(self, url: str, **kwargs):
        self._events.append(("goto", url))
        if "canvas" in url:
            if self._fail_canvas:
                raise TimeoutError("canvas 접속 타임아웃")
            self.url = url
            return
        # lms main.php 접속
        self.url = (
            "https://smartid.ssu.ac.kr/login" if self._expired
            else "https://lms.ssu.ac.kr/main.php"
        )


class _FakeContext:
    def __init__(self, page: _FakePage):
        self._page = page

    async def new_page(self):
        return self._page

    async def cookies(self):
        return []

    async def storage_state(self):
        return {"cookies": [], "origins": []}


class _FakeBrowser:
    def __init__(self, page: _FakePage):
        self._page = page

    async def new_context(self, **kwargs):
        return _FakeContext(self._page)

    async def close(self):
        ...


class _FakeChromium:
    def __init__(self, page: _FakePage):
        self._page = page

    async def launch(self, headless: bool = True):
        return _FakeBrowser(self._page)


class _FakePlaywright:
    def __init__(self, page: _FakePage):
        self.chromium = _FakeChromium(page)


class _FakePlaywrightCM:
    def __init__(self, page: _FakePage):
        self._page = page

    async def __aenter__(self):
        return _FakePlaywright(self._page)

    async def __aexit__(self, *exc):
        return False


def _install_fakes(monkeypatch, events: list, *, fail_canvas=False, expired=False):
    page = _FakePage(events, fail_canvas=fail_canvas, expired=expired)
    monkeypatch.setattr(auth_mod, "async_playwright", lambda: _FakePlaywrightCM(page))
    # 2초 sleep 단축
    async def _zero_sleep(_):
        return None
    monkeypatch.setattr(auth_mod.asyncio, "sleep", _zero_sleep)
    # _save_session 기록 (순서 검증용)
    def _fake_save(self, cookies, storage_state):
        events.append(("save",))
    monkeypatch.setattr(SSULMSAuthPlaywright, "_save_session", _fake_save)


@pytest.fixture()
def session_file(tmp_path):
    """user_info.name 이 있는 세션 파일 — _extract_user_info 스킵 (fake page 에 selector 불필요)."""
    p = tmp_path / "session_state.json"
    p.write_text(
        json.dumps({
            "cookies": [],
            "storage_state": {"cookies": [], "origins": []},
            "user_info": {"name": "테스트"},
            "saved_at": datetime.now().isoformat(),
        }),
        encoding="utf-8",
    )
    return p


async def test_load_session_visits_lms_then_canvas_then_saves(monkeypatch, session_file):
    """반환 True; lms main.php → canvas → save 순서로 동작한다."""
    events: list = []
    _install_fakes(monkeypatch, events)
    auth = SSULMSAuthPlaywright(session_file=str(session_file))
    ok = await auth.load_session()
    assert ok is True

    gotos = [e for e in events if e[0] == "goto"]
    assert "main.php" in gotos[0][1]
    assert "canvas.ssu.ac.kr" in gotos[1][1]
    # save 는 canvas goto 뒤에 온다
    assert events.index(("save",)) > events.index(gotos[1])


async def test_load_session_canvas_failure_is_nonfatal(monkeypatch, session_file):
    """canvas goto 가 raise 해도 반환 True + save 호출 (반환 계약 불변)."""
    events: list = []
    _install_fakes(monkeypatch, events, fail_canvas=True)
    auth = SSULMSAuthPlaywright(session_file=str(session_file))
    ok = await auth.load_session()
    assert ok is True
    assert ("save",) in events


async def test_load_session_expired_skips_canvas_and_save(monkeypatch, session_file):
    """main.php 후 SSO 로 튕기면 False — canvas goto·save 둘 다 없음."""
    events: list = []
    _install_fakes(monkeypatch, events, expired=True)
    auth = SSULMSAuthPlaywright(session_file=str(session_file))
    ok = await auth.load_session()
    assert ok is False
    assert all("canvas" not in url for kind, url in
               [(e[0], e[1]) for e in events if e[0] == "goto"])
    assert ("save",) not in events


def test_canvas_url_respects_env_override(monkeypatch):
    """CANVAS_BASE_URL 환경변수가 canvas_url 을 덮어쓴다."""
    monkeypatch.setenv("CANVAS_BASE_URL", "https://canvas.example.com")
    auth = SSULMSAuthPlaywright(session_file="/tmp/_x.json")
    assert auth.canvas_url == "https://canvas.example.com"
