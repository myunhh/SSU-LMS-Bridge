# backend/app/adapter/assignments.py
# 과제 목록 조회
"""과제 목록 + 마감일 조회"""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from .canvas_client import CanvasClient


class Assignment(BaseModel):
    id: int
    course_id: int
    title: str
    due_at: Optional[str] = None
    points_possible: Optional[float] = None
    submission_types: List[str] = []
    html_url: str = ""
    description_snippet: str = ""

    class Config:
        extra = "ignore"

    @property
    def due_date(self) -> Optional[datetime]:
        if self.due_at:
            return datetime.fromisoformat(self.due_at.replace("Z", "+00:00"))
        return None

    @property
    def is_past_due(self) -> bool:
        d = self.due_date
        return d is not None and d < datetime.now(d.tzinfo)


async def list_assignments(client: CanvasClient, course_id: int) -> List[Assignment]:
    params = {"per_page": 100, "order_by": "due_at"}
    try:
        raw = await client.get(f"/courses/{course_id}/assignments", params=params)
    except Exception:
        raw = await client.get(f"/courses/{course_id}/assignments", params=params, use_canvas=True)

    items = raw if isinstance(raw, list) else raw.get("assignments", raw.get("data", []))

    return [
        Assignment(
            id=a["id"],
            course_id=course_id,
            title=a.get("name", ""),
            due_at=a.get("due_at"),
            points_possible=a.get("points_possible"),
            submission_types=a.get("submission_types", []),
            html_url=a.get("html_url", ""),
            description_snippet=(a.get("description") or "")[:200],
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
