"""
scripts/analyze_api.py
──────────────────────────────────────────────────────────────
LMS 메인 페이지 로딩 시 발생하는 네트워크 요청(API) 캡처 분석.
강의 목록 API 엔드포인트를 찾는다.
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

from playwright.async_api import Request, Response
from lms_bridge.adapter.auth import LMSAuth
from lms_bridge.config import settings


async def main() -> None:
    captured: list[dict] = []

    def on_request(req: Request) -> None:
        url = req.url
        if any(kw in url for kw in ["api", "course", "class", "subject", "user", "enroll", "mypage"]):
            captured.append({
                "type": "REQ",
                "method": req.method,
                "url": url,
                "post": req.post_data,
            })

    async def on_response(resp: Response) -> None:
        url = resp.url
        ct = resp.headers.get("content-type", "")
        if "json" in ct and any(kw in url for kw in ["api", "course", "class", "subject", "enroll", "mypage"]):
            try:
                body = await resp.json()
                captured.append({
                    "type": "RES",
                    "url": url,
                    "status": resp.status,
                    "body_preview": json.dumps(body, ensure_ascii=False)[:300],
                })
            except Exception:
                pass

    async with LMSAuth() as auth:
        page = await auth.new_page()
        page.on("request", on_request)
        page.on("response", on_response)

        print("\n[1] 메인 페이지 로딩 및 API 캡처...")
        await page.goto(settings.lms_base_url, wait_until="networkidle", timeout=30_000)

        print(f"\n[2] 캡처된 관련 요청 ({len(captured)}개)")
        for item in captured:
            if item["type"] == "REQ":
                print(f"\n    ▶ [{item['method']}] {item['url']}")
                if item.get("post"):
                    print(f"      POST: {item['post'][:100]}")
            else:
                print(f"\n    ◀ [{item['status']}] {item['url']}")
                print(f"      {item['body_preview'][:200]}")

        # 전체 HTML에서 API 패턴 추출
        html = await page.content()
        print("\n[3] HTML 내 API/URL 패턴 추출")
        api_patterns = re.findall(r'["\'](/(?:api|courses?|classes?|subjects?|enroll)[^"\']{0,100})["\']', html)
        for p in sorted(set(api_patterns))[:30]:
            print(f"    {p}")

        # mypage 접근
        print("\n[4] /mypage 분석...")
        await page.goto(settings.lms_base_url + "/mypage", wait_until="networkidle", timeout=20_000)
        mypage_html = await page.content()
        with open(".cache/mypage.html", "w", encoding="utf-8") as f:
            f.write(mypage_html)
        print(f"    저장: .cache/mypage.html ({len(mypage_html):,} bytes)")

        # mypage HTML 에서 강의 관련 패턴 찾기
        course_ids = re.findall(r'[0-9a-f]{24}', mypage_html)
        if course_ids:
            print(f"\n[5] MongoDB ObjectID 후보 ({len(set(course_ids))}개)")
            for cid in sorted(set(course_ids))[:10]:
                print(f"    {cid}")

        await page.close()


if __name__ == "__main__":
    asyncio.run(main())
