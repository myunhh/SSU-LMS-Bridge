"""
lms_bridge/adapter/auth.py
──────────────────────────────────────────────────────────────
숭실대 스마트캠퍼스 LMS SSO 로그인 및 세션 관리.

구현 예정 (Phase 1-B, Day 3-4):
  - Playwright 기반 xn-sso-dir-sso 로그인 흐름
  - storage_state.json 을 통한 쿠키 캐시/재사용
  - 세션 만료 감지 및 자동 재로그인

현재 파일에는 인터페이스(타입·예외·기본 골격)만 정의되어 있다.
"""

from __future__ import annotations

from pathlib import Path

from lms_bridge.config import settings
from lms_bridge.logger import logger


class AuthError(Exception):
    """로그인/세션 관련 예외."""


class LMSAuth:
    """LMS 인증 및 세션 관리 클래스.

    사용 예::

        auth = LMSAuth()
        await auth.login()           # SSO 로그인 (세션 없으면 실행)
        page = await auth.new_page() # 인증된 Playwright 페이지 반환
        await auth.close()
    """

    def __init__(
        self,
        session_path: Path | None = None,
        headless: bool | None = None,
    ) -> None:
        self._session_path = session_path or settings.session_cache_path
        self._headless = headless if headless is not None else settings.playwright_headless
        self._browser = None
        self._context = None

    # ── 공개 인터페이스 (Day 3-4에 구현) ────────────────────────────────────

    async def login(self) -> None:
        """SSO 로그인을 수행하고 세션을 캐시한다.

        이미 유효한 세션이 있으면 재사용한다.

        TODO (Day 3):
            1. Playwright chromium 브라우저 실행
            2. storage_state.json 이 있으면 로드 → 세션 유효성 확인
            3. 세션이 없거나 만료됐으면 SSO 로그인 실행
            4. 로그인 성공 시 storage_state.json 저장
        """
        raise NotImplementedError("Day 3-4 에 구현 예정")

    async def new_page(self):  # -> playwright.async_api.Page
        """인증된 Playwright Page 객체를 반환한다.

        TODO (Day 3):
            login() 이 호출된 상태여야 한다.
            context.new_page() 를 반환하며, 이미 LMS 쿠키가 주입되어 있다.
        """
        raise NotImplementedError("Day 3-4 에 구현 예정")

    async def close(self) -> None:
        """브라우저를 종료하고 리소스를 해제한다."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        logger.info("LMSAuth: 브라우저 세션 종료")

    # ── 내부 헬퍼 (Day 3-4에 구현) ──────────────────────────────────────────

    async def _is_session_valid(self) -> bool:
        """저장된 세션 쿠키가 아직 유효한지 확인한다.

        TODO (Day 3): LMS 메인 페이지에 접근 후 로그인 리다이렉트 여부로 판단
        """
        raise NotImplementedError

    async def _do_sso_login(self) -> None:
        """실제 SSO 로그인 흐름을 Playwright 로 수행한다.

        TODO (Day 4):
            lms.ssu.ac.kr/login?type=xn-sso-dir-sso 에서
            학번/비밀번호 입력 → 로그인 버튼 클릭 → 세션 쿠키 추출
        """
        raise NotImplementedError

    async def __aenter__(self) -> LMSAuth:
        await self.login()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
