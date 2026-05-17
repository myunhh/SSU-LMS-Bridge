# backend/app/adapter/auth.py
# Playwright SSO 로그인 및 세션 관리 (LMSAuth)
"""
SSU(숭실대학교) LMS SSO 로그인 세션 관리 모듈 (Playwright) - 세션 자동 연장 버전
"""
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class SSULMSAuthPlaywright:
    """Playwright 기반 SSU LMS SSO 로그인 세션 관리"""

    def __init__(self, session_file: str = "ssu_lms_session.json", headless: bool = True):
        self.session_file = Path(session_file)
        self.headless = headless
        self.is_authenticated = False
        self.user_info = {}

        self.base_url = "https://lms.ssu.ac.kr"
        self.sso_url = "https://smartid.ssu.ac.kr"

    async def login(self, student_id: str, password: str) -> bool:
        """SSU SSO 로그인 후 세션을 JSON 파일로 저장"""
        async with async_playwright() as p:
            browser = None
            try:
                print("🌐 브라우저 시작...")
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 720},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                page = await context.new_page()

                print("1️⃣  SSU LMS 접속...")
                await page.goto(
                    f"{self.sso_url}/Symtra_sso/smln.asp?apiReturnUrl=https%3A%2F%2Flms.ssu.ac.kr%2Fxn-sso%2Fgw-cb.php",
                    wait_until="networkidle"
                )

                if self.sso_url not in page.url:
                    print(f"⚠️  예상치 못한 URL: {page.url}")
                print("2️⃣  SSU SSO 로그인 페이지 도달")

                print("3️⃣  인증 정보 입력...")
                id_selector = 'input[name="userid"], input[name="username"], input[name="id"]'

                await page.wait_for_selector(id_selector, timeout=5000)
                await page.fill(id_selector, student_id)
                await asyncio.sleep(0.3)
                await page.fill('input[type="password"]', password)
                await asyncio.sleep(0.3)

                print("4️⃣  로그인 요청...")
                login_btn_selector = (
                    'input[type="submit"], button[type="submit"], '
                    'button:has-text("로그인"), a:has-text("로그인"), '
                    'input[type="image"]'
                )
                await page.wait_for_selector(login_btn_selector, timeout=5000)
                async with page.expect_navigation(timeout=15000, wait_until="networkidle"):
                    await page.click(login_btn_selector)

                if self.sso_url in page.url or 'login' in page.url.lower():
                    print("❌ 로그인 실패: 학번/비밀번호를 확인하세요")
                    return False

                await asyncio.sleep(2)

                if 'login.php' in page.url or self.sso_url in page.url:
                    print("❌ 로그인 실패")
                    return False

                print("5️⃣  세션 저장 중...")

                cookies = await context.cookies()
                storage_state = await context.storage_state()

                await self._extract_user_info(page)
                self._save_session(cookies, storage_state)

                self.is_authenticated = True
                print(f"✅ SSU LMS 로그인 성공: {self.user_info.get('name', student_id)}")

                return True

            except Exception as e:
                print(f"❌ 오류: {str(e)}")
                return False

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
                except:
                    continue

            self.user_info['login_time'] = datetime.now().isoformat()
        except:
            self.user_info = {'login_time': datetime.now().isoformat()}

    def _save_session(self, cookies: list, storage_state: dict):
        """세션 정보를 JSON 파일로 저장"""
        try:
            session_data = {
                'cookies': cookies,
                'storage_state': storage_state,
                'user_info': self.user_info,
                'saved_at': datetime.now().isoformat()
            }

            with open(self.session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)

            print(f"💾 세션 저장 완료: {self.session_file}")

        except Exception as e:
            print(f"❌ 세션 저장 실패: {str(e)}")

    async def load_session(self) -> bool:
        """저장된 세션을 로드하고, 유효하다면 최신 세션 상태로 업데이트하여 덮어씀"""
        if not self.session_file.exists():
            print("⚠️  저장된 세션 파일 없음")
            return False

        browser = None
        try:
            with open(self.session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context(
                    storage_state=session_data['storage_state'],
                    viewport={'width': 1280, 'height': 720},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                page = await context.new_page()

                # LMS 메인에 접속하여 세션 연장 유도
                print("🔄 세션 유효성 검증 및 연장 요청 중...")
                await page.goto(f"{self.base_url}/main.php", timeout=15000, wait_until="networkidle")
                await asyncio.sleep(2)

                # 만료되어 로그인 창으로 튕겼는지 확인
                if 'login' in page.url or self.sso_url in page.url:
                    print("⚠️  세션 만료됨 (재로그인 필요)")
                    await browser.close()
                    return False

                # 세션이 유효하므로 새로 갱신된 쿠키/스토리지 상태 추출
                updated_cookies = await context.cookies()
                updated_storage_state = await context.storage_state()

                if not session_data.get('user_info', {}).get('name'):
                    await self._extract_user_info(page)
                else:
                    self.user_info = session_data['user_info']

                # 갱신된 최신 토큰으로 파일 덮어쓰기 (만료 시간 초기화)
                self._save_session(updated_cookies, updated_storage_state)
                self.is_authenticated = True

                print(f"✅ 세션 연장 완료! (이전 저장 시각: {session_data.get('saved_at')})")
                await browser.close()
                return True

        except Exception as e:
            print(f"❌ 세션 로드 및 연장 중 오류 발생: {str(e)}")
            if browser:
                await browser.close()
            return False

    def get_session_data(self) -> Dict:
        """저장된 세션 데이터 반환"""
        if not self.session_file.exists():
            return {}
        with open(self.session_file, 'r', encoding='utf-8') as f:
            return json.load(f)


class SSULMSAuth:
    """동기 방식 래퍼 (간편 사용)"""

    def __init__(self, session_file: str = "ssu_lms_session.json", headless: bool = True):
        self.auth = SSULMSAuthPlaywright(session_file, headless)

    def login(self, student_id: str, password: str) -> bool:
        return asyncio.run(self.auth.login(student_id, password))

    def load_session(self) -> bool:
        return asyncio.run(self.auth.load_session())

    def get_session_data(self) -> Dict:
        return self.auth.get_session_data()


# 1번 방식: 주기적으로 세션을 갱신해 주는 비동기 루프 함수
async def session_keeper_loop(auth_playwright: SSULMSAuthPlaywright, interval_seconds: int = 5400):
    """
    지정한 시간(기본 1시간 30분)마다 대시보드를 찔러서 쿠키를 무한 연장하는 루프
    """
    print(f"\n🚀 세션 자동 연장 루프 가동 시작 (주기: {interval_seconds}초)")
    while True:
        try:
            print(f"\n⏱️  [{datetime.now().strftime('%H:%M:%S')}] 주기적 세션 갱신 예약 수행...")
            success = await auth_playwright.load_session()
            if not success:
                print("❌ 백그라운드 세션 연장 실패. 세션 파일이 유효하지 않거나 만료되었습니다.")
        except Exception as e:
            print(f"❌ 루프 내부 오류 발생: {e}")
        
        await asyncio.sleep(interval_seconds)


async def main_async():
    print("=" * 60)
    print("SSU(숭실대) LMS SSO 로그인 및 세션 유지")
    print("=" * 60)

    # 갱신 과정을 눈으로 확인하려면 headless=False로 두고 사용하세요.
    # 완전히 백그라운드 구동을 원하시면 headless=True로 변경하시면 됩니다.
    auth_obj = SSULMSAuthPlaywright(headless=False)

    # 1. 기존 세션이 있다면 먼저 로드 및 연장 시도
    if await auth_obj.load_session():
        print("🎉 기존 세션을 자동으로 연장하여 이어서 사용합니다.")
    else:
        # 2. 기존 세션이 없거나 이미 만료되었다면 새로 로그인 수행
        student_id = input("\n학번: ")
        password = input("비밀번호: ")
        if not await auth_obj.login(student_id, password):
            print("\n로그인에 실패하여 프로그램을 종료합니다.")
            return

    # 3. 로그인/세션 로드 완료 후 1시간 30분(5400초)마다 무한 연장 백그라운드 루프 진입
    await session_keeper_loop(auth_obj, interval_seconds=5400)


if __name__ == "__main__":
    asyncio.run(main_async())
