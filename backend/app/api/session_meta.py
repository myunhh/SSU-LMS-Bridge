# backend/app/api/session_meta.py
# LMS 세션 메타 공용 상수 / 헬퍼
# ──────────────────────────────────────────────────────────────────────────────
# routes/lms.py 와 routes/connectors.py 가 복붙으로 갖고 있던 세션 판정 로직을
# 한 곳으로 모았다. 아래 두 상수는 프론트 lmsAuth.js 의 SESSION_MAX_AGE /
# SESSION_REFRESH_INTERVAL 과 값이 짝을 이루므로, 변경 시 양쪽을 함께 고칠 것.
# ──────────────────────────────────────────────────────────────────────────────
import json
from datetime import datetime

from app.config import settings

# SSU SSO 쿠키 만료 (관찰값 ~7일) — 프론트 lmsAuth.js 의 SESSION_MAX_AGE 와 동일
SESSION_MAX_AGE = 7 * 24 * 3600
# main.py 예약 세션 갱신(IntervalTrigger) 주기 — 프론트 lmsAuth.js 의 SESSION_REFRESH_INTERVAL 과 동일
SESSION_REFRESH_INTERVAL = 5400


def read_session_meta() -> dict | None:
    """세션 파일(JSON)을 읽어 dict 반환. 없거나 손상(파싱 실패)이면 None."""
    path = settings.session_cache_abspath
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return None


def age_seconds(saved_at_iso: str | None) -> float:
    """세션 saved_at(ISO 문자열) 경과 초. 파싱 불가 시 무한대(=만료 취급)."""
    if not saved_at_iso:
        return float("inf")
    try:
        saved = datetime.fromisoformat(saved_at_iso)
    except ValueError:
        return float("inf")
    now = datetime.now(saved.tzinfo) if saved.tzinfo else datetime.now()
    return (now - saved).total_seconds()
