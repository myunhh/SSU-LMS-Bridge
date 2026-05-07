"""
scripts/test_login.py
──────────────────────────────────────────────────────────────
SSO 로그인 + 세션 캐시 동작 확인 스크립트.

실행: python scripts/test_login.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from lms_bridge.adapter.auth import LMSAuth
from lms_bridge.config import settings


async def main() -> None:
    print("\n" + "=" * 55)
    print("  LMS-Bridge SSO 로그인 테스트")
    print("=" * 55)
    print(f"  학번  : {settings.lms_username}")
    print(f"  URL   : {settings.login_url}")
    print(f"  세션  : {settings.session_cache_path}")
    print("=" * 55)

    auth = LMSAuth(headless=True)

    # ── 1차 로그인 ────────────────────────────────────────────
    print("\n[1] 로그인 시도...")
    t0 = time.perf_counter()
    try:
        await auth.login()
        elapsed = time.perf_counter() - t0
        print(f"    ✅  로그인 성공! ({elapsed:.1f}초)")
    except Exception as e:
        print(f"    ❌  로그인 실패: {e}")
        await auth.close()
        sys.exit(1)

    # ── 세션 유효성 확인 ──────────────────────────────────────
    print("\n[2] 세션 유효성 확인...")
    valid = await auth._is_session_valid()
    print(f"    {'✅  유효' if valid else '❌  만료'}")

    # ── 페이지 접속 테스트 ────────────────────────────────────
    print("\n[3] 인증된 페이지 접속 테스트 (/classes)...")
    page = await auth.new_page()
    try:
        await page.goto(f"{settings.lms_base_url}/classes", wait_until="networkidle", timeout=30_000)
        title = await page.title()
        url = page.url
        print(f"    URL   : {url}")
        print(f"    타이틀: {title}")
        print(f"    {'✅  접속 성공' if 'login' not in url else '❌  로그인 페이지로 리다이렉트됨'}")

        # 강의 목록이 있는지 확인
        cards = await page.query_selector_all("[class*='course'], [class*='class'], [class*='subject']")
        print(f"    강의 카드 요소 수: {len(cards)}개")
    finally:
        await page.close()

    # ── 세션 캐시 파일 확인 ──────────────────────────────────
    print("\n[4] 세션 캐시 파일 확인...")
    cache_path = settings.session_cache_path
    if cache_path.exists():
        size = cache_path.stat().st_size
        print(f"    ✅  {cache_path}  ({size:,} bytes)")
    else:
        print(f"    ❌  세션 파일 없음: {cache_path}")

    # ── 2차 로그인 (캐시 재사용 확인) ────────────────────────
    print("\n[5] 세션 재사용 테스트 (캐시에서 로드)...")
    await auth.close()
    auth2 = LMSAuth(headless=True)
    t1 = time.perf_counter()
    await auth2.login()
    elapsed2 = time.perf_counter() - t1
    print(f"    ✅  세션 재사용 완료! ({elapsed2:.1f}초, 1차 대비 {elapsed - elapsed2:.1f}초 빠름)")
    await auth2.close()

    print("\n" + "=" * 55)
    print("  🎉  모든 테스트 통과!")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
