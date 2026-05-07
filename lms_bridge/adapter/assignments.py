"""
lms_bridge/adapter/assignments.py
──────────────────────────────────────────────────────────────
과제 목록 및 마감일 파싱 모듈. (Phase 1-B, 2주차 구현 예정)
"""

from __future__ import annotations

from lms_bridge.models import Assignment


async def get_assignments(auth, course_id: str) -> list[Assignment]:
    """강의 과제 목록을 반환한다.

    TODO (2주차): 과제 페이지 파싱 구현
    """
    raise NotImplementedError("2주차에 구현 예정")


async def get_all_deadlines(auth) -> list[Assignment]:
    """전체 과목의 과제 마감일을 통합하여 반환한다.

    TODO (2주차): list_courses → get_assignments 순차 호출 후 병합
    """
    raise NotImplementedError("2주차에 구현 예정")
