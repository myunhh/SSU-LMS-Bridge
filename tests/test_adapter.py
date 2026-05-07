"""
tests/test_adapter.py
──────────────────────────────────────────────────────────────
LMS Adapter 단위 테스트 (Day 5-7 및 2주차에 채워질 예정).

현재는 인터페이스 존재 여부와 기본 구조만 확인한다.
실제 LMS 연동 테스트는 Day 5-7 에 구현한다.
"""

from __future__ import annotations

import pytest

from lms_bridge.adapter.auth import AuthError, LMSAuth
from lms_bridge.adapter.courses import list_courses


class TestLMSAuthInterface:
    """LMSAuth 인터페이스 존재 여부 확인."""

    def test_auth_class_exists(self):
        auth = LMSAuth()
        assert auth is not None

    def test_auth_error_is_exception(self):
        assert issubclass(AuthError, Exception)

    def test_auth_has_required_methods(self):
        auth = LMSAuth()
        assert callable(getattr(auth, "login", None))
        assert callable(getattr(auth, "new_page", None))
        assert callable(getattr(auth, "close", None))

    @pytest.mark.asyncio
    async def test_login_not_implemented(self):
        """Day 3-4 구현 전에는 NotImplementedError 가 발생해야 한다."""
        auth = LMSAuth()
        with pytest.raises(NotImplementedError):
            await auth.login()

    @pytest.mark.asyncio
    async def test_list_courses_not_implemented(self):
        """Day 5-7 구현 전에는 NotImplementedError 가 발생해야 한다."""
        auth = LMSAuth()
        with pytest.raises(NotImplementedError):
            await list_courses(auth)


# ── Day 5-7 에 채울 실제 테스트 자리 ──────────────────────────────────────────

class TestListCoursesReal:
    """실제 LMS 접속 테스트. 환경 변수에 실제 계정이 있을 때만 실행."""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Day 5-7: 실제 LMS 연동 구현 후 활성화")
    async def test_list_courses_returns_list(self):
        auth = LMSAuth()
        await auth.login()
        courses = await list_courses(auth)
        await auth.close()

        assert isinstance(courses, list)
        assert len(courses) > 0

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Day 5-7: 실제 LMS 연동 구현 후 활성화")
    async def test_course_has_required_fields(self):
        auth = LMSAuth()
        await auth.login()
        courses = await list_courses(auth)
        await auth.close()

        for c in courses:
            assert c.id, "course.id 가 비어 있으면 안 됨"
            assert c.name, "course.name 이 비어 있으면 안 됨"
