# backend/app/adapter/grades.py
# 성적 조회 — Canvas enrollment 의 grades.
"""과목별 현재 성적(백분율) 조회.

Canvas `/users/self/enrollments?include[]=grades` 가 과목별 current_score 를 준다.
enrollment 에는 과목명이 없으므로 `/courses` 한 번으로 id→name 을 만들어 join 한다
(총 2콜). SSU 는 letter grade 를 보통 비워 두므로(null) 점수(%) 가 주 신호다.
"""
from app.logger import logger

from ..models import CourseGrade
from .canvas_client import CanvasClient
from .notices import is_session_unauthorized


async def list_grades(client: CanvasClient) -> list[CourseGrade]:
    """수강 과목별 현재 성적(CourseGrade) 목록. 점수 높은 순 정렬."""
    enr = await client.get(
        "/users/self/enrollments",
        params={
            "type[]": "StudentEnrollment",
            "state[]": "active",
            "include[]": "grades",
            "per_page": 50,
        },
        use_canvas=True,
    )
    enrollments = enr if isinstance(enr, list) else enr.get("data", [])

    # 과목 id→name (1콜). LearningX /courses 는 404 라 list_courses 처럼 Canvas 로 폴백한다.
    # 실패해도 성적은 내보내되 이름만 비운다.
    name_map: dict[int, str] = {}
    params = {"enrollment_state": "active", "per_page": 50}
    try:
        try:
            raw = await client.get("/courses", params=params)
        except Exception as e:
            if is_session_unauthorized(e):
                raise
            raw = await client.get("/courses", params=params, use_canvas=True)
        items = raw if isinstance(raw, list) else raw.get("courses", raw.get("data", []))
        name_map = {it["id"]: it.get("name", "") for it in items if it.get("id")}
    except Exception as e:
        if is_session_unauthorized(e):
            raise
        logger.debug(f"성적: 과목명 조회 실패(이름 생략): {e!r}")

    out: list[CourseGrade] = []
    for e in enrollments:
        cid = e.get("course_id")
        g = e.get("grades", {}) or {}
        out.append(CourseGrade(
            course_id=cid,
            course_name=name_map.get(cid, ""),
            current_score=g.get("current_score"),
            current_grade=g.get("current_grade"),
            final_score=g.get("final_score"),
            final_grade=g.get("final_grade"),
        ))
    # 점수 있는 과목을 점수 내림차순, 점수 없는 과목은 뒤로.
    out.sort(key=lambda c: (c.current_score is None, -(c.current_score or 0)))
    return out
