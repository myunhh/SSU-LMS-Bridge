"""
scripts/analyze_courses_api.py
──────────────────────────────────────────────────────────────
수강 강의 목록 API 엔드포인트를 찾는다.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import Response
from lms_bridge.adapter.auth import LMSAuth
from lms_bridge.config import settings


async def capture_all_api(auth, url: str, label: str) -> list[dict]:
    """주어진 URL 로딩 시 발생하는 모든 /api/v1 응답을 캡처."""
    results = []

    async def on_response(resp: Response) -> None:
        if "/api/v1/" in resp.url:
            ct = resp.headers.get("content-type", "")
            try:
                if "json" in ct:
                    body = await resp.json()
                    results.append({"url": resp.url, "status": resp.status, "body": body})
            except Exception:
                pass

    page = await auth.new_page()
    page.on("response", on_response)
    print(f"\n{'='*60}")
    print(f"  [{label}] {url}")
    print(f"{'='*60}")
    await page.goto(url, wait_until="networkidle", timeout=30_000)

    print(f"  타이틀: {await page.title()}")
    print(f"  최종 URL: {page.url}")
    print(f"\n  캡처된 API ({len(results)}개):")
    for r in results:
        body_str = json.dumps(r["body"], ensure_ascii=False)
        # 수강 관련 키워드 있으면 강조
        is_course = any(k in r["url"] for k in ["course", "enroll", "class", "mypage", "user"])
        marker = "🎯" if is_course else "  "
        print(f"\n  {marker} [{r['status']}] {r['url']}")
        print(f"      {body_str[:400]}")

    await page.close()
    return results


async def main() -> None:
    async with LMSAuth() as auth:
        # mypage 분석
        await capture_all_api(auth, settings.lms_base_url + "/mypage", "MYPAGE")

        # 직접 API 호출 테스트
        print("\n\n[직접 API 엔드포인트 탐색]")
        page = await auth.new_page()

        candidate_apis = [
            "/api/v1/users/me",
            "/api/v1/users/me/courses",
            "/api/v1/users/me/enrollments",
            "/api/v1/enrollments",
            "/api/v1/courses",
            "/api/v1/courses?enrolled=true",
            "/api/v1/my-courses",
            "/api/v1/mypage",
            "/api/v1/mypage/courses",
        ]

        for path in candidate_apis:
            url = settings.lms_base_url + path
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=10_000)
                ct = resp.headers.get("content-type", "") if resp else ""
                status = resp.status if resp else "?"
                if "json" in ct:
                    try:
                        body = await page.evaluate("() => JSON.parse(document.body.innerText)")
                        body_str = json.dumps(body, ensure_ascii=False)[:200]
                        print(f"  ✅ [{status}] {path}")
                        print(f"     {body_str}")
                    except Exception:
                        content = await page.content()
                        print(f"  ✅ [{status}] {path} (parse 실패, {len(content)} bytes)")
                else:
                    content = await page.content()
                    print(f"  ─  [{status}] {path} (ct={ct[:30]!r}, {len(content)} bytes)")
            except Exception as e:
                print(f"  ✗  {path}: {e!s:.60}")

        await page.close()


if __name__ == "__main__":
    asyncio.run(main())
