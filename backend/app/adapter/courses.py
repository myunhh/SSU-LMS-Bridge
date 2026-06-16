# backend/app/adapter/courses.py
# 수강 강의 목록 조회
"""수강 과목 목록 조회"""
import asyncio

from app.logger import logger

from ..models import Course
from .canvas_client import CanvasClient
from .notices import is_session_unauthorized

# 과목 동시 조회 상한 — 한 학기 과목 수는 작지만 폭주 방지용 세마포어.
# httpx.AsyncClient 는 동시 요청에 안전하므로 과목 루프를 병렬화한다 (#2).
_COURSE_CONCURRENCY = 5


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
    except Exception as e:
        if is_session_unauthorized(e):
            raise  # 세션 만료는 전역 핸들러(→ 401 '재로그인 필요')로 전파
        logger.debug(f"과목 {course_id} 교수명 조회 실패: {e!r}")
        return ""


async def _get_progress_and_materials(
    client: CanvasClient, course_id: int
) -> tuple[float | None, int]:
    """모듈 1회 호출로 (진도율 0.0~100.0, 모듈 아이템 총 개수) 동시 계산.

    진도율과 자료 수가 같은 modules?include[]=items 응답에서 나오므로
    호출을 합쳐 N+1 을 늘리지 않는다 (#39).
    """
    try:
        # Link 헤더 페이지네이션 추적 — 모듈 100건 초과 시 진도율/자료 수 왜곡 방지
        prog = await client.get_all_pages(
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
            return None, 0
        return round(completed / total * 100, 1), total
    except Exception as e:
        if is_session_unauthorized(e):
            raise
        logger.debug(f"과목 {course_id} 모듈(진도/자료 수) 조회 실패: {e!r}")
        return None, 0


async def list_course_ids(client: CanvasClient) -> list[int]:
    """강의 ID 목록만 가볍게 조회 (교수/진도 N+1 호출 없이 1~2콜).

    todos·통합공지처럼 ID 만 필요한 곳에서 list_courses 대신 사용.
    """
    params = {"enrollment_state": "active", "per_page": 50}
    try:
        raw = await client.get("/courses", params=params)
    except Exception as e:
        # LearningX(Bearer)와 Canvas(쿠키)는 인증이 독립적이므로 401 이어도 폴백 시도.
        logger.debug(f"LearningX 강의 ID 목록 실패 → Canvas 폴백: {e!r}")
        raw = await client.get("/courses", params=params, use_canvas=True)
    items = raw if isinstance(raw, list) else raw.get("courses", raw.get("data", []))
    return [it["id"] for it in items if it.get("id")]


async def list_courses(client: CanvasClient) -> list[Course]:
    params = {
        "enrollment_state": "active",
        "per_page": 50,
        "include[]": ["term", "total_students", "course_progress"],
    }

    try:
        raw = await client.get("/courses", params=params)
    except Exception as e:
        logger.debug(f"LearningX 강의 목록 실패 → Canvas 폴백: {e!r}")
        raw = await client.get("/courses", params=params, use_canvas=True)

    items = raw if isinstance(raw, list) else raw.get("courses", raw.get("data", []))

    # 출석율 캐시(perform_sync 가 출결현황에서 계산해 둔 값)를 한 번만 읽는다.
    # SSU 의 'progress' 는 출석율로 표시한다(출석 일수/전체 일수). 캐시가 있으면 그 값을
    # 우선 쓰고, 없으면(최초 동기화 전 등) 기존 Canvas 진도 로직으로 폴백한다.
    # (지연 import — 서비스 계층 순환 의존 회피, cached 읽기는 네트워크 0)
    from app.services.attendance_service import load_cache as _load_attendance
    attendance_cache = _load_attendance()

    sem = asyncio.Semaphore(_COURSE_CONCURRENCY)

    async def _build_course(item: dict) -> Course:
        course_id = item.get("id")
        async with sem:
            # 과목당 추가 호출 2개(교수명 + 모듈)를 한 gather 로 병렬 실행.
            # _get_professor/_get_progress_and_materials 내부에서 세션 만료(401)는
            # 이미 re-raise 하므로, return_exceptions 없이 gather 가 401 을 그대로
            # 전파한다 (재로그인 유도 정책 유지). 콜 수는 여전히 과목당 정확히 2.
            professor, (module_progress, materials) = await asyncio.gather(
                _get_professor(client, course_id),
                _get_progress_and_materials(client, course_id),
            )

        # 진도율(=출석율) 우선순위: 출결현황 출석율 캐시 > Canvas course_progress > 모듈 진도.
        att = attendance_cache.get(str(course_id))
        if isinstance(att, dict) and att.get("rate") is not None:
            progress = att["rate"]
        else:
            cp = item.get("course_progress", {})
            if cp and cp.get("requirement_count"):
                completed = cp.get("requirement_completed_count", 0)
                total = cp.get("requirement_count", 1)
                progress = round(completed / total * 100, 1)
            else:
                progress = module_progress

        return Course(
            id=course_id,
            name=item.get("name", item.get("course_name", "")),
            course_code=item.get("course_code", ""),
            term=item.get("term", {}).get("name", "") if isinstance(item.get("term"), dict) else "",
            professor=professor,
            credits=item.get("credits"),
            progress=progress,
            materials=materials,           # ✅ 강의 모듈 아이템 총 개수 (#39)
        )

    # 과목 루프 병렬화 — 첫 401 이 gather 밖으로 전파되어 전역 핸들러에 도달한다.
    return list(await asyncio.gather(*(_build_course(item) for item in items)))
