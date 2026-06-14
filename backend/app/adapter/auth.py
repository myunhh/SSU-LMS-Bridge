# backend/app/adapter/auth.py
# Playwright SSO 로그인 및 세션 관리 (LMSAuth)
"""
SSU(숭실대학교) LMS SSO 로그인 세션 관리 모듈 (Playwright) - 세션 자동 연장 버전
"""
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from loguru import logger
from playwright.async_api import Page, async_playwright


class SSULMSAuthPlaywright:
    """Playwright 기반 SSU LMS SSO 로그인 세션 관리"""

    def __init__(self, session_file: str = "ssu_lms_session.json", headless: bool = True):
        self.session_file = Path(session_file)
        self.headless = headless
        self.is_authenticated = False
        self.user_info = {}

        self.base_url = "https://lms.ssu.ac.kr"
        self.sso_url = "https://smartid.ssu.ac.kr"
        # Canvas 호스트(쿠키 인증) — canvas_client.py 와 동일한 //lms.→//canvas. 치환 규칙
        self.canvas_url = (
            os.getenv("CANVAS_BASE_URL", "").rstrip("/")
            or self.base_url.replace("//lms.", "//canvas.")
        )

    async def login(self, student_id: str, password: str) -> bool:
        """SSU SSO 로그인 후 세션을 JSON 파일로 저장.

        반환값 False 는 '자격증명 불일치'만 의미한다. Chromium 미설치·네트워크
        단절·SSO 페이지 변경(TimeoutError) 같은 인프라 오류는 그대로 전파해
        호출부(routes/lms.py)가 401 과 구분(502)해 응답할 수 있게 한다.
        """
        async with async_playwright() as p:
            browser = None
            try:
                logger.info("[Auth] 브라우저 시작…")
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 720},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                page = await context.new_page()

                logger.info("[Auth] SSU SSO 로그인 페이지 접속…")
                await page.goto(
                    f"{self.sso_url}/Symtra_sso/smln.asp?apiReturnUrl=https%3A%2F%2Flms.ssu.ac.kr%2Fxn-sso%2Fgw-cb.php",
                    wait_until="networkidle"
                )

                if self.sso_url not in page.url:
                    logger.warning(f"[Auth] 예상치 못한 URL: {page.url}")

                logger.info("[Auth] 인증 정보 입력…")
                id_selector = 'input[name="userid"], input[name="username"], input[name="id"]'

                await page.wait_for_selector(id_selector, timeout=5000)
                await page.fill(id_selector, student_id)
                await asyncio.sleep(0.3)
                await page.fill('input[type="password"]', password)
                await asyncio.sleep(0.3)

                logger.info("[Auth] 로그인 요청…")
                login_btn_selector = (
                    'input[type="submit"], button[type="submit"], '
                    'button:has-text("로그인"), a:has-text("로그인"), '
                    'input[type="image"]'
                )
                await page.wait_for_selector(login_btn_selector, timeout=5000)
                async with page.expect_navigation(timeout=15000, wait_until="networkidle"):
                    await page.click(login_btn_selector)

                # 자격증명 실패 → False (인프라 오류와 구분되는 유일한 False 경로)
                if self.sso_url in page.url or 'login' in page.url.lower():
                    logger.warning("[Auth] 로그인 실패: 학번/비밀번호 불일치")
                    return False

                await asyncio.sleep(2)

                if 'login.php' in page.url or self.sso_url in page.url:
                    logger.warning("[Auth] 로그인 실패: 학번/비밀번호 불일치")
                    return False

                logger.info("[Auth] 세션 저장 중…")

                cookies = await context.cookies()
                storage_state = await context.storage_state()

                await self._extract_user_info(page)
                self._save_session(cookies, storage_state)

                self.is_authenticated = True
                logger.info(f"[Auth] SSU LMS 로그인 성공: {self.user_info.get('name', student_id)}")

                return True

            finally:
                if browser:
                    await browser.close()

    async def _extract_user_info(self, page: Page):
        """사용자 이름 추출"""
        try:
            import re
            selectors = ['.username', '.user-name', '[class*="user"]']

            for selector in selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element:
                        text = await element.text_content()
                        name_match = re.search(r'([가-힣]{2,4})', text)
                        if name_match:
                            self.user_info['name'] = name_match.group(1)
                            break
                except Exception:
                    continue

            self.user_info['login_time'] = datetime.now().isoformat()
        except Exception:
            self.user_info = {'login_time': datetime.now().isoformat()}

    def _save_session(self, cookies: list, storage_state: dict):
        """세션 정보를 JSON 파일로 원자적 저장.

        같은 디렉토리의 tmp 파일에 0600 으로 먼저 쓴 뒤 os.replace 로 원자 교체한다
        (study_server._save · connectors._upsert_env_file 와 동일 규약). 기존처럼
        O_TRUNC 로 제자리에서 덮어쓰면 쓰기 도중 중단·동시 쓰기 시 세션 파일이
        반쯤 잘린 채 손상돼 직전 유효 세션마저 날아간다 — load_session 이 그걸
        '세션 무효(재로그인 필요)'로 오판한다. os.replace 는 같은 파일시스템에서
        원자적이라 교체 실패해도 직전 유효 세션 파일이 그대로 보존된다.

        tmp 도 처음부터 0600(os.open mode)으로 만든다 — 시크릿(SSO 쿠키·xn_api_token)이
        잠깐이라도 0644 로 노출되는 창을 없앤다.
        """
        try:
            session_data = {
                'cookies': cookies,
                'storage_state': storage_state,
                'user_info': self.user_info,
                'saved_at': datetime.now().isoformat()
            }

            # 같은 디렉토리 tmp (os.replace 는 동일 파일시스템에서만 원자적)
            tmp = self.session_file.with_suffix(self.session_file.suffix + '.tmp')

            # 세션 토큰(SSO 쿠키·xn_api_token) 노출 방지 — 소유자만 읽기/쓰기(0600)
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, indent=2, ensure_ascii=False)
                # O_CREAT 의 mode 는 신규 생성 시에만 적용 — tmp 가 기존 0644 로
                # 남아 있었다면 0600 으로 좁힌다 (replace 전이라 본 파일엔 영향 없음)
                os.chmod(tmp, 0o600)
                # 원자 교체 — 여기서 실패해도 직전 유효 세션 파일은 그대로 보존된다
                os.replace(tmp, self.session_file)
            except BaseException:
                # 교체 전 실패 시 반쯤 쓰인 tmp 잔여물 정리 (본 파일은 무손상)
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

            logger.info(f"[Auth] 세션 저장 완료: {self.session_file}")

        except Exception:
            logger.exception("[Auth] 세션 저장 실패")

    async def load_session(self) -> bool:
        """저장된 세션을 로드하고, 유효하다면 최신 세션 상태로 업데이트하여 덮어씀.

        lms.ssu.ac.kr 와 canvas.ssu.ac.kr 두 호스트 쿠키를 함께 연장한다 — Canvas
        호스트(쿠키 인증)를 방문하지 않으면 _normandy_session 같은 Canvas 쿠키가
        갱신되지 않아 예약 sync 가 Canvas 우선 경로에서 폴백·결측을 겪는다.

        반환값 False 는 '세션 무효(파일 없음/손상/만료) = 재로그인 필요'만 의미한다.
        Playwright 구동·페이지 접속 단계의 인프라 오류는 그대로 전파해
        호출부(routes/lms.py · routes/sync.py)가 401 과 구분해 응답할 수 있게 한다.
        """
        if not self.session_file.exists():
            logger.warning("[Auth] 저장된 세션 파일 없음")
            return False

        # 세션 파일 손상(JSON 파싱 실패, storage_state 누락 등) → 재로그인 필요
        try:
            with open(self.session_file, encoding='utf-8') as f:
                session_data = json.load(f)
            storage_state = session_data['storage_state']
        except Exception as e:
            logger.warning(f"[Auth] 세션 파일 손상 — 재로그인 필요: {e}")
            return False

        # 이 아래(Playwright 단계)의 예외는 세션 무효가 아니라 인프라 오류 → 전파
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            try:
                context = await browser.new_context(
                    storage_state=storage_state,
                    viewport={'width': 1280, 'height': 720},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                page = await context.new_page()

                # LMS 메인에 접속하여 세션 연장 유도
                logger.info("[Auth] 세션 유효성 검증 및 연장 요청 중…")
                await page.goto(f"{self.base_url}/main.php", timeout=15000, wait_until="networkidle")
                await asyncio.sleep(2)

                # 만료되어 로그인 창으로 튕겼는지 확인
                if 'login' in page.url or self.sso_url in page.url:
                    logger.warning("[Auth] 세션 만료됨 (재로그인 필요)")
                    return False

                # 사용자 정보 추출은 page 가 아직 lms main.php 에 있을 때 수행한다
                # (아래 canvas 방문 후엔 page.url 이 canvas 로 바뀌므로). 읽기 전용.
                if not session_data.get('user_info', {}).get('name'):
                    await self._extract_user_info(page)
                else:
                    self.user_info = session_data['user_info']

                # Canvas 호스트(canvas.ssu.ac.kr — 쿠키 인증)도 방문해 _normandy_session 등
                # Canvas 쿠키를 함께 재발급/연장한다. 실패해도 LMS 세션 연장은 유효하므로
                # 경고만 남긴다 (반환 계약 불변 — False 는 여전히 '세션 무효'만 의미).
                try:
                    await page.goto(f"{self.canvas_url}/", timeout=15000, wait_until="networkidle")
                except Exception as e:
                    logger.warning(f"[Auth] Canvas 세션 연장 방문 실패 — LMS 세션만 연장됨: {e}")

                # 세션이 유효하므로 새로 갱신된 쿠키/스토리지 상태 추출 (canvas 방문 후)
                updated_cookies = await context.cookies()
                updated_storage_state = await context.storage_state()

                # 갱신된 최신 토큰으로 파일 덮어쓰기 (만료 시간 초기화)
                self._save_session(updated_cookies, updated_storage_state)
                self.is_authenticated = True

                logger.info(f"[Auth] 세션 연장 완료 (이전 저장 시각: {session_data.get('saved_at')})")
                return True
            finally:
                await browser.close()
