"""scripts/analyze_lms_api.py - lms.ssu.ac.kr /api/v1 + attendance_item 상세 분석"""

from __future__ import annotations
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv; load_dotenv()

import httpx
from playwright.async_api import Response
from lms_bridge.adapter.auth import LMSAuth
from lms_bridge.config import settings

CANVAS_BASE = "https://canvas.ssu.ac.kr/learningx/api/v1"
LMS_API = "https://lms.ssu.ac.kr/api/v1"
COURSE_ID = 44172  # 고급AI수학
COURSE_ID2 = 44166  # 컴퓨터구조 (미제출 과제 있음)


async def main() -> None:
    auth = LMSAuth()
    await auth.login()

    # 과목 페이지에서 네트워크 캡처
    page = await auth.new_page()
    captured: list[dict] = []

    async def on_response(resp: Response) -> None:
        if resp.url and ("api/v1" in resp.url or "attendance" in resp.url.lower()):
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                try:
                    body = await resp.json()
                    captured.append({"url": resp.url, "status": resp.status, "body": body})
                except Exception:
                    pass

    page.on("response", on_response)

    # 컴퓨터구조 과목 페이지 접속
    print(f"\n[0] 컴퓨터구조(44166) 과목 페이지 접속")
    await page.goto(
        f"https://canvas.ssu.ac.kr/learningx/courses/{COURSE_ID2}",
        wait_until="networkidle", timeout=30_000,
    )
    print(f"    URL: {page.url} / 타이틀: {await page.title()}")

    print(f"\n  캡처된 API ({len(captured)}개):")
    for r in captured[:15]:
        print(f"\n  [{r['status']}] {r['url']}")
        print(f"  {json.dumps(r['body'], ensure_ascii=False)[:300]}")

    # LMS API 토큰
    lms_cookies_raw = await auth._context.cookies(["https://lms.ssu.ac.kr"])
    lms_cookies = {c["name"]: c["value"] for c in lms_cookies_raw}
    xn_token = lms_cookies.get("xn_coursecatalog_api_token", "")

    # canvas API 토큰/쿠키
    canvas_token = await auth.get_canvas_token()
    canvas_cookies = await auth.get_canvas_cookies()

    await page.close()
    await auth.close()

    lms_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {xn_token}",
        "Referer": "https://lms.ssu.ac.kr/",
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
    }

    canvas_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {canvas_token}",
        "Referer": f"https://canvas.ssu.ac.kr/learningx/courses/{COURSE_ID2}",
        "User-Agent": "Mozilla/5.0",
    }

    print(f"\n{'='*60}")
    print("LMS API (lms.ssu.ac.kr/api/v1) 탐색")
    print(f"{'='*60}")

    async with httpx.AsyncClient(headers=lms_headers, cookies=lms_cookies, follow_redirects=True, timeout=15) as client:
        for path, label in [
            (f"/courses/{COURSE_ID2}", "과목 상세(LMS)"),
            (f"/courses/{COURSE_ID2}/assignments", "과제(LMS)"),
            (f"/courses/{COURSE_ID2}/announcements", "공지(LMS)"),
            (f"/courses/{COURSE_ID2}/modules", "모듈(LMS)"),
            (f"/courses/{COURSE_ID2}/boards", "게시판(LMS)"),
            ("/users/me/courses", "내 강의(LMS)"),
        ]:
            url = f"{LMS_API}{path}"
            try:
                r = await client.get(url)
                body_text = r.text[:200]
                print(f"  [{r.status_code}] {label}: {body_text}")
            except Exception as e:
                print(f"  ERR {label}: {e!s:.60}")

    print(f"\n{'='*60}")
    print(f"Canvas API - 컴퓨터구조({COURSE_ID2}) 탐색")
    print(f"{'='*60}")

    async with httpx.AsyncClient(headers=canvas_headers, cookies=canvas_cookies, follow_redirects=True, timeout=15) as client:

        # 모듈 상세
        r = await client.get(f"{CANVAS_BASE}/courses/{COURSE_ID2}/modules?per_page=100")
        modules = r.json() if r.status_code == 200 else []
        print(f"\n  모듈 {len(modules)}개")

        for mod in modules[:3]:
            print(f"\n  [{mod['title']}] module_id={mod['module_id']}")
            for item in mod.get("module_items", []):
                ct = item.get("content_type", "")
                data = item.get("content_data", {})
                print(f"    [{ct}] {item.get('title','')[:40]}")
                if data:
                    print(f"      data: {json.dumps(data, ensure_ascii=False)[:200]}")

        # attendance_item 상세 조회
        print(f"\n  attendance_item 상세 조회:")
        if modules:
            for mod in modules[:2]:
                for item in mod.get("module_items", []):
                    if item.get("content_type") == "attendance_item":
                        content_id = item.get("content_id")
                        for path2, label2 in [
                            (f"/courses/{COURSE_ID2}/attendance_items/{content_id}", f"attendance {content_id}"),
                            (f"/attendance_items/{content_id}", f"attendance global {content_id}"),
                        ]:
                            r2 = await client.get(f"{CANVAS_BASE}{path2}")
                            print(f"    [{r2.status_code}] {label2}")
                            if r2.status_code == 200:
                                print(f"      {r2.text[:300]}")
                        break

        # 과제 direct 탐색
        for path, label in [
            (f"/courses/{COURSE_ID2}/assignments?per_page=50", "과제"),
            (f"/courses/{COURSE_ID2}/discussion_topics?only_announcements=true&per_page=20", "공지(discussion)"),
        ]:
            r = await client.get(f"{CANVAS_BASE}{path}")
            print(f"\n  [{r.status_code}] {label}")
            if r.status_code == 200:
                print(f"    {r.text[:400]}")


if __name__ == "__main__":
    asyncio.run(main())
