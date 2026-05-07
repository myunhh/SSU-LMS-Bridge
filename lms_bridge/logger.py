"""
lms_bridge/logger.py
──────────────────────────────────────────────────────────────
loguru 기반 전역 로거 설정.
모든 모듈에서 `from lms_bridge.logger import logger` 로 import.
"""

from __future__ import annotations

import sys

from loguru import logger as _logger

from lms_bridge.config import settings


def setup_logger() -> None:
    """로거를 설정한다. 앱 진입점(cli.py, server.py 등)에서 한 번만 호출."""
    _logger.remove()  # 기본 핸들러 제거
    _logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )
    _logger.add(
        ".cache/lms_bridge.log",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        enqueue=True,  # 멀티스레드 안전
    )


# 모듈 임포트 시 바로 사용할 수 있도록 기본 설정 적용
setup_logger()

logger = _logger
