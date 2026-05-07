"""
scripts/analyze_course_detail.py
──────────────────────────────────────────────────────────────
고급AI수학(44172) 상세 API 탐색: 강의자료, 공지, 과제, 파일.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

import httpx
from playwright.async_api import Response
from lms_bridge.adapter.auth import LMSAuth
from lms_bridge.config import settings

CANVAS_BASE = "https://canvas.ssu.ac.kr/learningx/api/v1"

COURSE_ID = 44172  # 고급AI수학


async def main() -> None:
    # Playwright로 mypage 접속해서 canvas 쿠키/토큰 초기화
    auth = LMSAuth()
    await auth.login()

    page = await auth.new_page()
    captured: list[dict] = []

    async def on_response(resp: Response) -> None:
        if "canvas.ssu.ac.kr" in resp.url:
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                try:
                    body = await resp.json()
                    captured.append({"url": resp.url, "status": resp.status, "body": body})
                except Exception:
                    pass

    page.on("response", on_response)

    # 해당 강의 페이지 접속
    print(f"\n[0] 강의 페이지 접속 (course_id={COURSE_ID})")
    await page.goto(
        f"https://canvas.ssu.ac.kr/learningx/courses/{COURSE_ID}",
        wait_until="networkidle",
        timeout=30_000,
    )
    print(f"    URL: {page.url}")
    print(f"    타이틀: {await page.title()}")
    print(f"\n  캡처된 API ({len(captured)}개):")
    for r in captured:
        print(f"\n  [{r['status']}] {r['url']}")
        print(f"  {json.dumps(r['body'], ensure_ascii=False)[:300]}")

    # 토큰 추출
    canvas_cookies = await auth._context.cookies(["https://canvas.ssu.ac.kr"])
    token = next((c["value"] for c in canvas_cookies if c["name"] == "xn_api_token"), "")
    canvas_cookie_dict = {c["name"]: c["value"] for c in canvas_cookies}

    await page.close()
    await auth.close()

    # httpx로 다양한 엔드포인트 탐색
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Referer": f"https://canvas.ssu.ac.kr/learningx/courses/{COURSE_ID}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }

    print(f"\n{'='*60}")
    print(f"  course_id={COURSE_ID} API 탐색")
    print(f"{'='*60}")

    candidates = [
        # 강의자료/파일
        f"/courses/{COURSE_ID}/files",
        f"/courses/{COURSE_ID}/files?per_page=50",
        f"/courses/{COURSE_ID}/folders",
        f"/courses/{COURSE_ID}/modules",
        f"/courses/{COURSE_ID}/modules?include[]=items",
        # 공지사항
        f"/courses/{COURSE_ID}/discussion_topics?only_announcements=true",
        f"/courses/{COURSE_ID}/announcements",
        f"/learn_activities/courses/{COURSE_ID}/announcements",
        # 과제
        f"/courses/{COURSE_ID}/assignments",
        f"/courses/{COURSE_ID}/assignments?per_page=50",
        f"/learn_activities/courses/{COURSE_ID}/assignments",
        # 모듈 아이템
        f"/courses/{COURSE_ID}/modules?include[]=items&per_page=50",
    ]

    async with httpx.AsyncClient(headers=headers, cookies=canvas_cookie_dict, follow_redirects=True, timeout=15) as client:
        for path in candidates:
            url = f"{CANVAS_BASE}{path}"
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    try:
                        body = r.json()
                        if body:
                            body_str = json.dumps(body, ensure_ascii=False)
                            print(f"\n  ✅ [{r.status_code}] {path}")
                            print(f"     {body_str[:400]}")
                        else:
                            print(f"  ─  [{r.status_code}] {path} (빈 응답)")
                    except Exception:
                        print(f"  ─  [{r.status_code}] {path} (JSON 파싱 실패)")
                else:
                    print(f"  ✗  [{r.status_code}] {path}")
            except Exception as e:
                print(f"  ERR {path}: {e!s:.60}")


if __name__ == "__main__":
    asyncio.run(main())
