# backend/app/main.py
# FastAPI 앱 인스턴스 및 라우터 등록
# 실행: uvicorn app.main:app --reload --port 8000
"""FastAPI 엔트리포인트.

MCP 마운트(Notion / Obsidian)만 우선 연결해둠.
다른 팀원이 추가할 라우터(courses / notices / assignments / sync / chat)는
아래 TODO 블록에서 include_router 로 끼우면 된다.
"""
from fastapi import FastAPI
from loguru import logger

from app.api.routes import chat
from app.config import get_settings
from app.mcp_client.setup import setup_mcp

settings = get_settings()

app = FastAPI(title="SSU LMS Bridge", version="0.1.0")

# ── MCP 서버(Notion · Obsidian) SSE 마운트 ─────────────────
setup_mcp(app, settings)

# ── 채팅(LLM + MCP tool-use) 라우터 ───────────────────────
app.include_router(chat.router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.on_event("startup")
async def _startup() -> None:
    logger.info("[App] SSU LMS Bridge backend 시작")


# ── TODO: 다른 팀원이 추가할 라우터 ───────────────────────
# from app.api.routes import courses, notices, assignments, sync
# app.include_router(courses.router,     prefix="/api")
# app.include_router(notices.router,     prefix="/api")
# app.include_router(assignments.router, prefix="/api")
# app.include_router(sync.router,        prefix="/api")
