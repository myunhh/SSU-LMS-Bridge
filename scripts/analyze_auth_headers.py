"""
scripts/analyze_auth_headers.py
──────────────────────────────────────────────────────────────
canvas API 요청 시 실제 전송되는 헤더 캡처.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import Request, Response
from lms_bridge.adapter.auth import LMSAuth
from lms_bridge.config import settings

CANVAS_BASE = "https://canvas.ssu.ac.kr"


async def main() -> None:
    captured_headers: dict = {}
    captured_responses: list = []

    async def on_request(req: Request) -> None:
        if "canvas.ssu.ac.kr" in req.url:
            captured_headers[req.url] = dict(req.headers)

    async def on_response(resp: Response) -> None:
        if "canvas.ssu.ac.kr" in resp.url and "/api/v1/" in resp.url:
            ct = resp.headers.get("content-type", "")
            try:
                if "json" in ct:
                    body = await resp.json()
                    captured_responses.append({
                        "url": resp.url,
                        "status": resp.status,
                        "body": body,
                    })
            except Exception:
                pass

    async with LMSAuth() as auth:
        page = await auth.new_page()
        page.on("request", on_request)
        page.on("response", on_response)

        await page.goto(settings.lms_base_url + "/mypage", wait_until="networkidle", timeout=30_000)

        print("\n[1] canvas.ssu.ac.kr 요청 헤더 분석")
        for url, hdrs in captured_headers.items():
            if "/api/v1/" in url:
                print(f"\n  URL: {url[:80]}")
                for k, v in hdrs.items():
                    # 인증 관련 헤더 표시
                    if k.lower() in [
                        "authorization", "x-auth-token", "x-api-key", "x-csrf-token",
                        "cookie", "x-requested-with", "origin", "referer",
                        "x-xsrf-token", "x-token",
                    ]:
                        print(f"    {k}: {v[:80]}")

        print("\n[2] 성공한 API 응답")
        for r in captured_responses:
            print(f"\n  [{r['status']}] {r['url']}")
            print(f"  {json.dumps(r['body'], ensure_ascii=False)[:300]}")

        # 토큰 추출 시도 - JavaScript 실행
        print("\n[3] JavaScript 에서 토큰 추출 시도")
        for js_expr in [
            "window.ENV?.current_user_id",
            "window.ENV?.access_token",
            "localStorage.getItem('access_token')",
            "localStorage.getItem('token')",
            "document.cookie",
            "window.__INITIAL_STATE__",
            "Object.keys(localStorage)",
        ]:
            try:
                result = await page.evaluate(js_expr)
                if result:
                    print(f"    {js_expr}: {str(result)[:100]}")
            except Exception:
                pass

        # network request로 직접 canvas API 호출 (브라우저 컨텍스트 내)
        print("\n[4] 브라우저 fetch()로 canvas API 직접 호출")
        for path, label in [
            (f"/learningx/api/v1/users/{settings.lms_username}/terms?include_invited_course_contained=true", "학기 목록"),
        ]:
            try:
                result = await page.evaluate(f"""
                    async () => {{
                        const r = await fetch('https://canvas.ssu.ac.kr{path}', {{
                            credentials: 'include',
                            headers: {{ 'Accept': 'application/json' }}
                        }});
                        const data = await r.json();
                        return {{ status: r.status, data: JSON.stringify(data).slice(0, 300) }};
                    }}
                """)
                print(f"  {label}: status={result['status']}")
                print(f"    {result['data']}")
            except Exception as e:
                print(f"  {label} 실패: {e}")

        # 쿠키 전체 재확인
        print("\n[5] canvas.ssu.ac.kr 쿠키 목록")
        all_cookies = await auth._context.cookies(["https://canvas.ssu.ac.kr"])
        for c in all_cookies:
            print(f"  {c['name']}: {c['value'][:60]} (httpOnly={c.get('httpOnly')})")

        await page.close()


if __name__ == "__main__":
    asyncio.run(main())
