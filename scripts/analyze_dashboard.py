"""
scripts/analyze_dashboard.py
──────────────────────────────────────────────────────────────
로그인 후 LMS 대시보드/강의목록 페이지 구조 분석.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from lms_bridge.adapter.auth import LMSAuth
from lms_bridge.config import settings


async def main() -> None:
    async with LMSAuth() as auth:
        page = await auth.new_page()

        # 로그인 후 메인 페이지 탐색
        print("\n[1] LMS 메인 페이지 분석")
        await page.goto(settings.lms_base_url, wait_until="networkidle", timeout=30_000)
        print(f"    URL   : {page.url}")
        print(f"    타이틀: {await page.title()}")

        # 네비게이션 메뉴 링크 수집
        print("\n[2] 네비게이션 / 주요 링크")
        links = await page.query_selector_all("a[href]")
        seen = set()
        for link in links:
            href = await link.get_attribute("href") or ""
            text = (await link.inner_text()).strip()
            if href.startswith("http") or href.startswith("/"):
                if href not in seen and len(href) < 100:
                    seen.add(href)
                    if any(kw in href.lower() for kw in ["course", "class", "subject", "lms", "index", "main", "dashboard"]):
                        print(f"    [{text[:30]:30}] → {href}")

        # 강의 카드/목록 패턴 탐색 (다양한 선택자 시도)
        print("\n[3] 강의 목록 요소 탐색")
        selectors_to_try = [
            ".course-card",
            ".course-item",
            ".subject-item",
            "[class*='course']",
            "[class*='subject']",
            "[class*='class']",
            "li[data-course]",
            "[data-course-id]",
            ".xn-course",
            ".course-list li",
        ]
        for sel in selectors_to_try:
            els = await page.query_selector_all(sel)
            if els:
                print(f"    ✅ {sel!r:35} → {len(els)}개 발견")
                if len(els) <= 3:
                    for el in els:
                        txt = (await el.inner_text()).strip()[:60]
                        print(f"       텍스트: {txt!r}")
            else:
                print(f"    ─  {sel!r:35} → 없음")

        # HTML 저장
        html = await page.content()
        with open(".cache/dashboard.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\n[4] HTML 저장: .cache/dashboard.html ({len(html):,} bytes)")

        # 주요 URL 시도
        print("\n[5] 주요 URL 탐색")
        test_urls = [
            "/",
            "/courses",
            "/classes",
            "/dashboard",
            "/home",
            "/index",
        ]
        for path in test_urls:
            url = settings.lms_base_url + path
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=10_000)
                final = page.url
                status = resp.status if resp else "?"
                title = await page.title()
                redirect = " → " + final if final != url else ""
                print(f"    [{status}] {path:15}{redirect}")
                print(f"           타이틀: {title[:50]}")
            except Exception as e:
                print(f"    [ERR] {path}: {e!s:.40}")

        await page.close()


if __name__ == "__main__":
    asyncio.run(main())
