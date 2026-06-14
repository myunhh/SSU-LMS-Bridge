# backend/app/api/routes/courses.py
# 강의 조회 라우트
# ──────────────────────────────────────────────────────────────────────────────
#   GET /api/courses              → Course[]   (수강 강의 목록)
#   GET /api/courses/{id}/modules → Material[] (주차별 강의 자료/모듈 아이템)
# ──────────────────────────────────────────────────────────────────────────────
from fastapi import APIRouter, Depends

from app.adapter.canvas_client import CanvasClient
from app.adapter.courses import list_courses
from app.adapter.materials import list_materials
from app.api.deps import get_canvas_client
from app.models import Course, Material

router = APIRouter()


@router.get("/courses", response_model=list[Course])
async def get_courses(client: CanvasClient = Depends(get_canvas_client)):
    return await list_courses(client)


@router.get("/courses/{course_id}/modules", response_model=list[Material])
async def get_course_modules(course_id: int, client: CanvasClient = Depends(get_canvas_client)):
    return await list_materials(client, course_id)
