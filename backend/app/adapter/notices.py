# backend/app/adapter/notices.py
# 공지사항 파싱
"""공지사항 조회"""
from typing import List
from .canvas_client import CanvasClient
from ..models import Notice


async def list_notices(client: CanvasClient, course_id: int) -> List[Notice]:
    try:
        raw = await client.get(
            "/announcements",
            params={"context_codes[]": f"course_{course_id}", "per_page": 50},
            use_canvas=True,
        )
    except Exception:
        raw = await client.get(
            f"/courses/{course_id}/discussion_topics",
            params={"only_announcements": "true", "per_page": 50},
        )

    items = raw if isinstance(raw, list) else raw.get("data", [])

    return [
        Notice(
            id=n["id"],
            course_id=course_id,
            title=n.get("title", ""),
            message_snippet=(n.get("message") or "")[:300],
            posted_at=n.get("posted_at", n.get("created_at")),
            author=n.get("author", {}).get("display_name", "") if isinstance(n.get("author"), dict) else "",
            html_url=n.get("html_url", ""),
        )
        for n in items if n.get("id")
    ]
