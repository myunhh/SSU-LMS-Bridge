# backend/app/main.py
# FastAPI 앱 인스턴스 및 라우터 등록
# 실행: uvicorn app.main:app --reload --port 8000
# ──────────────────────────────────────────────────────────────────────────────
# 구성:
#   - lifespan        : 로깅 초기화 + 설정 요약 출력
#   - CORS            : 프론트 dev 서버(:3000) 출처 허용
#   - setup_mcp       : Notion / Obsidian MCP 를 SSE 로 같은 프로세스에 마운트
#   - 라우터          : lms, sync, chat  (courses/notices/assignments 는 추후)
# ──────────────────────────────────────────────────────────────────────────────
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from httpx import HTTPStatusError

from app.api.routes import assignments, chat, connectors, courses, lms, mcp, notices, sync
from app.api.session_meta import SESSION_REFRESH_INTERVAL
from app.config import settings
from app.logger import setup_logging
from app.mcp_client.setup import setup_mcp
from app.services import notify_service

API_TITLE = "SSU LMS Bridge API"
API_VERSION = "0.1.0"

# 매일 정해진 시각(SYNC_HOUR)에 자동 동기화하는 스케줄러
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 기동 ──────────────────────────────────────────────────
    log = setup_logging()
    log.info(f"{API_TITLE} v{API_VERSION} 시작")
    log.info(f"  · LMS base       : {settings.lms_base_url}")
    log.info(f"  · 세션 캐시      : {settings.session_cache_abspath}")
    log.info(f"  · CORS 허용 출처 : {settings.cors_origins}")
    log.info(f"  · LLM provider   : {settings.llm_provider} ({settings.llm_model})")

    # ── 예약 동기화 (매일 SYNC_HOUR 시) ──────────────────────
    scheduler.add_job(
        sync.run_scheduled_sync,
        CronTrigger(hour=settings.sync_hour, minute=0),
        id="daily_sync",
        replace_existing=True,
        misfire_grace_time=3600,  # 서버가 잠시 꺼졌다 켜져도 1시간 내면 실행
    )
    # ── 예약 세션 갱신 (SESSION_REFRESH_INTERVAL 주기) ───────
    # auth.load_session 으로 lms·canvas 쿠키를 주기적으로 연장 — GET /api/lms/session
    # 의 nextRefreshIn 카운트다운이 실재 동작을 가리키게 한다.
    scheduler.add_job(
        lms.run_scheduled_session_refresh,
        IntervalTrigger(seconds=SESSION_REFRESH_INTERVAL),
        id="session_refresh",
        replace_existing=True,
        misfire_grace_time=600,
    )
    # ── 예약 이메일 알림 스캔 (#9) ───────────────────────────
    # 마감 임박 과제/신규 공지를 주기적으로 스캔해 이메일 발송. SMTP 미설정이면
    # job 자체를 등록하지 않는다 (Notion/Obsidian 의 is_configured 가드와 동일 정책).
    # 실제 푸시(FCM/웹푸시)는 프론트 service worker 필요 → 범위 밖, 이메일만.
    if notify_service.smtp_configured():
        scheduler.add_job(
            notify_service.scan_and_notify,
            IntervalTrigger(minutes=settings.notify_scan_interval_minutes),
            id="notify_scan",
            replace_existing=True,
            misfire_grace_time=600,
        )

    scheduler.start()
    job = scheduler.get_job("daily_sync")
    nxt = job.next_run_time.strftime("%Y-%m-%d %H:%M") if job and job.next_run_time else "—"
    log.info(f"  · 예약 동기화    : 매일 {settings.sync_hour:02d}:00 (다음 실행 {nxt})")
    log.info(f"  · 세션 자동 갱신 : {SESSION_REFRESH_INTERVAL}초 주기")
    if notify_service.smtp_configured():
        log.info(
            f"  · 이메일 알림    : {settings.notify_scan_interval_minutes}분 주기 스캔 "
            f"(마감 {settings.notify_deadline_hours}시간 전)"
        )
    else:
        log.info("  · 이메일 알림    : SMTP 미설정 → 비활성")

    yield

    # ── 종료 ──────────────────────────────────────────────────
    scheduler.shutdown(wait=False)
    log.info(f"{API_TITLE} 종료")


app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 업스트림(Canvas/LMS) 오류를 깔끔한 JSON 으로 변환 ─────────
# 어댑터가 httpx 로 LMS REST 를 호출하다 4xx/5xx 를 만나면 raise_for_status 가
# HTTPStatusError 를 던진다. 이를 라우트마다 try/except 하지 않고 전역 처리한다.
#   401/403/419(세션 만료·CSRF) → 401 (프론트가 재로그인 유도)
#   그 외                        → 502 (LMS 업스트림 오류)
@app.exception_handler(HTTPStatusError)
async def upstream_error_handler(request: Request, exc: HTTPStatusError):
    code = exc.response.status_code if exc.response is not None else 502
    if code in (401, 403, 419):
        return JSONResponse(
            status_code=401,
            content={"detail": "LMS 세션이 만료되었습니다. 다시 로그인해주세요."},
        )
    return JSONResponse(
        status_code=502,
        content={"detail": f"LMS 서버 응답 오류 ({code})."},
    )


# ── MCP 서버(Notion · Obsidian) SSE 마운트 ────────────────────
# 토큰/인증코드가 비어 있으면 해당 MCP 는 건너뛴다 (setup_mcp 내부 처리).
setup_mcp(app, settings)

# ── 라우터 등록 ───────────────────────────────────────────────
app.include_router(lms.router, prefix="/api", tags=["lms"])
app.include_router(sync.router, prefix="/api", tags=["sync"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(courses.router, prefix="/api", tags=["courses"])
app.include_router(notices.router, prefix="/api", tags=["notices"])
app.include_router(assignments.router, prefix="/api", tags=["assignments"])
app.include_router(connectors.router, prefix="/api", tags=["connectors"])
app.include_router(mcp.router, prefix="/api", tags=["mcp"])


# ── 헬스 체크 / 루트 ──────────────────────────────────────────
@app.get("/api/health", tags=["meta"])
async def health():
    """서버 기동 확인용. 의존성(세션/외부 API) 검사는 하지 않는다."""
    return {"status": "ok", "service": API_TITLE, "version": API_VERSION}


@app.get("/health", tags=["meta"])
async def health_alias():
    return {"status": "ok"}


@app.get("/", tags=["meta"])
async def root():
    return {"service": API_TITLE, "docs": "/docs", "health": "/api/health"}
