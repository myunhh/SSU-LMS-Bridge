# backend/app/api/routes/notices.py
# 공지사항 조회 라우트
# ──────────────────────────────────────────────────────────────────────────────
#   GET /api/courses/{id}/notices     → Notice[]
#   GET /api/courses/{id}/discussions → Notice[]  (일반 토론, 공지와 분리)
# ──────────────────────────────────────────────────────────────────────────────
from fastapi import APIRouter, Depends

from app.adapter.canvas_client import CanvasClient
from app.adapter.courses import list_course_ids
from app.adapter.notices import list_all_notices, list_discussions, list_notices
from app.api.deps import get_canvas_client
from app.models import Notice

router = APIRouter()


@router.get("/notices", response_model=list[Notice])
async def get_all_notices(client: CanvasClient = Depends(get_canvas_client)):
    """전 과목 통합 공지 (대시보드 초기 로드용)."""
    course_ids = await list_course_ids(client)
    return await list_all_notices(client, course_ids)


@router.get("/courses/{course_id}/notices", response_model=list[Notice])
async def get_notices(course_id: int, client: CanvasClient = Depends(get_canvas_client)):
    return await list_notices(client, course_id)


@router.get("/courses/{course_id}/discussions", response_model=list[Notice])
async def get_discussions(course_id: int, client: CanvasClient = Depends(get_canvas_client)):
    """과목 토론 목록 (공지 탭과 분리 — only_announcements 미지정)."""
    return await list_discussions(client, course_id)
