# backend/app/api/routes/assignments.py
# 과제 조회 라우트
# ──────────────────────────────────────────────────────────────────────────────
#   GET /api/courses/{id}/assignments → Assignment[]  (해당 강의 과제)
#   GET /api/assignments/todos        → Assignment[]  (모든 강의 마감 통합, 마감일순)
# ──────────────────────────────────────────────────────────────────────────────
from fastapi import APIRouter, Depends

from app.adapter.assignments import list_all_deadlines, list_assignments
from app.adapter.canvas_client import CanvasClient
from app.adapter.courses import list_course_ids
from app.api.deps import get_canvas_client
from app.models import Assignment

router = APIRouter()


@router.get("/courses/{course_id}/assignments", response_model=list[Assignment])
async def get_assignments(course_id: int, client: CanvasClient = Depends(get_canvas_client)):
    return await list_assignments(client, course_id)


@router.get("/assignments/todos", response_model=list[Assignment])
async def get_todos(client: CanvasClient = Depends(get_canvas_client)):
    # 전 강의 마감 통합. ID 만 필요하므로 경량 조회 사용 (교수/진도 N+1 회피).
    course_ids = await list_course_ids(client)
    return await list_all_deadlines(client, course_ids)
