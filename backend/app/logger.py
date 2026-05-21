# backend/app/logger.py
# loguru 기반 로깅 설정
# ──────────────────────────────────────────────────────────────────────────────
# setup_logging() 을 앱 기동 시 1회 호출한다 (main.py 의 lifespan).
# LOG_LEVEL 환경변수(.env) 를 반영한다.
# ──────────────────────────────────────────────────────────────────────────────
import sys

from loguru import logger

from app.config import settings

_CONFIGURED = False

_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
    "| <level>{level: <8}</level> "
    "| <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
    "- <level>{message}</level>"
)


def setup_logging():
    """loguru 기본 핸들러를 제거하고 stderr 핸들러를 LOG_LEVEL 로 재설정."""
    global _CONFIGURED
    if _CONFIGURED:
        return logger
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level.upper(),
        format=_FORMAT,
        colorize=True,
        backtrace=True,
        diagnose=False,  # 운영에서 변수값 노출 방지
    )
    _CONFIGURED = True
    return logger


__all__ = ["logger", "setup_logging"]
