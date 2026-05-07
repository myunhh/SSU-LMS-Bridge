"""
lms_bridge/adapter/notices.py
──────────────────────────────────────────────────────────────
공지사항 파싱 모듈. (Phase 1-B, 2주차 구현 예정)
"""

from __future__ import annotations

from lms_bridge.models import Notice


async def get_notices(auth, course_id: str) -> list[Notice]:
    """강의 공지사항 목록을 반환한다.

    TODO (2주차): 공지사항 페이지 파싱 구현
    """
    raise NotImplementedError("2주차에 구현 예정")
