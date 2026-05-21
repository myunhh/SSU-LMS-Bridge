# backend/app/main.py
# FastAPI 앱 인스턴스 및 라우터 등록
# 실행: uvicorn app.main:app --reload --port 8000
# ──────────────────────────────────────────────────────────────────────────────
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logger import setup_logging

API_TITLE = "SSU LMS Bridge API"
API_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 기동 ──────────────────────────────────────────────────
    log = setup_logging()
    log.info(f"{API_TITLE} v{API_VERSION} 시작")
    log.info(f"  · LMS base       : {settings.lms_base_url}")
    log.info(f"  · 세션 캐시      : {settings.session_cache_abspath}")
    log.info(f"  · CORS 허용 출처 : {settings.cors_origins}")
    log.info(f"  · LLM provider   : {settings.llm_provider} ({settings.llm_model})")
    # TODO(🅴): APScheduler 로 매일 settings.sync_hour 시 자동 동기화 등록

    yield

    # ── 종료 ──────────────────────────────────────────────────
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


# ── 헬스 체크 / 루트 ──────────────────────────────────────────
@app.get("/api/health", tags=["meta"])
async def health():
    """서버 기동 확인용. 의존성(세션/외부 API) 검사는 하지 않는다."""
    return {
        "status": "ok",
        "service": API_TITLE,
        "version": API_VERSION,
    }


@app.get("/", tags=["meta"])
async def root():
    return {"service": API_TITLE, "docs": "/docs", "health": "/api/health"}


# ── 라우터 등록 ───────────────────────────────────────────────
# TODO(🅰 5~7 / 🅱 / 🅳): 라우트 구현 후 아래처럼 등록한다.
#   from app.api.routes import courses, notices, assignments, sync, chat, lms
#   app.include_router(courses.router,     prefix="/api", tags=["courses"])
#   app.include_router(notices.router,     prefix="/api", tags=["notices"])
#   app.include_router(assignments.router, prefix="/api", tags=["assignments"])
#   app.include_router(sync.router,        prefix="/api", tags=["sync"])
#   app.include_router(chat.router,        prefix="/api", tags=["chat"])
#   app.include_router(lms.router,         prefix="/api", tags=["lms"])
