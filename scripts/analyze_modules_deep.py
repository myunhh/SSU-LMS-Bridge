"""scripts/analyze_modules_deep.py - 모듈 아이템 상세 분석"""

from __future__ import annotations
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv; load_dotenv()

import httpx
from lms_bridge.adapter.auth import LMSAuth
from lms_bridge.config import settings

CANVAS_BASE = "https://canvas.ssu.ac.kr/learningx/api/v1"
COURSE_ID = 44172  # 고급AI수학


async def main() -> None:
    auth = LMSAuth()
    await auth.login()
    token = await auth.get_canvas_token()
    cookies = await auth.get_canvas_cookies()
    await auth.close()

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Referer": f"https://canvas.ssu.ac.kr/learningx/courses/{COURSE_ID}",
        "User-Agent": "Mozilla/5.0",
    }

    async with httpx.AsyncClient(headers=headers, cookies=cookies, follow_redirects=True, timeout=15) as client:

        # 전체 모듈 (아이템 포함)
        r = await client.get(f"{CANVAS_BASE}/courses/{COURSE_ID}/modules?per_page=100")
        modules = r.json()
        print(f"총 {len(modules)}개 주차\n")

        # content_type 종류 수집
        all_types: dict[str, list] = {}

        for mod in modules[:5]:  # 처음 5주차만
            print(f"\n{'='*50}")
            print(f"[{mod['title']}] module_id={mod['module_id']}")
            items = mod.get("module_items", [])
            for item in items:
                ct = item.get("content_type", "?")
                all_types.setdefault(ct, []).append(item)
                data = item.get("content_data", {})
                print(f"  [{ct:30}] {item.get('title','')[:40]}")
                # 파일 URL 있으면 출력
                if "url" in data:
                    print(f"    url: {data['url'][:80]}")
                if "file_url" in data:
                    print(f"    file_url: {data['file_url'][:80]}")
                if "download_url" in data:
                    print(f"    download_url: {data['download_url'][:80]}")
                if "attachment" in data:
                    print(f"    attachment: {json.dumps(data['attachment'], ensure_ascii=False)[:100]}")

        # content_type 종류 요약
        print(f"\n\n{'='*50}")
        print("content_type 종류 요약:")
        for ct, items in sorted(all_types.items()):
            print(f"  {ct}: {len(items)}개")
            # 각 타입의 첫 아이템 content_data 키 출력
            if items:
                sample = items[0]
                data = sample.get("content_data", {})
                print(f"    content_data keys: {list(data.keys())[:10]}")

        # 개별 module item 탐색 (파일 타입)
        print(f"\n\n{'='*50}")
        print("파일/자료 관련 아이템 상세:")
        for mod in modules:
            for item in mod.get("module_items", []):
                ct = item.get("content_type", "")
                data = item.get("content_data", {})
                # 파일 관련 타입 찾기
                if any(kw in ct.lower() for kw in ["file", "attachment", "resource", "material"]):
                    print(f"\n  [{mod['title']}] {item.get('title')}")
                    print(f"    content_type: {ct}")
                    print(f"    content_data: {json.dumps(data, ensure_ascii=False)[:300]}")

        # 모듈 아이템 중 실제 파일이 없다면 - board/공지 엔드포인트 확인
        print(f"\n\n{'='*50}")
        print("공지/과제 대체 엔드포인트 탐색:")
        for path, label in [
            (f"/courses/{COURSE_ID}/boards", "게시판 목록"),
            (f"/courses/{COURSE_ID}/board_posts", "게시판 글"),
            (f"/boards/{COURSE_ID}/posts", "보드 글"),
            (f"/learn_activities/courses/{COURSE_ID}", "과목 활동"),
            (f"/learn_activities/courses/{COURSE_ID}/weeks", "주차별"),
            (f"/learn_activities/courses/{COURSE_ID}/notices", "공지(notices)"),
            (f"/learn_activities/courses/{COURSE_ID}/homeworks", "과제(homeworks)"),
            (f"/courses/{COURSE_ID}", "과목 기본 정보"),
        ]:
            url = f"{CANVAS_BASE}{path}"
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    try:
                        body = r.json()
                        print(f"\n  ✅ [{r.status_code}] {label}: {path}")
                        print(f"     {json.dumps(body, ensure_ascii=False)[:300]}")
                    except Exception:
                        print(f"  ─  [{r.status_code}] {label}: {path} (parse 실패)")
                else:
                    print(f"  ✗  [{r.status_code}] {label}: {path}")
            except Exception as e:
                print(f"  ERR {label}: {e!s:.60}")


if __name__ == "__main__":
    asyncio.run(main())
