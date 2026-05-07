"""
lms_bridge/adapter/auth.py
──────────────────────────────────────────────────────────────
숭실대 스마트캠퍼스 LMS SSO 로그인 및 세션 관리.

로그인 흐름 (분석 결과):
  1. https://lms.ssu.ac.kr/login?type=xn-sso-dir-sso
     → https://smartid.ssu.ac.kr/Symtra_sso/smln.asp?apiReturnUrl=...
  2. form[name=LoginInfo, action=smln_pcs.asp, target=pFrame] 에
     userid / pwd 입력 후 제출 (iframe 타겟)
  3. smln_pcs.asp → SSO 인증 → lms.ssu.ac.kr/xn-sso/gw-cb.php 콜백
  4. LMS 세션 쿠키(coursecatalog_session 등) 설정 완료
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from lms_bridge.config import settings
from lms_bridge.logger import logger


class AuthError(Exception):
    """로그인 / 세션 관련 예외."""


# LMS 에서 로그인 성공 후 보이는 경로 패턴 (리다이렉트 감지용)
_LMS_AUTHED_PATH_PATTERNS = ["/classes", "/dashboard", "/xn-sso/gw-cb.php"]
# 세션 유효성 확인용 — 로그인 없이 접근하면 리다이렉트되는 보호 페이지
_SESSION_CHECK_URL = f"{settings.lms_base_url}/classes"


class LMSAuth:
    """LMS 인증 및 Playwright 세션 관리.

    사용 예 (컨텍스트 매니저)::

        async with LMSAuth() as auth:
            page = await auth.new_page()
            await page.goto("https://lms.ssu.ac.kr/classes")

    사용 예 (수동)::

        auth = LMSAuth()
        await auth.login()
        page = await auth.new_page()
        ...
        await auth.close()
    """

    def __init__(
        self,
        session_path: Path | None = None,
        headless: bool | None = None,
    ) -> None:
        self._session_path: Path = session_path or settings.session_cache_path
        self._headless: bool = headless if headless is not None else settings.playwright_headless

        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    # ────────────────────────────────────────────────────────────────────────
    # 공개 인터페이스
    # ────────────────────────────────────────────────────────────────────────

    async def login(self) -> None:
        """SSO 로그인을 수행하고 세션을 캐시한다.

        이미 유효한 세션이 있으면 재사용한다.
        캐시가 없거나 만료됐으면 실제 SSO 로그인을 진행한다.
        """
        await self._start_browser()

        if self._session_path.exists():
            logger.info("세션 캐시 발견 — 유효성 확인 중...")
            await self._load_session()
            if await self._is_session_valid():
                logger.info("세션 재사용 ✅")
                return
            logger.info("세션 만료 — 재로그인 진행")

        await self._do_sso_login()

    async def new_page(self) -> Page:
        """인증된 Playwright Page 를 반환한다. login() 후 호출해야 한다."""
        if self._context is None:
            raise AuthError("login() 을 먼저 호출하세요.")
        return await self._context.new_page()

    async def close(self) -> None:
        """브라우저를 종료하고 리소스를 해제한다."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
        logger.info("LMSAuth: 브라우저 세션 종료")

    # ────────────────────────────────────────────────────────────────────────
    # 내부 헬퍼
    # ────────────────────────────────────────────────────────────────────────

    async def _start_browser(self) -> None:
        """Playwright + Chromium 브라우저를 시작한다."""
        if self._pw is None:
            self._pw = await async_playwright().start()
        if self._browser is None:
            self._browser = await self._pw.chromium.launch(
                headless=self._headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        # 컨텍스트가 없으면 새로 생성
        if self._context is None:
            self._context = await self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="ko-KR",
            )

    async def _load_session(self) -> None:
        """저장된 storage_state 를 컨텍스트에 로드한다."""
        if self._context:
            await self._context.close()
        storage = json.loads(self._session_path.read_text(encoding="utf-8"))
        self._context = await self._browser.new_context(  # type: ignore[union-attr]
            storage_state=storage,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="ko-KR",
        )
        logger.debug(f"세션 로드: {self._session_path}")

    async def _is_session_valid(self) -> bool:
        """저장된 세션 쿠키가 아직 유효한지 확인한다.

        보호된 페이지(/classes)에 접근했을 때 로그인 페이지로 리다이렉트되면
        세션이 만료된 것으로 판단한다.
        """
        page = await self._context.new_page()  # type: ignore[union-attr]
        try:
            resp = await page.goto(
                _SESSION_CHECK_URL,
                wait_until="domcontentloaded",
                timeout=20_000,
            )
            final_url = page.url
            # 로그인 페이지로 리다이렉트됐으면 세션 만료
            if "login" in final_url or "smartid.ssu.ac.kr" in final_url:
                return False
            # 응답 코드가 200 이면 유효
            return resp is not None and resp.status == 200
        except Exception as e:
            logger.warning(f"세션 확인 중 오류: {e}")
            return False
        finally:
            await page.close()

    async def _do_sso_login(self) -> None:
        """실제 SSO 로그인 흐름을 Playwright 로 수행한다.

        흐름:
          LMS 로그인 URL → smartid.ssu.ac.kr SSO 폼 → userid/pwd 입력
          → LoginInfoSend() 호출 (iframe 타겟 제출) → LMS 콜백 대기
          → storage_state 저장
        """
        page = await self.new_page()
        login_url = settings.login_url

        try:
            logger.info(f"SSO 로그인 시작: {login_url}")

            # 1. LMS 로그인 URL 접속 → smartid.ssu.ac.kr 로 리다이렉트됨
            await page.goto(login_url, wait_until="networkidle", timeout=30_000)
            logger.debug(f"현재 URL: {page.url}")

            # 2. SSO 폼이 있는지 확인
            if "smartid.ssu.ac.kr" not in page.url:
                raise AuthError(f"예상치 못한 URL: {page.url!r} (smartid.ssu.ac.kr 로 리다이렉트 실패)")

            # 3. 학번 / 비밀번호 입력
            await page.wait_for_selector("#userid", timeout=10_000)
            await page.fill("#userid", settings.lms_username)
            await page.fill("#pwd", settings.lms_password)
            logger.debug("학번 / 비밀번호 입력 완료")

            # 4. 로그인 버튼 클릭 (JavaScript:LoginInfoSend 호출)
            #    form target="pFrame" 이므로 iframe 에 제출됨
            #    → SSO 처리 후 메인 페이지가 LMS 콜백 URL 로 이동
            async with page.expect_navigation(
                url=lambda u: "lms.ssu.ac.kr" in u,
                timeout=30_000,
            ):
                await page.click("a.btn_login")

            logger.debug(f"로그인 후 URL: {page.url}")

            # 5. LMS 메인 페이지 로딩 대기
            await page.wait_for_load_state("networkidle", timeout=30_000)
            final_url = page.url

            # 6. 로그인 성공 여부 확인
            if "login" in final_url or "smartid.ssu.ac.kr" in final_url:
                raise AuthError(
                    "로그인 실패: 학번 또는 비밀번호를 확인하세요. "
                    f"(현재 URL: {final_url})"
                )

            logger.info(f"로그인 성공 ✅  (URL: {final_url})")

            # 7. 세션 저장
            await self._save_session()

        except AuthError:
            raise
        except Exception as e:
            raise AuthError(f"로그인 중 오류 발생: {e}") from e
        finally:
            await page.close()

    async def _save_session(self) -> None:
        """현재 컨텍스트의 storage_state 를 파일에 저장한다."""
        self._session_path.parent.mkdir(parents=True, exist_ok=True)
        state = await self._context.storage_state()  # type: ignore[union-attr]
        self._session_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"세션 저장 완료: {self._session_path}")

    async def get_canvas_token(self) -> str:
        """canvas.ssu.ac.kr API 에 사용할 Bearer 토큰(xn_api_token)을 반환한다.

        mypage 를 한 번 방문해야 canvas 세션 쿠키가 설정된다.
        """
        if self._context is None:
            raise AuthError("login() 을 먼저 호출하세요.")

        # canvas 쿠키 확인
        canvas_cookies = await self._context.cookies(["https://canvas.ssu.ac.kr"])
        token = next(
            (c["value"] for c in canvas_cookies if c["name"] == "xn_api_token"),
            None,
        )

        if not token:
            # mypage 방문으로 canvas 세션 초기화
            logger.info("canvas 토큰 초기화 중 (mypage 방문)...")
            page = await self.new_page()
            try:
                await page.goto(
                    f"{settings.lms_base_url}/mypage",
                    wait_until="networkidle",
                    timeout=30_000,
                )
            finally:
                await page.close()
            canvas_cookies = await self._context.cookies(["https://canvas.ssu.ac.kr"])
            token = next(
                (c["value"] for c in canvas_cookies if c["name"] == "xn_api_token"),
                None,
            )

        if not token:
            raise AuthError("canvas API 토큰(xn_api_token)을 가져올 수 없습니다.")

        return token

    async def get_canvas_cookies(self) -> dict[str, str]:
        """canvas.ssu.ac.kr 도메인 쿠키를 dict 형태로 반환한다."""
        if self._context is None:
            raise AuthError("login() 을 먼저 호출하세요.")
        cookies = await self._context.cookies(["https://canvas.ssu.ac.kr"])
        return {c["name"]: c["value"] for c in cookies}

    # ────────────────────────────────────────────────────────────────────────
    # 컨텍스트 매니저
    # ────────────────────────────────────────────────────────────────────────

    async def __aenter__(self) -> LMSAuth:
        await self.login()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
