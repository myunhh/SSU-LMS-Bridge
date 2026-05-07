"""scripts/analyze_commons.py - commons 콘텐츠 및 파일 URL 탐색"""

from __future__ import annotations
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv; load_dotenv()

import httpx
from playwright.async_api import Response
from lms_bridge.adapter.auth import LMSAuth
from lms_bridge.config import settings

CANVAS_BASE = "https://canvas.ssu.ac.kr/learningx/api/v1"
LMS_API    = "https://lms.ssu.ac.kr/api/v1"
COURSE_ID  = 44166  # 컴퓨터구조


async def main() -> None:
    auth = LMSAuth()
    await auth.login()

    # Playwright로 실제 강의 페이지 접속 → 네트워크 완전 캡처
    page = await auth.new_page()
    captured: list[dict] = []
    all_req_urls: list[str] = []

    async def on_request(req) -> None:
        all_req_urls.append(req.url)

    async def on_response(resp: Response) -> None:
        ct = resp.headers.get("content-type", "")
        if "json" in ct and resp.status == 200:
            try:
                body = await resp.json()
                captured.append({"url": resp.url, "body": body})
            except Exception:
                pass

    page.on("request", on_request)
    page.on("response", on_response)

    # LMS에서 해당 과목 접속
    print("\n[1] LMS 컴퓨터구조 과목 접속")
    await page.goto(
        f"{settings.lms_base_url}/courses/{COURSE_ID}",
        wait_until="networkidle", timeout=30_000,
    )
    print(f"    URL: {page.url} / 타이틀: {await page.title()}")

    # 모든 요청 URL 중 canvas 관련
    canvas_urls = [u for u in all_req_urls if "canvas.ssu.ac.kr" in u]
    print(f"\n  canvas.ssu.ac.kr 요청 ({len(canvas_urls)}개):")
    for u in canvas_urls[:20]:
        print(f"    {u[:100]}")

    # JSON 응답 캡처
    canvas_json = [r for r in captured if "canvas.ssu.ac.kr" in r["url"]]
    lms_json    = [r for r in captured if "lms.ssu.ac.kr"    in r["url"]]

    print(f"\n  canvas JSON 응답 ({len(canvas_json)}개):")
    for r in canvas_json[:10]:
        print(f"\n  {r['url'][:100]}")
        print(f"  {json.dumps(r['body'], ensure_ascii=False)[:300]}")

    print(f"\n  lms JSON 응답 ({len(lms_json)}개):")
    for r in lms_json[:10]:
        print(f"\n  {r['url'][:100]}")
        print(f"  {json.dumps(r['body'], ensure_ascii=False)[:300]}")

    # canvas/lms 토큰
    canvas_token = await auth.get_canvas_token()
    canvas_cookies = await auth.get_canvas_cookies()

    lms_cookies_raw = await auth._context.cookies(["https://lms.ssu.ac.kr"])
    lms_cookies = {c["name"]: c["value"] for c in lms_cookies_raw}
    xn_token = lms_cookies.get("xn_coursecatalog_api_token", "")

    await page.close()
    await auth.close()

    # commons item 상세 조회
    commons_id = "69b7b7f6bdb0c5144e04e3e0"  # 컴퓨터구조 2주차

    canvas_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {canvas_token}",
        "Referer": f"https://canvas.ssu.ac.kr/learningx/courses/{COURSE_ID}",
        "User-Agent": "Mozilla/5.0",
    }

    print(f"\n{'='*60}")
    print("Commons 콘텐츠 API 탐색")
    print(f"{'='*60}")

    async with httpx.AsyncClient(headers=canvas_headers, cookies=canvas_cookies, follow_redirects=True, timeout=15) as client:
        for path, label in [
            (f"/commons/items/{commons_id}", "commons item"),
            (f"/commons/{commons_id}", "commons direct"),
            (f"/courses/{COURSE_ID}/commons/{commons_id}", "commons in course"),
            (f"/courses/{COURSE_ID}/attendance_items/786059", "attendance item 상세"),
            (f"/attendance_items/786059", "attendance item global"),
            (f"/courses/{COURSE_ID}/attendance_items/786059/files", "attendance files"),
        ]:
            r = await client.get(f"{CANVAS_BASE}{path}")
            print(f"  [{r.status_code}] {label}: {r.text[:200]}")

    # lms.ssu.ac.kr/api/v1 에서 course 관련 보드 찾기
    print(f"\n{'='*60}")
    print(f"LMS 보드 탐색 (course_id={COURSE_ID})")
    print(f"{'='*60}")

    lms_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {xn_token}",
        "Referer": f"https://lms.ssu.ac.kr/courses/{COURSE_ID}",
        "User-Agent": "Mozilla/5.0",
    }

    async with httpx.AsyncClient(headers=lms_headers, cookies=lms_cookies, follow_redirects=True, timeout=15) as client:
        for path, label in [
            (f"/courses/{COURSE_ID}/boards", "과목 보드 목록"),
            ("/boards", "전체 보드 목록"),
            (f"/users/me", "내 정보"),
        ]:
            r = await client.get(f"{LMS_API}{path}")
            print(f"  [{r.status_code}] {label}: {r.text[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
