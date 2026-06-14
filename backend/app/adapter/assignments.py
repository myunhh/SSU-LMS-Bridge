# backend/app/adapter/assignments.py
# 과제 목록 조회
"""과제 목록 + 마감일 조회"""
import asyncio

from app.logger import logger

from ..models import Assignment
from .canvas_client import CanvasClient
from .notices import html_to_text, is_session_unauthorized

# 과목별 과제 동시 조회 상한 (httpx.AsyncClient 는 동시 요청 안전, #2)
_DEADLINE_CONCURRENCY = 5


async def _get_submitted_ids(client: CanvasClient, course_id: int) -> set[int]:
    """제출 완료된 과제 ID 집합 반환"""
    try:
        # Link 헤더 페이지네이션 추적 — 100건 초과 시 제출 여부 누락 방지
        # ⚠️ /courses/:id/submissions 라우트는 Canvas REST 에 없음(404) —
        #    여러 과제 통합 조회는 /courses/:id/students/submissions 가 공식 경로.
        subs = await client.get_all_pages(
            f"/courses/{course_id}/students/submissions",
            params={"student_ids[]": "self", "per_page": 100},
            use_canvas=True,
        )
        if not isinstance(subs, list):
            subs = subs.get("data", [])
        return {
            s["assignment_id"]
            for s in subs
            if s.get("workflow_state") not in ("unsubmitted", None)
        }
    except Exception as e:
        if is_session_unauthorized(e):
            raise  # 세션 만료는 삼키지 않고 전역 핸들러(→ 401 '재로그인 필요')로 전파
        logger.debug(f"과목 {course_id} 제출 현황 조회 실패 (미제출 처리): {e!r}")
        return set()


async def list_assignments(client: CanvasClient, course_id: int) -> list[Assignment]:
    params = {"per_page": 100, "order_by": "due_at"}
    try:
        raw = await client.get(f"/courses/{course_id}/assignments", params=params)
    except Exception as e:
        # LearningX(Bearer)와 Canvas(쿠키)는 인증이 독립적이므로 401 이어도 폴백 시도.
        logger.debug(f"과목 {course_id} LearningX 과제 실패 → Canvas 폴백: {e!r}")
        raw = await client.get_all_pages(
            f"/courses/{course_id}/assignments", params=params, use_canvas=True
        )

    items = raw if isinstance(raw, list) else raw.get("assignments", raw.get("data", []))

    submitted_ids = await _get_submitted_ids(client, course_id)

    return [
        Assignment(
            id=a["id"],
            course_id=course_id,
            title=a.get("name", ""),
            due_at=a.get("due_at"),
            points_possible=a.get("points_possible"),
            submission_types=a.get("submission_types", []),
            html_url=a.get("html_url", ""),
            description=a.get("description") or "",                    # ✅ 전체 본문 (HTML 원문)
            description_text=html_to_text(a.get("description") or ""),  # ✅ 평문 (최대 8000자)
            submitted=a["id"] in submitted_ids,
        )
        for a in items if a.get("id")
    ]


async def list_all_deadlines(client: CanvasClient, course_ids: list[int]) -> list[Assignment]:
    # 과목별 과제 조회를 병렬화. return_exceptions=True 로 한 과목 실패가 전체를
    # 중단시키지 않게 하되, 세션 만료(401)만 골라 re-raise 해 401 전파 정책을 유지한다.
    sem = asyncio.Semaphore(_DEADLINE_CONCURRENCY)

    async def _fetch(cid: int) -> list[Assignment]:
        async with sem:
            return await list_assignments(client, cid)

    results = await asyncio.gather(
        *(_fetch(cid) for cid in course_ids), return_exceptions=True
    )

    all_assignments: list[Assignment] = []
    for cid, result in zip(course_ids, results, strict=True):
        if isinstance(result, BaseException):
            if is_session_unauthorized(result):
                # 세션 만료 시 조용한 부분/빈 결과 대신 401 로 전파 (재로그인 유도)
                raise result
            logger.warning(f"과목 {cid} 과제 조회 실패, 건너뜀: {result!r}")
            continue
        all_assignments.extend(result)
    return sorted(all_assignments, key=lambda a: a.due_at or "9999")
