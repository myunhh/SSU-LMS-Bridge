# backend/app/adapter/notices.py
# 공지사항 파싱
"""공지사항 조회"""
from typing import List
from .canvas_client import CanvasClient
from ..models import Notice


def _ctx_course_id(context_code: str) -> int:
    """'course_44176' → 44176"""
    if context_code and context_code.startswith("course_"):
        try:
            return int(context_code.split("_", 1)[1])
        except ValueError:
            return 0
    return 0


async def list_all_notices(client: CanvasClient, course_ids: List[int]) -> List[Notice]:
    """전 과목 공지를 한 번의 /announcements 호출로 통합 조회 (context_code 로 과목 구분)."""
    if not course_ids:
        return []
    params = {
        "context_codes[]": [f"course_{cid}" for cid in course_ids],
        "per_page": 100,
    }
    try:
        raw = await client.get("/announcements", params=params, use_canvas=True)
    except Exception:
        # 폴백: 과목별 개별 조회
        out: List[Notice] = []
        for cid in course_ids:
            try:
                out.extend(await list_notices(client, cid))
            except Exception:
                continue
        return out

    items = raw if isinstance(raw, list) else raw.get("data", [])
    result = []
    for n in items:
        if not n.get("id"):
            continue
        result.append(Notice(
            id=n["id"],
            course_id=_ctx_course_id(n.get("context_code", "")),
            title=n.get("title", ""),
            # Notice 모델 필드명은 `message` (전체 본문). 프론트가 미리보기로 잘라서 노출.
            message=n.get("message") or "",
            posted_at=n.get("posted_at", n.get("created_at")),
            author=n.get("author", {}).get("display_name", "") if isinstance(n.get("author"), dict) else "",
            html_url=n.get("html_url", ""),
            is_read=n.get("read_state") == "read",
        ))
    return result


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
            message=n.get("message") or "",          # ✅ 전체 본문
            posted_at=n.get("posted_at", n.get("created_at")),
            author=n.get("author", {}).get("display_name", "") if isinstance(n.get("author"), dict) else "",
            html_url=n.get("html_url", ""),
            is_read=n.get("read_state") == "read",
        )
        for n in items if n.get("id")
    ]
