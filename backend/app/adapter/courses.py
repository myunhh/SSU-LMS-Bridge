# backend/app/adapter/courses.py
# 수강 강의 목록 조회
"""수강 과목 목록 조회"""
from typing import List
from pydantic import BaseModel
from .canvas_client import CanvasClient


class Course(BaseModel):
    id: int
    name: str
    course_code: str = ""
    term: str = ""

    class Config:
        extra = "ignore"


async def list_courses(client: CanvasClient) -> List[Course]:
    params = {"enrollment_state": "active", "per_page": 50}

    try:
        raw = await client.get("/courses", params=params)
    except Exception:
        raw = await client.get("/courses", params=params, use_canvas=True)

    items = raw if isinstance(raw, list) else raw.get("courses", raw.get("data", []))

    courses = []
    for item in items:
        courses.append(Course(
            id=item.get("id"),
            name=item.get("name", item.get("course_name", "")),
            course_code=item.get("course_code", ""),
            term=item.get("term", {}).get("name", "") if isinstance(item.get("term"), dict) else "",
        ))
    return courses
