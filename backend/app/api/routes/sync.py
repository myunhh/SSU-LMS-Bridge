# backend/app/api/routes/sync.py
# 동기화 라우트
# ──────────────────────────────────────────────────────────────────────────────
#   POST /api/sync         → SyncResult  (세션 갱신 + Canvas 수집)
#   GET  /api/sync/status  → { running, lastSyncAt }
#
# 흐름:
#   1) 세션 파일 존재 확인 (없으면 503 — 먼저 로그인)
#   2) auth.load_session() 으로 세션 유효성 검증 + 쿠키 연장 (← auth.py 호출)
#   3) CanvasClient 로 강의/과제/공지 수집, 개수를 SyncResult 로 반환
#   (Notion / Obsidian 반영은 🅲 단계에서 추가)
# ──────────────────────────────────────────────────────────────────────────────
from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from app.adapter.assignments import list_all_deadlines
from app.adapter.auth import SSULMSAuthPlaywright
from app.adapter.canvas_client import CanvasClient
from app.adapter.courses import list_courses
from app.adapter.notices import list_notices
from app.config import settings
from app.logger import logger
from app.models import SyncResult

router = APIRouter()

# 프로세스 메모리 상의 마지막 동기화 상태 (재시작 시 초기화 — 영속화는 추후 DB)
_state: dict = {"running": False, "last_sync_at": None}


@router.post("/sync", response_model=SyncResult)
async def trigger_sync() -> SyncResult:
    path = settings.session_cache_abspath
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LMS 세션이 없습니다. 먼저 로그인하세요.",
        )

    _state["running"] = True
    errors: list[str] = []
    courses = []
    assignments = []
    notices = []

    try:
        # 1) 세션 로드 + 연장 (auth.py)
        path.parent.mkdir(parents=True, exist_ok=True)
        auth = SSULMSAuthPlaywright(
            session_file=str(path),
            headless=settings.playwright_headless,
        )
        logger.info("[Sync] 세션 검증/연장 중…")
        ok = await auth.load_session()
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="LMS 세션이 만료되었습니다. 다시 로그인해주세요.",
            )

        # 2) Canvas 데이터 수집
        async with CanvasClient(session_file=str(path)) as client:
            courses = await list_courses(client)
            course_ids = [c.id for c in courses]
            logger.info(f"[Sync] 강의 {len(courses)}개 — 과제/공지 수집")

            try:
                assignments = await list_all_deadlines(client, course_ids)
            except Exception as e:
                errors.append(f"assignments: {e}")

            for cid in course_ids:
                try:
                    notices.extend(await list_notices(client, cid))
                except Exception as e:
                    errors.append(f"notices[{cid}]: {e}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[Sync] 실패")
        errors.append(str(e))
    finally:
        _state["running"] = False

    result = SyncResult(
        success=len(errors) == 0,
        courses=len(courses),
        assignments=len(assignments),
        notices=len(notices),
        materials=0,  # 자료/파일 다운로드는 🅲 단계
        errors=errors,
    )
    _state["last_sync_at"] = result.synced_at
    logger.info(
        f"[Sync] 완료 — 강의 {result.courses} · 과제 {result.assignments} · "
        f"공지 {result.notices} · 오류 {len(errors)}"
    )
    return result


@router.get("/sync/status")
async def sync_status():
    last = _state["last_sync_at"]
    return {
        "running": _state["running"],
        "lastSyncAt": last.isoformat() if isinstance(last, datetime) else None,
    }
