# backend/app/adapter/assignments.py
# 과제 목록 조회
"""과제 목록 + 마감일 조회"""
from typing import List, Set
from .canvas_client import CanvasClient
from ..models import Assignment


async def _get_submitted_ids(client: CanvasClient, course_id: int) -> Set[int]:
    """제출 완료된 과제 ID 집합 반환"""
    try:
        subs = await client.get(
            f"/courses/{course_id}/submissions",
            params={"student_ids[]": "self", "per_page": 100},
            use_canvas=True,
        )
        if not isinstance(subs, list):
            subs = subs.get("data", [])
        return {
            s["assignment_id"]
            for s in subs
            if s.get("workflow_state") not in ("unsubmitted", None)
        }
    except Exception:
        return set()


async def list_assignments(client: CanvasClient, course_id: int) -> List[Assignment]:
    params = {"per_page": 100, "order_by": "due_at"}
    try:
        raw = await client.get(f"/courses/{course_id}/assignments", params=params)
    except Exception:
        raw = await client.get(f"/courses/{course_id}/assignments", params=params, use_canvas=True)

    items = raw if isinstance(raw, list) else raw.get("assignments", raw.get("data", []))

    submitted_ids = await _get_submitted_ids(client, course_id)

    return [
        Assignment(
            id=a["id"],
            course_id=course_id,
            title=a.get("name", ""),
            due_at=a.get("due_at"),
            points_possible=a.get("points_possible"),
            submission_types=a.get("submission_types", []),
            html_url=a.get("html_url", ""),
            description=a.get("description") or "",  # ✅ 전체 본문
            submitted=a["id"] in submitted_ids,
        )
        for a in items if a.get("id")
    ]


async def list_all_deadlines(client: CanvasClient, course_ids: List[int]) -> List[Assignment]:
    all_assignments = []
    for cid in course_ids:
        try:
            all_assignments.extend(await list_assignments(client, cid))
        except Exception:
            continue
    return sorted(all_assignments, key=lambda a: a.due_at or "9999")
