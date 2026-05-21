# backend/app/api/deps.py
# 공통 의존성 주입 — CanvasClient 팩토리
# ──────────────────────────────────────────────────────────────────────────────
# FastAPI 라우트에서 `client: CanvasClient = Depends(get_canvas_client)` 형태로 사용.
# 요청마다 CanvasClient 를 init() → yield → close() 한다.
# 세션 파일이 없으면(=로그인 전) 503 으로 변환해 프론트가 "재로그인 필요" 처리 가능.
# ──────────────────────────────────────────────────────────────────────────────
from typing import AsyncGenerator

from fastapi import HTTPException, status

from app.adapter.canvas_client import CanvasClient
from app.config import settings


async def get_canvas_client() -> AsyncGenerator[CanvasClient, None]:
    client = CanvasClient(session_file=str(settings.session_cache_abspath))
    try:
        await client.init()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LMS 세션이 없습니다. 먼저 로그인하세요.",
        ) from e
    try:
        yield client
    finally:
        await client.close()
