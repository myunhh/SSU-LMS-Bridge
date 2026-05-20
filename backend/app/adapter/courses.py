# backend/app/adapter/courses.py
# 수강 강의 목록 조회
"""수강 과목 목록 조회"""
from typing import List, Optional
from .canvas_client import CanvasClient
from ..models import Course


async def _get_professor(client: CanvasClient, course_id: int) -> str:
    """강의 담당 교수명 반환"""
    try:
        teachers = await client.get(
            f"/courses/{course_id}/users",
            params={"enrollment_type[]": "teacher", "per_page": 10},
            use_canvas=True,
        )
        if not isinstance(teachers, list):
            teachers = teachers.get("data", [])
        names = [t.get("name", "") for t in teachers if t.get("name")]
        return ", ".join(names)
    except Exception:
        return ""


async def _get_progress(client: CanvasClient, course_id: int) -> Optional[float]:
    """강의 진도율 반환 (0.0 ~ 100.0)"""
    try:
        prog = await client.get(
            f"/courses/{course_id}/modules",
            params={"per_page": 100, "include[]": "items"},
            use_canvas=True,
        )
        if not isinstance(prog, list):
            prog = prog.get("data", [])
        total = sum(len(m.get("items", [])) for m in prog)
        completed = sum(
            1
            for m in prog
            for item in m.get("items", [])
            if item.get("completion_requirement", {}).get("completed")
        )
        if total == 0:
            return None
        return round(completed / total * 100, 1)
    except Exception:
        return None


async def list_courses(client: CanvasClient) -> List[Course]:
    params = {
        "enrollment_state": "active",
        "per_page": 50,
        "include[]": ["term", "total_students", "course_progress"],
    }

    try:
        raw = await client.get("/courses", params=params)
    except Exception:
        raw = await client.get("/courses", params=params, use_canvas=True)

    items = raw if isinstance(raw, list) else raw.get("courses", raw.get("data", []))

    courses = []
    for item in items:
        course_id = item.get("id")

        # 교수명
        professor = await _get_professor(client, course_id)

        # 진도율 (course_progress가 있으면 사용, 없으면 modules API 호출)
        cp = item.get("course_progress", {})
        if cp and cp.get("requirement_count"):
            completed = cp.get("requirement_completed_count", 0)
            total = cp.get("requirement_count", 1)
            progress = round(completed / total * 100, 1)
        else:
            progress = await _get_progress(client, course_id)

        courses.append(Course(
            id=course_id,
            name=item.get("name", item.get("course_name", "")),
            course_code=item.get("course_code", ""),
            term=item.get("term", {}).get("name", "") if isinstance(item.get("term"), dict) else "",
            professor=professor,           # ✅ 추가
            credits=item.get("credits"),   # ✅ 추가
            progress=progress,             # ✅ 추가
        ))
    return courses
