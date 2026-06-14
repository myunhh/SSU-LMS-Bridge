from loguru import logger

from app.mcp_client.base import MCPClientBase

NOTICE_DB_PROPS = {
    "제목": {"title": {}}, "과목": {"select": {}},
    "날짜": {"date": {}}, "중요": {"checkbox": {}}, "읽음": {"checkbox": {}},
}
ASSIGNMENT_DB_PROPS = {
    "제목": {"title": {}}, "과목": {"select": {}}, "마감일": {"date": {}},
    # '배점'(points_possible, 예: 100점)을 그대로 저장 — percent 포맷이 아니라
    # 일반 number 다 (#8: 배점을 비중(%)으로 오해해 /100 하던 왜곡 제거).
    "유형": {"select": {}}, "배점": {"number": {}},
    "제출완료": {"checkbox": {}},
}


async def sync_notion(
    notices: list,
    assignments: list,
    notion_mcp_url: str,
    notion_token: str,
) -> dict:
    mcp = MCPClientBase(
        server_url=notion_mcp_url,
        headers={"Authorization": f"Bearer {notion_token}"},
    )

    notice_added = 0
    assign_added = 0
    failed = 0

    # 단일 SSE 세션으로 전체 push 처리 — 항목마다 재연결하지 않는다.
    async with mcp.session() as s:
        # DB 확보 — 실패하면 전체 push 가 무의미하므로 예외를 그대로 전파
        # (perform_sync 가 "notion: ..." 오류로 수거)
        notice_db_id = await mcp.call_tool_in(s, "ensure_db", {
            "title": "공지사항", "properties": NOTICE_DB_PROPS,
        })
        assign_db_id = await mcp.call_tool_in(s, "ensure_db", {
            "title": "과제", "properties": ASSIGNMENT_DB_PROPS,
        })

        # 공지 upsert — 한 건 실패해도 나머지 항목은 계속 진행
        for n in notices:
            try:
                result = await mcp.call_tool_in(s, "upsert_notice", {
                    "db_id": notice_db_id, "title": n["title"],
                    "course_name": n["course_name"], "date": n["date"],
                    "pinned": n.get("pinned", False), "unread": n.get("unread", True),
                })
            except Exception as e:
                logger.warning(f"[Notion] upsert 실패 ({n['title']}): {e}")
                failed += 1
                continue
            if result == "created":
                notice_added += 1

        # 과제 upsert — 한 건 실패해도 나머지 항목은 계속 진행
        for a in assignments:
            try:
                result = await mcp.call_tool_in(s, "upsert_assignment", {
                    "db_id": assign_db_id, "title": a["title"],
                    "course_name": a["course_name"], "due": a["due"],
                    "type": a.get("type", "기타"), "weight": a.get("weight", 0),
                    "submitted": a.get("submitted", False),
                })
            except Exception as e:
                logger.warning(f"[Notion] upsert 실패 ({a['title']}): {e}")
                failed += 1
                continue
            if result == "created":
                assign_added += 1

    logger.info(
        f"[Notion] 공지 {notice_added}건 · 과제 {assign_added}건 추가 · 실패 {failed}건"
    )
    return {
        "notices_added": notice_added,
        "assignments_added": assign_added,
        "failed": failed,
    }
