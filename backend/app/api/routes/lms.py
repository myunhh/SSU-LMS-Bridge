# backend/app/api/routes/lms.py
# LMS SSO 인증 라우트 — adapter/auth.py 의 SSULMSAuthPlaywright 를 직접 호출.
# ──────────────────────────────────────────────────────────────────────────────
#   POST   /api/lms/login            { studentId, password } → { ok, userInfo, savedAt }
#   GET    /api/lms/session          → { active, userInfo?, savedAt?, nextRefreshIn? }
#   POST   /api/lms/session/refresh  → { ok, savedAt }
#   DELETE /api/lms/session          → 204
#
# 세션 파일 경로는 settings.session_cache_abspath 로 통일한다.
# (CanvasClient / deps.get_canvas_client 와 같은 파일을 읽도록)
# ──────────────────────────────────────────────────────────────────────────────
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.adapter.auth import SSULMSAuthPlaywright
from app.config import settings
from app.logger import logger

router = APIRouter()

# 프론트(lmsAuth.js)와 동일한 상수
SESSION_MAX_AGE = 7 * 24 * 3600       # SSU SSO 쿠키 만료(관찰값 ~7일)
SESSION_REFRESH_INTERVAL = 5400       # auth.py session_keeper_loop 주기


class LmsLoginRequest(BaseModel):
    studentId: str
    password: str


def _make_auth() -> SSULMSAuthPlaywright:
    """세션 파일 경로/디렉토리를 보장한 인증 객체."""
    path = settings.session_cache_abspath
    path.parent.mkdir(parents=True, exist_ok=True)
    return SSULMSAuthPlaywright(
        session_file=str(path),
        headless=settings.playwright_headless,
    )


def _read_session_meta() -> dict | None:
    path = settings.session_cache_abspath
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return None


def _age_seconds(saved_at_iso: str | None) -> float:
    if not saved_at_iso:
        return float("inf")
    try:
        saved = datetime.fromisoformat(saved_at_iso)
    except ValueError:
        return float("inf")
    now = datetime.now(saved.tzinfo) if saved.tzinfo else datetime.now()
    return (now - saved).total_seconds()


@router.post("/lms/login")
async def lms_login(req: LmsLoginRequest):
    """학번/비밀번호로 SSU SSO 로그인 (Playwright). 세션을 파일로 저장."""
    auth = _make_auth()
    logger.info(f"[LMS] 로그인 시도: {req.studentId}")
    ok = await auth.login(req.studentId, req.password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="LMS 학번 또는 비밀번호가 일치하지 않습니다.",
        )
    meta = _read_session_meta() or {}
    return {
        "ok": True,
        "userInfo": meta.get("user_info", auth.user_info),
        "savedAt": meta.get("saved_at") or datetime.now().isoformat(),
    }


@router.get("/lms/session")
async def lms_session():
    """저장된 세션 메타만 읽어 상태 반환 (Playwright 미기동)."""
    meta = _read_session_meta()
    if not meta:
        return {"active": False}
    saved_at = meta.get("saved_at")
    age = _age_seconds(saved_at)
    if age > SESSION_MAX_AGE:
        return {"active": False}
    return {
        "active": True,
        "userInfo": meta.get("user_info", {}),
        "savedAt": saved_at,
        "nextRefreshIn": max(0.0, SESSION_REFRESH_INTERVAL - (age % SESSION_REFRESH_INTERVAL)),
    }


@router.post("/lms/session/refresh")
async def lms_session_refresh():
    """저장된 세션을 로드·검증하고 쿠키를 연장 (auth.load_session)."""
    if not settings.session_cache_abspath.exists():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 없습니다. 다시 로그인해주세요.",
        )
    auth = _make_auth()
    logger.info("[LMS] 세션 갱신 시도")
    ok = await auth.load_session()
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 만료되었습니다. 다시 로그인해주세요.",
        )
    meta = _read_session_meta() or {}
    return {"ok": True, "savedAt": meta.get("saved_at")}


@router.delete("/lms/session", status_code=status.HTTP_204_NO_CONTENT)
async def lms_session_clear():
    """저장된 세션 파일 삭제."""
    path = settings.session_cache_abspath
    if path.exists():
        path.unlink()
        logger.info("[LMS] 세션 파일 삭제")
    return None
