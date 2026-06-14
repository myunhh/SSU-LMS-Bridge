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
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.adapter.auth import SSULMSAuthPlaywright
from app.api.routes import sync as sync_routes  # 예약 갱신이 sync 진행 여부 확인 (순환 없음)
from app.api.session_meta import (
    SESSION_MAX_AGE,
    SESSION_REFRESH_INTERVAL,
    age_seconds,
    read_session_meta,
)
from app.config import settings
from app.logger import logger

router = APIRouter()


class LmsLoginRequest(BaseModel):
    studentId: str
    password: str


# ── /api/lms/login 인-메모리 rate limit (#6) ─────────────────────────────────
# 무인증 로그인 엔드포인트의 무차별 대입/남용 방지. 외부 의존(Redis 등) 없이
# 프로세스 메모리에 키별 시도 기록만 둔다 (재시작 시 초기화 — 테스트는 reset 로
# 격리). 키는 학번+클라이언트 IP 조합이라, 한 IP 가 여러 학번을 돌리거나
# 한 학번을 여러 IP 로 노려도 각각 카운트된다.
#   - 윈도(window) 내 시도 횟수가 max_attempts 초과 → 429
#   - 연속 실패가 failure_threshold 도달 → backoff 동안 추가 차단 → 429
# 카운트는 진입 시(record_attempt), 실패/성공 판정은 사후(record_result)에 한다.
#
# _attempts:  key -> 최근 시도들의 monotonic 타임스탬프 리스트 (윈도 슬라이딩)
# _failures:  key -> (연속 실패 횟수, backoff 해제 시각 or None)
_attempts: dict[str, list[float]] = {}
_failures: dict[str, tuple[int, float | None]] = {}


def reset_login_rate_limit() -> None:
    """rate limit 상태 초기화 (테스트 격리용 — 프로세스 재시작과 동등)."""
    _attempts.clear()
    _failures.clear()


def _rate_limit_key(req: LmsLoginRequest, request: Request) -> str:
    client_ip = request.client.host if request.client else "unknown"
    return f"{req.studentId}|{client_ip}"


def _check_rate_limit(key: str) -> None:
    """윈도 시도 횟수 + 연속 실패 backoff 검사. 초과 시 HTTP 429 raise."""
    now = time.monotonic()

    # 1) 연속 실패 backoff — 아직 차단 시간이 안 지났으면 즉시 거부.
    fail_count, blocked_until = _failures.get(key, (0, None))
    if blocked_until is not None and now < blocked_until:
        retry_after = int(blocked_until - now) + 1
        logger.warning(f"[LMS] 로그인 backoff 차단 (연속 실패 {fail_count}회): {key}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.",
            headers={"Retry-After": str(retry_after)},
        )

    # 2) 슬라이딩 윈도 — 윈도 밖 기록은 버리고 남은 시도 수를 센다.
    window = settings.login_rate_limit_window_seconds
    recent = [t for t in _attempts.get(key, []) if now - t < window]
    if len(recent) >= settings.login_rate_limit_max_attempts:
        retry_after = int(window - (now - recent[0])) + 1
        logger.warning(f"[LMS] 로그인 rate limit 초과 ({len(recent)}회/{window}s): {key}")
        _attempts[key] = recent  # 정리된 윈도 반영
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.",
            headers={"Retry-After": str(retry_after)},
        )

    recent.append(now)
    _attempts[key] = recent


def _record_login_result(key: str, success: bool) -> None:
    """로그인 결과 기록 — 성공 시 카운터 리셋, 실패 시 연속 실패 누적/backoff."""
    if success:
        _failures.pop(key, None)
        return
    fail_count = _failures.get(key, (0, None))[0] + 1
    blocked_until: float | None = None
    if fail_count >= settings.login_rate_limit_failure_threshold:
        blocked_until = time.monotonic() + settings.login_rate_limit_backoff_seconds
        logger.warning(f"[LMS] 연속 실패 {fail_count}회 — backoff 발동: {key}")
    _failures[key] = (fail_count, blocked_until)


def _make_auth() -> SSULMSAuthPlaywright:
    """세션 파일 경로/디렉토리를 보장한 인증 객체."""
    path = settings.session_cache_abspath
    # 세션 파일 디렉토리도 소유자 전용(0700) — 단 exist_ok=True 라 기존 디렉토리
    # 권한은 그대로이므로, 실질 방어선은 auth._save_session 의 파일 단위 0600.
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    return SSULMSAuthPlaywright(
        session_file=str(path),
        headless=settings.playwright_headless,
    )


@router.post("/lms/login")
async def lms_login(req: LmsLoginRequest, request: Request):
    """학번/비밀번호로 SSU SSO 로그인 (Playwright). 세션을 파일로 저장.

    무인증 엔드포인트라 진입 시 인-메모리 rate limit(#6)을 먼저 검사한다 —
    윈도 내 시도 횟수 초과 또는 연속 실패 backoff 중이면 429.
    """
    key = _rate_limit_key(req, request)
    _check_rate_limit(key)  # 초과 시 429 raise
    auth = _make_auth()
    logger.info(f"[LMS] 로그인 시도: {req.studentId}")
    try:
        ok = await auth.login(req.studentId, req.password)
    except Exception:
        # 인프라 오류(Chromium 미설치, 네트워크 단절, SSO 마크업 변경 등)는
        # 자격증명 오류(401)와 구분해 502 로 응답한다. 서버 측 문제이므로
        # 연속 실패 카운터(backoff)에는 반영하지 않는다.
        logger.exception("[LMS] 로그인 처리 중 서버 오류")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LMS 로그인 처리 중 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        )
    if not ok:
        # 자격증명 불일치 — 연속 실패 카운터 누적 (backoff 발동 대상).
        _record_login_result(key, success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="LMS 학번 또는 비밀번호가 일치하지 않습니다.",
        )
    _record_login_result(key, success=True)  # 성공 — 카운터 리셋
    meta = read_session_meta() or {}
    return {
        "ok": True,
        "userInfo": meta.get("user_info", auth.user_info),
        "savedAt": meta.get("saved_at") or datetime.now().isoformat(),
    }


@router.get("/lms/session")
async def lms_session():
    """저장된 세션 메타만 읽어 상태 반환 (Playwright 미기동)."""
    meta = read_session_meta()
    if not meta:
        return {"active": False}
    saved_at = meta.get("saved_at")
    age = age_seconds(saved_at)
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
    try:
        ok = await auth.load_session()
    except Exception:
        # 인프라 오류는 세션 만료(401)와 구분해 502 로 응답
        logger.exception("[LMS] 세션 갱신 처리 중 서버 오류")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="세션 갱신 처리 중 서버 오류가 발생했습니다.",
        )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 만료되었습니다. 다시 로그인해주세요.",
        )
    meta = read_session_meta() or {}
    return {"ok": True, "savedAt": meta.get("saved_at")}


@router.delete("/lms/session", status_code=status.HTTP_204_NO_CONTENT)
async def lms_session_clear():
    """저장된 세션 파일 삭제."""
    path = settings.session_cache_abspath
    if path.exists():
        path.unlink()
        logger.info("[LMS] 세션 파일 삭제")
    return None


async def run_scheduled_session_refresh() -> None:
    """APScheduler 주기 세션 갱신 (SESSION_REFRESH_INTERVAL 마다).

    예약 작업이므로 예외를 밖으로 던지지 않는다 (로그로만). 동기화가 진행 중이면
    세션 파일 동시 갱신(Playwright 동시 쓰기)을 피하려 갱신을 양보한다 —
    sync 가 어차피 load_session 으로 세션을 연장하므로 손해 없음.
    """
    if not settings.session_cache_abspath.exists():
        logger.debug("[LMS] 예약 세션 갱신 건너뜀 — 세션 파일 없음(미로그인)")
        return
    if sync_routes.is_sync_running():
        logger.info("[LMS] 예약 세션 갱신 건너뜀 — 동기화 진행 중 (세션 파일 동시 갱신 회피)")
        return
    auth = _make_auth()
    try:
        ok = await auth.load_session()
    except Exception:
        logger.exception("[LMS] 예약 세션 갱신 실패 (인프라 오류)")
        return
    if not ok:
        logger.warning("[LMS] 예약 세션 갱신 실패 — 세션 만료, 재로그인 필요")
