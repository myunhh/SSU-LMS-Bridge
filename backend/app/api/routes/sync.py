# backend/app/api/routes/sync.py
# 동기화 라우트 + 공용 동기화 로직
# ──────────────────────────────────────────────────────────────────────────────
#   POST /api/sync         → SyncResult  (수동 동기화)
#   GET  /api/sync/status  → { running, lastSyncAt, syncHour }
#   perform_sync()         → 핵심 로직 (라우트 + APScheduler 예약 작업 공용)
#   run_scheduled_sync()   → 스케줄러용 래퍼 (예외를 로그로만 처리)
#
# 흐름:
#   1) 세션 파일 존재 확인 (없으면 SyncSessionError 503)
#   2) auth.load_session() 으로 세션 검증 + 쿠키 연장 (← auth.py)
#   3) CanvasClient 로 강의/과제/공지 수집
#   4) Notion 이 설정돼 있으면 공지·과제를 Notion DB 로 upsert
#   5) Obsidian 이 설정돼 있으면 공지·과제를 Vault 에 markdown 노트로 push
# ──────────────────────────────────────────────────────────────────────────────
from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.adapter.assignments import list_all_deadlines
from app.adapter.auth import SSULMSAuthPlaywright
from app.adapter.canvas_client import CanvasClient
from app.adapter.courses import list_courses
from app.adapter.materials import list_all_materials, material_type_label
from app.adapter.notices import list_all_notices
from app.config import is_configured, settings
from app.logger import logger
from app.models import SyncResult, submission_type_label
from app.services import notify_service
from app.services.notion_services import sync_notion
from app.services.vault_service import sync_obsidian

router = APIRouter()

# 프로세스 메모리 상의 마지막 동기화 상태 (재시작 시 초기화)
_state: dict = {"running": False, "last_sync_at": None}


def is_sync_running() -> bool:
    """동기화 진행 중 여부 — lms.py 예약 세션 갱신이 private _state 를 직접 안 읽도록."""
    return _state["running"]


class SyncSessionError(Exception):
    """동기화 불가 상태(세션 없음/만료, 동시 실행 등) — HTTP status + detail 운반."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


async def perform_sync() -> SyncResult:
    """동기화 핵심 로직 (수동/예약 공용). 세션 문제는 SyncSessionError 로 raise."""
    # 동시 실행 가드 — 여기서 running=True 설정 전(첫 await 이전)에 raise 하므로
    # 단일 이벤트 루프에서 원자적이고, 아래 finally 가 진행 중인 다른 실행의
    # 플래그를 되돌리는 일도 없다 (수동 연타 / 예약 동기화 중복 방지).
    if _state["running"]:
        raise SyncSessionError(409, "동기화가 이미 진행 중입니다.")

    path = settings.session_cache_abspath
    if not path.exists():
        raise SyncSessionError(503, "LMS 세션이 없습니다. 먼저 로그인하세요.")

    _state["running"] = True
    errors: list[str] = []
    courses = []
    assignments = []
    notices = []
    materials = []

    try:
        # 1) 세션 로드 + 연장 (auth.py)
        # 세션 디렉토리는 소유자 전용(0700) — 기존 디렉토리 권한은 안 바뀌는 한계가
        # 있으므로(exist_ok=True), 파일 단위 0600(auth._save_session)이 실질 방어선.
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        auth = SSULMSAuthPlaywright(
            session_file=str(path),
            headless=settings.playwright_headless,
        )
        logger.info("[Sync] 세션 검증/연장 중…")
        try:
            ok = await auth.load_session()
        except Exception as e:
            # 인프라 오류(Chromium 미설치, 네트워크 단절 등)는 세션 만료(401)와
            # 구분해 503 으로 — 아래 광역 except 에 삼켜지지 않게 명시 변환.
            logger.exception("[Sync] 세션 검증 중 서버 오류")
            raise SyncSessionError(503, "LMS 세션 검증 중 서버 오류가 발생했습니다.") from e
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

            # 주차별 강의자료 메타(주차·제목·유형·LMS 딥링크) — Obsidian 강의자료 노트용.
            # 본문 파일은 LTI 뒤라 못 받지만 메타+딥링크로 주차별 인덱스를 만든다.
            try:
                materials = await list_all_materials(client, course_ids)
            except Exception as e:
                errors.append(f"materials: {e}")

        # push payload 조립 — Notion·Obsidian 두 push 가 공유한다.
        # (sync_notion / sync_obsidian 은 각자 자기 키만 읽으므로 추가 키는 무해)
        name_map = {c.id: c.name for c in courses}
        notice_payload = [
            {
                "title": n.title,
                "course_name": name_map.get(n.course_id, ""),
                "date": n.posted_at,
                "pinned": n.pinned,
                "unread": not n.is_read,
                "text": n.message_text,
            }
            for n in notices if n.posted_at
        ]
        assign_payload = [
            {
                "title": a.title,
                "course_name": name_map.get(a.course_id, ""),
                "due": a.due_at,
                # 원시 Canvas 코드(online_upload 등)를 앱 화면과 통일된 한글
                # 라벨로 매핑해 Notion '유형'·Obsidian 노트에 같은 라벨을 보낸다 (#12).
                "type": submission_type_label(
                    a.submission_types[0] if a.submission_types else None
                ),
                # ⚠️ points_possible 은 '배점'(예: 100점)이지 성적 비중(%)이 아니다 (#8).
                # 원래 값 그대로 Notion '배점' number 에 저장한다 (notion_server 가 /100 안 함).
                "weight": a.points_possible or 0,
                "submitted": a.submitted,
                "text": a.description_text,
            }
            for a in assignments if a.due_at
        ]
        # 강의자료 payload — 주차(module_name)·제목·유형(한글 라벨)·LMS 딥링크.
        # SubHeader 등 url 없는 구분 헤더는 제외(목록 노이즈 방지)하되, 제목만 있는
        # 자료는 url 없이도 표기한다(vault_service 가 링크 없이 렌더).
        material_payload = [
            {
                "course_name": name_map.get(m.course_id, ""),
                "module_name": m.module_name,
                "title": m.title,
                "type": material_type_label(m.item_type),
                "url": m.url or "",
                "position": m.position,
            }
            for m in materials
            if m.item_type != "SubHeader" and m.title
        ]

        # 3) Notion push (설정된 경우에만 — placeholder 'xxxx' 는 미설정 취급)
        if is_configured(settings.notion_token, settings.notion_root_page_id):
            try:
                pushed = await sync_notion(
                    notices=notice_payload,
                    assignments=assign_payload,
                    notion_mcp_url=settings.notion_mcp_url,
                    notion_token=settings.notion_token,
                )
                # 부분 실패도 SyncResult.errors 에 드러낸다 (success=False 로 프론트 인지)
                if pushed.get("failed"):
                    errors.append(f"notion: {pushed['failed']}건 upsert 실패")
                logger.info(
                    f"[Sync] Notion push — 공지 {pushed.get('notices_added')} · "
                    f"과제 {pushed.get('assignments_added')} 신규 · "
                    f"실패 {pushed.get('failed', 0)}건"
                )
            except Exception as e:
                logger.exception("[Sync] Notion push 실패")
                errors.append(f"notion: {e}")
        else:
            logger.info("[Sync] Notion 미설정 → push 건너뜀")

        # 4) Obsidian push (설정된 경우에만 — setup.py 마운트 조건과 동일해야 함)
        if is_configured(settings.obsidian_mcp_auth_code):
            try:
                pushed_obs = await sync_obsidian(
                    notice_payload,
                    assign_payload,
                    settings.obsidian_mcp_url,
                    settings.obsidian_mcp_auth_code,
                    materials=material_payload,
                )
                if pushed_obs.get("failed"):
                    errors.append(f"obsidian: {pushed_obs['failed']}건 저장 실패")
                logger.info(
                    f"[Sync] Obsidian push — 저장 {pushed_obs.get('saved')} · "
                    f"변경없음 {pushed_obs.get('skipped')} · 실패 {pushed_obs.get('failed', 0)}건"
                )
            except Exception as e:
                logger.exception("[Sync] Obsidian push 실패")
                errors.append(f"obsidian: {e}")
        else:
            logger.info("[Sync] Obsidian 미설정 → push 건너뜀")

        # 5) 이메일 알림 (설정된 경우에만, #9)
        # 방금 수집한 과제/공지로 마감 임박분만 발송한다 — 추가 네트워크 호출 0회.
        # 신규 공지 diff 는 주기 스캔 job(notify_service.scan_and_notify)이 담당하므로
        # 여기선 마감 임박만 보낸다(sync 직후 중복 발송 회피). 발송 실패가 sync 를
        # 깨지 않도록 send_email 이 예외를 삼키고, 한 번 더 try 로 감싼다.
        if notify_service.smtp_configured():
            try:
                deadlines = notify_service.upcoming_deadlines(
                    assign_payload, within_hours=settings.notify_deadline_hours
                )
                digest = notify_service.render_digest(deadlines, [])
                if digest:
                    notify_service.send_email(*digest)
            except Exception as e:
                logger.warning(f"[Sync] 이메일 알림 발송 중 오류(무시): {e}")

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
        # 수집(파악)된 강의 모듈 아이템 총 개수 — list_courses 가 이미 계산해 온
        # Course.materials 의 집계 (추가 네트워크 호출 0회). 강의 자료 파일
        # 다운로드는 LTI 뷰어 뒤라 범위 밖 — Obsidian 엔 공지/과제 markdown 만 push.
        materials=sum(c.materials for c in courses),
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
        # 예약 동기화 시각(SYNC_HOUR) — 프론트 connectors 페이지의 '매일 HH:00' 안내용
        "syncHour": settings.sync_hour,
    }
