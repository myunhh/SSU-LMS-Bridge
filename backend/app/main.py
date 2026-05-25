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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from httpx import HTTPStatusError

from app.api.routes import assignments, chat, courses, lms, notices, sync
from app.config import settings
from app.logger import setup_logging
from app.mcp_client.setup import setup_mcp

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
