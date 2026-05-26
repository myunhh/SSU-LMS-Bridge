# backend/app/api/routes/sync.py
# 동기화 라우트 + 공용 동기화 로직
# ──────────────────────────────────────────────────────────────────────────────
#   POST /api/sync         → SyncResult  (수동 동기화)
#   GET  /api/sync/status  → { running, lastSyncAt }
#   perform_sync()         → 핵심 로직 (라우트 + APScheduler 예약 작업 공용)
#   run_scheduled_sync()   → 스케줄러용 래퍼 (예외를 로그로만 처리)
#
# 흐름:
#   1) 세션 파일 존재 확인 (없으면 SyncSessionError 503)
#   2) auth.load_session() 으로 세션 검증 + 쿠키 연장 (← auth.py)
#   3) CanvasClient 로 강의/과제/공지 수집
#   4) Notion 이 설정돼 있으면 공지·과제를 Notion DB 로 upsert
# ──────────────────────────────────────────────────────────────────────────────
from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.adapter.assignments import list_all_deadlines
from app.adapter.auth import SSULMSAuthPlaywright
from app.adapter.canvas_client import CanvasClient
from app.adapter.courses import list_courses
from app.adapter.notices import list_all_notices
from app.config import settings
from app.logger import logger
from app.models import SyncResult
from app.services.notion_services import sync_notion

router = APIRouter()

# 프로세스 메모리 상의 마지막 동기화 상태 (재시작 시 초기화)
_state: dict = {"running": False, "last_sync_at": None}


class SyncSessionError(Exception):
    """세션 없음/만료 — 재로그인 필요. (HTTP status + detail 운반)"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _is_configured(*vals) -> bool:
    """값이 실제로 채워졌는지 (빈값/placeholder 'xxxx' 제외)."""
    return all(v and "xxxx" not in str(v).lower() for v in vals)


async def perform_sync() -> SyncResult:
    """동기화 핵심 로직 (수동/예약 공용). 세션 문제는 SyncSessionError 로 raise."""
    path = settings.session_cache_abspath
    if not path.exists():
        raise SyncSessionError(503, "LMS 세션이 없습니다. 먼저 로그인하세요.")

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
            raise SyncSessionError(401, "LMS 세션이 만료되었습니다. 다시 로그인해주세요.")

        # 2) Canvas 데이터 수집
        async with CanvasClient(session_file=str(path)) as client:
            courses = await list_courses(client)
            course_ids = [c.id for c in courses]
            logger.info(f"[Sync] 강의 {len(courses)}개 — 과제/공지 수집")

            try:
                assignments = await list_all_deadlines(client, course_ids)
            except Exception as e:
                errors.append(f"assignments: {e}")

            try:
                notices = await list_all_notices(client, course_ids)
            except Exception as e:
                errors.append(f"notices: {e}")

        # 3) Notion push (설정된 경우에만)
        if _is_configured(settings.notion_token, settings.notion_root_page_id):
            try:
                name_map = {c.id: c.name for c in courses}
                notice_payload = [
                    {
                        "title": n.title,
                        "course_name": name_map.get(n.course_id, ""),
                        "date": n.posted_at,
                        "pinned": False,
                        "unread": not n.is_read,
                    }
                    for n in notices if n.posted_at
                ]
                assign_payload = [
                    {
                        "title": a.title,
                        "course_name": name_map.get(a.course_id, ""),
                        "due": a.due_at,
                        "type": (a.submission_types[0] if a.submission_types else "기타"),
                        "weight": a.points_possible or 0,
                        "submitted": a.submitted,
                    }
                    for a in assignments if a.due_at
                ]
                pushed = await sync_notion(
                    notices=notice_payload,
                    assignments=assign_payload,
                    notion_mcp_url=settings.notion_mcp_url,
                    notion_token=settings.notion_token,
                )
                logger.info(
                    f"[Sync] Notion push — 공지 {pushed.get('notices_added')} · "
                    f"과제 {pushed.get('assignments_added')} 신규"
                )
            except Exception as e:
                logger.exception("[Sync] Notion push 실패")
                errors.append(f"notion: {e}")
        else:
            logger.info("[Sync] Notion 미설정 → push 건너뜀")

    except SyncSessionError:
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
        materials=0,  # Obsidian Vault 동기화는 추후
        errors=errors,
    )
    _state["last_sync_at"] = result.synced_at
    logger.info(
        f"[Sync] 완료 — 강의 {result.courses} · 과제 {result.assignments} · "
        f"공지 {result.notices} · 오류 {len(errors)}"
    )
    return result


async def run_scheduled_sync() -> None:
    """APScheduler 예약 작업용 래퍼. 예외를 밖으로 던지지 않고 로그로만 남긴다."""
    logger.info("[Sync] 예약 동기화 시작")
    try:
        await perform_sync()
    except SyncSessionError as e:
        logger.warning(f"[Sync] 예약 동기화 건너뜀 — {e.detail}")
    except Exception:
        logger.exception("[Sync] 예약 동기화 실패")


@router.post("/sync", response_model=SyncResult)
async def trigger_sync() -> SyncResult:
    try:
        return await perform_sync()
    except SyncSessionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/sync/status")
async def sync_status():
    last = _state["last_sync_at"]
    return {
        "running": _state["running"],
        "lastSyncAt": last.isoformat() if isinstance(last, datetime) else None,
    }
