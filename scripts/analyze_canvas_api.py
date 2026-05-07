"""
scripts/analyze_canvas_api.py
──────────────────────────────────────────────────────────────
canvas.ssu.ac.kr/learningx/api/v1/ 전체 구조 탐색.
쿠키 추출 후 httpx로 직접 API 호출.
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
from lms_bridge.adapter.auth import LMSAuth
from lms_bridge.config import settings

CANVAS_BASE = "https://canvas.ssu.ac.kr/learningx/api/v1"


async def get_cookies(auth: LMSAuth) -> dict[str, str]:
    """Playwright 컨텍스트에서 canvas.ssu.ac.kr 쿠키를 추출한다."""
    all_cookies = await auth._context.cookies()
    return {c["name"]: c["value"] for c in all_cookies}


async def call_api(client: httpx.AsyncClient, path: str, label: str) -> dict | list | None:
    url = f"{CANVAS_BASE}{path}"
    try:
        r = await client.get(url, timeout=15)
        body = r.json()
        print(f"\n  ✅ [{r.status_code}] {label}")
        print(f"     {path}")
        print(f"     {json.dumps(body, ensure_ascii=False)[:400]}")
        return body
    except Exception as e:
        print(f"\n  ✗ {label}: {e!s:.80}")
        return None


async def main() -> None:
    async with LMSAuth() as auth:
        # Playwright로 mypage 한 번 접속해서 canvas 쿠키 초기화
        page = await auth.new_page()
        await page.goto(settings.lms_base_url + "/mypage", wait_until="networkidle", timeout=30_000)

        cookies = await get_cookies(auth)
        print(f"\n쿠키 목록:")
        for k, v in cookies.items():
            print(f"  {k}: {v[:40]}...")

        await page.close()

    # httpx 클라이언트로 canvas API 직접 호출
    username = settings.lms_username
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://lms.ssu.ac.kr/",
    }

    async with httpx.AsyncClient(cookies=cookies, headers=headers, follow_redirects=True) as client:
        print("\n" + "="*60)
        print("  Canvas API 탐색")
        print("="*60)

        # 1. 학기 목록
        terms_data = await call_api(
            client,
            f"/users/{username}/terms?include_invited_course_contained=true",
            "학기 목록"
        )
        if not terms_data:
            print("  ⚠️ 쿠키 인증 실패 - canvas 도메인 쿠키 없음")
            return

        term_ids = [t["id"] for t in terms_data.get("enrollment_terms", []) if t.get("workflow_state") == "active"]
        active_term_id = next(
            (t["id"] for t in terms_data.get("enrollment_terms", [])
             if t.get("default") and "학기" in t.get("name", "")), None
        )
        print(f"\n  활성 term IDs: {term_ids}")
        print(f"  현재 학기 term ID: {active_term_id}")

        # 2. 수강 강의 목록 (전체 활성 학기)
        term_params = "&".join(f"term_ids[]={tid}" for tid in term_ids)
        courses_data = await call_api(
            client,
            f"/learn_activities/courses?{term_params}",
            "수강 강의 목록"
        )

        if courses_data and isinstance(courses_data, list):
            print(f"\n  수강 과목 총 {len(courses_data)}개:")
            for c in courses_data:
                print(f"    [{c['id']}] {c['name']} / 교수: {c.get('professors','?')} / term: {c.get('term_id')}")

            # 첫 번째 과목으로 추가 API 탐색
            if courses_data:
                course = next((c for c in courses_data if c.get("term_id") == active_term_id), courses_data[0])
                cid = course["id"]
                cname = course["name"]
                print(f"\n  [샘플 과목: {cname} (id={cid})]")

                for path, label in [
                    (f"/courses/{cid}", "과목 상세"),
                    (f"/courses/{cid}/announcements", "공지사항"),
                    (f"/courses/{cid}/assignments", "과제 목록"),
                    (f"/courses/{cid}/modules", "강의 모듈/주차"),
                    (f"/courses/{cid}/files", "파일 목록"),
                    (f"/courses/{cid}/pages", "페이지 목록"),
                    (f"/learn_activities/courses/{cid}/resources", "강의 자료"),
                    (f"/learn_activities/courses/{cid}/announcements", "공지사항(v2)"),
                    (f"/learn_activities/courses/{cid}/assignments", "과제(v2)"),
                ]:
                    await call_api(client, path, label)

        # 3. Todo (과제 마감일)
        await call_api(
            client,
            f"/learn_activities/to_dos?{term_params}",
            "전체 할일/마감일"
        )


if __name__ == "__main__":
    asyncio.run(main())
