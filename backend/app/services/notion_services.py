from loguru import logger
from app.mcp_client.base import MCPClientBase

NOTICE_DB_PROPS = {
    "제목": {"title": {}}, "과목": {"select": {}},
    "날짜": {"date": {}}, "중요": {"checkbox": {}}, "읽음": {"checkbox": {}},
}
ASSIGNMENT_DB_PROPS = {
    "제목": {"title": {}}, "과목": {"select": {}}, "마감일": {"date": {}},
    "유형": {"select": {}}, "비중(%)": {"number": {"format": "percent"}},
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

    # DB 확보
    notice_db_id = await mcp.call_tool("ensure_db", {
        "title": "공지사항", "properties": NOTICE_DB_PROPS,
    })
    assign_db_id = await mcp.call_tool("ensure_db", {
        "title": "과제", "properties": ASSIGNMENT_DB_PROPS,
    })

    # 공지 upsert
    notice_added = 0
    for n in notices:
        result = await mcp.call_tool("upsert_notice", {
            "db_id": notice_db_id, "title": n["title"],
            "course_name": n["course_name"], "date": n["date"],
            "pinned": n.get("pinned", False), "unread": n.get("unread", True),
        })
        if result == "created":
            notice_added += 1

    # 과제 upsert
    assign_added = 0
    for a in assignments:
        result = await mcp.call_tool("upsert_assignment", {
            "db_id": assign_db_id, "title": a["title"],
            "course_name": a["course_name"], "due": a["due"],
            "type": a.get("type", "기타"), "weight": a.get("weight", 0),
            "submitted": a.get("submitted", False),
        })
        if result == "created":
            assign_added += 1

    logger.info(f"[Notion] 공지 {notice_added}건 · 과제 {assign_added}건 추가")
    return {"notices_added": notice_added, "assignments_added": assign_added}
