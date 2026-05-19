# backend/app/adapter/materials.py
# 강의 자료(파일) 조회 및 다운로드
# backend/app/adapter/materials.py
# 강의 자료(파일) 조회 및 다운로드
"""주차별 강의 자료 조회"""
from typing import List
from .canvas_client import CanvasClient
from ..models import Material


async def list_materials(client: CanvasClient, course_id: int) -> List[Material]:
    try:
        modules = await client.get(
            f"/courses/{course_id}/modules",
            params={"per_page": 100},
            use_canvas=True,
        )
    except Exception:
        modules = await client.get(
            f"/courses/{course_id}/modules",
            params={"per_page": 100},
        )

    if not isinstance(modules, list):
        modules = modules.get("data", modules.get("modules", []))

    results = []
    for mod in modules:
        mod_id = mod.get("id")
        mod_name = mod.get("name", "")

        try:
            items = await client.get(
                f"/courses/{course_id}/modules/{mod_id}/items",
                params={"per_page": 100},
                use_canvas=True,
            )
        except Exception:
            try:
                items = await client.get(
                    f"/courses/{course_id}/modules/{mod_id}/items",
                    params={"per_page": 100},
                )
            except Exception:
                continue

        if not isinstance(items, list):
            items = items.get("data", [])

        for item in items:
            results.append(Material(
                id=item.get("id", 0),
                course_id=course_id,
                module_name=mod_name,
                title=item.get("title", ""),
                item_type=item.get("type", ""),
                url=item.get("url") or item.get("html_url") or item.get("external_url"),
                position=item.get("position", 0),
            ))

    return results
