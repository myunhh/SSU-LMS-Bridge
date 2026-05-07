"""
scripts/test_canvas_api.py
──────────────────────────────────────────────────────────────
LMSAuth + CanvasClient 통합 테스트.
실제 수강 과목, 공지사항, 과제, 강의 자료를 가져온다.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from lms_bridge.adapter.auth import LMSAuth
from lms_bridge.adapter.canvas_client import CanvasClient


async def main() -> None:
    print("\n" + "="*60)
    print("  LMS-Bridge Canvas API 통합 테스트")
    print("="*60)

    async with LMSAuth() as auth:
        # canvas 토큰 초기화
        print("\n[1] Canvas 토큰 준비...")
        token = await auth.get_canvas_token()
        print(f"    ✅ 토큰 획득: {token[:40]}...")

        async with await CanvasClient.from_auth(auth) as client:

            # 학기 목록
            print("\n[2] 학기 목록")
            terms = await client.get_terms()
            for t in terms:
                marker = "★" if t.get("default") else " "
                print(f"    [{marker}] id={t['id']} name={t['name']}")

            current_term = client.get_current_term(terms)
            print(f"\n    현재 학기: {current_term['name']} (id={current_term['id']})")

            # 수강 강의 목록
            print("\n[3] 수강 강의 목록")
            courses = await client.get_courses(terms)
            for c in courses:
                if c.get("term_id") == current_term["id"]:
                    print(f"    ✅ [{c['id']}] {c['name']}")
                    print(f"       교수: {c.get('professors','?')} / 수강생: {c.get('total_students','?')}명")

            # 첫 번째 현재학기 과목으로 상세 탐색
            current_courses = [c for c in courses if c.get("term_id") == current_term["id"]]
            if not current_courses:
                print("    현재 학기 수강 과목 없음")
                return

            sample = current_courses[0]
            cid = sample["id"]
            cname = sample["name"]
            print(f"\n[4] 샘플 과목 상세: {cname} (id={cid})")

            # 공지사항
            print(f"\n  [4-1] 공지사항")
            notices = await client.get_announcements(cid)
            print(f"    {len(notices)}개 로드")
            for n in notices[:3]:
                print(f"    - {json.dumps(n, ensure_ascii=False)[:100]}")

            # 과제
            print(f"\n  [4-2] 과제 목록")
            assignments = await client.get_assignments(cid)
            print(f"    {len(assignments)}개 로드")
            for a in assignments[:3]:
                print(f"    - {json.dumps(a, ensure_ascii=False)[:100]}")

            # 강의 자료
            print(f"\n  [4-3] 강의 자료")
            resources = await client.get_resources(cid)
            print(f"    {len(resources)}개 로드")
            for r in resources[:3]:
                print(f"    - {json.dumps(r, ensure_ascii=False)[:100]}")

            # 모듈
            print(f"\n  [4-4] 모듈(주차)")
            modules = await client.get_modules(cid)
            print(f"    {len(modules)}개 로드")
            for m in modules[:3]:
                print(f"    - {json.dumps(m, ensure_ascii=False)[:100]}")

            # 전체 할일
            print(f"\n[5] 전체 할일/마감일")
            todos = await client.get_all_todos(terms)
            todo_list = todos.get("to_dos", [])
            print(f"    {len(todo_list)}개 과목의 할일 정보")
            for t in todo_list[:3]:
                acts = t.get("activities", {})
                print(f"    course_id={t['course_id']}: 미제출={acts.get('total_unsubmitted_assignments',0)} / 안읽은공지={acts.get('total_unread_announcements',0)}")

    print("\n" + "="*60)
    print("  🎉  Canvas API 통합 테스트 완료!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
