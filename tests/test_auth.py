"""
tests/test_auth.py
──────────────────────────────────────────────────────────────
LMSAuth 단위 테스트.

실제 LMS 연동 테스트는 SKIP 처리. CI 환경에서는 자격증명이 없으므로
인터페이스 및 오류 처리 로직만 확인한다.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lms_bridge.adapter.auth import AuthError, LMSAuth


class TestLMSAuthInit:
    """LMSAuth 초기화 테스트."""

    def test_default_session_path(self):
        """기본 세션 경로가 설정값과 일치해야 한다."""
        from lms_bridge.config import settings
        auth = LMSAuth()
        assert auth._session_path == settings.session_cache_path

    def test_custom_session_path(self, tmp_path):
        """커스텀 세션 경로 지정이 작동해야 한다."""
        custom = tmp_path / "my_session.json"
        auth = LMSAuth(session_path=custom)
        assert auth._session_path == custom

    def test_headless_default(self):
        """기본 headless 설정이 settings 값과 일치해야 한다."""
        from lms_bridge.config import settings
        auth = LMSAuth()
        assert auth._headless == settings.playwright_headless

    def test_headless_override(self):
        """headless 파라미터로 settings 를 덮어쓸 수 있어야 한다."""
        auth = LMSAuth(headless=False)
        assert auth._headless is False

    def test_initial_state_none(self):
        """초기 상태에서 browser/context 는 None 이어야 한다."""
        auth = LMSAuth()
        assert auth._browser is None
        assert auth._context is None
        assert auth._pw is None


class TestLMSAuthErrors:
    """LMSAuth 오류 처리 테스트."""

    @pytest.mark.asyncio
    async def test_new_page_without_login_raises(self):
        """login() 없이 new_page() 호출 시 AuthError 가 발생해야 한다."""
        auth = LMSAuth()
        with pytest.raises(AuthError, match="login()"):
            await auth.new_page()

    @pytest.mark.asyncio
    async def test_get_canvas_token_without_login_raises(self):
        """login() 없이 get_canvas_token() 호출 시 AuthError 가 발생해야 한다."""
        auth = LMSAuth()
        with pytest.raises(AuthError):
            await auth.get_canvas_token()

    @pytest.mark.asyncio
    async def test_close_without_login_is_safe(self):
        """login() 없이 close() 호출해도 에러가 없어야 한다."""
        auth = LMSAuth()
        await auth.close()  # should not raise

    def test_auth_error_is_exception(self):
        assert issubclass(AuthError, Exception)

    def test_auth_error_message(self):
        err = AuthError("test message")
        assert "test message" in str(err)


class TestLMSAuthInterface:
    """LMSAuth 메서드 인터페이스 확인."""

    def test_has_login(self):
        assert callable(getattr(LMSAuth, "login", None))

    def test_has_new_page(self):
        assert callable(getattr(LMSAuth, "new_page", None))

    def test_has_close(self):
        assert callable(getattr(LMSAuth, "close", None))

    def test_has_get_canvas_token(self):
        assert callable(getattr(LMSAuth, "get_canvas_token", None))

    def test_has_get_canvas_cookies(self):
        assert callable(getattr(LMSAuth, "get_canvas_cookies", None))

    def test_has_context_manager(self):
        assert hasattr(LMSAuth, "__aenter__")
        assert hasattr(LMSAuth, "__aexit__")


class TestLMSAuthSessionCache:
    """세션 캐시 관련 테스트."""

    @pytest.mark.asyncio
    async def test_save_session_creates_file(self, tmp_path):
        """_save_session() 이 파일을 생성해야 한다."""
        import json
        session_path = tmp_path / "session.json"
        auth = LMSAuth(session_path=session_path)

        # _context mock
        mock_context = AsyncMock()
        mock_context.storage_state.return_value = {
            "cookies": [{"name": "test", "value": "val"}],
            "origins": [],
        }
        auth._context = mock_context

        await auth._save_session()
        assert session_path.exists()
        data = json.loads(session_path.read_text())
        assert "cookies" in data

    def test_session_path_not_exists_initially(self, tmp_path):
        """존재하지 않는 세션 경로는 is_session_valid() 분기에서 처리된다."""
        session_path = tmp_path / "nonexistent.json"
        auth = LMSAuth(session_path=session_path)
        assert not session_path.exists()


# ── 실제 LMS 연동 테스트 (CI 환경에서 SKIP) ─────────────────────────────────

class TestLMSAuthReal:
    """실제 LMS 연동 테스트. 학번/비밀번호가 있을 때만 실행."""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="실제 LMS 자격증명 필요 — 로컬에서만 실행")
    async def test_login_success(self):
        """실제 SSO 로그인이 성공해야 한다."""
        auth = LMSAuth()
        await auth.login()
        assert auth._context is not None
        await auth.close()

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="실제 LMS 자격증명 필요 — 로컬에서만 실행")
    async def test_session_is_valid_after_login(self):
        """로그인 후 세션이 유효해야 한다."""
        async with LMSAuth() as auth:
            valid = await auth._is_session_valid()
            assert valid is True

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="실제 LMS 자격증명 필요 — 로컬에서만 실행")
    async def test_canvas_token_obtained(self):
        """canvas API 토큰을 가져올 수 있어야 한다."""
        async with LMSAuth() as auth:
            token = await auth.get_canvas_token()
            assert token
            assert token.startswith("eyJ")  # JWT 형식
