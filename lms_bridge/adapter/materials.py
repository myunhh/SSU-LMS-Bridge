"""
lms_bridge/adapter/materials.py
──────────────────────────────────────────────────────────────
강의 자료 파싱 및 파일 다운로드 모듈. (Phase 1-B, 2주차 구현 예정)
"""

from __future__ import annotations

from lms_bridge.models import CourseMaterial


async def get_course_materials(
    auth,
    course_id: str,
    week: int | None = None,
) -> list[CourseMaterial]:
    """주차별 강의 자료 목록을 반환한다.

    Args:
        auth: 로그인 완료된 LMSAuth 인스턴스
        course_id: MongoDB ObjectID 형식 강의 ID
        week: 특정 주차 (None 이면 전체 주차)

    TODO (2주차): 파싱 및 파일 URL 추출 구현
    """
    raise NotImplementedError("2주차에 구현 예정")
