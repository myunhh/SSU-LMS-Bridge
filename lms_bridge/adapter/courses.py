"""
lms_bridge/adapter/courses.py
──────────────────────────────────────────────────────────────
강의 목록 파싱 모듈.

구현 예정 (Phase 1-B, Day 5-7):
  - 로그인 세션으로 LMS 강의 목록 페이지 접근
  - SPA 렌더링 대기 후 HTML 파싱
  - MongoDB ObjectID 기반 강의 ID 추출
  - Course 모델 리스트 반환
"""

from __future__ import annotations

from lms_bridge.models import Course


async def list_courses(auth) -> list[Course]:
    """현재 학기 수강 과목 목록을 반환한다.

    Args:
        auth: 로그인 완료된 LMSAuth 인스턴스

    Returns:
        Course 리스트 (id, name, professor, credits, year, semester, url)

    TODO (Day 5-7):
        1. auth.new_page() 로 인증된 페이지 획득
        2. LMS 메인 또는 강의 목록 URL 로 이동
        3. page.wait_for_load_state("networkidle") 로 SPA 렌더링 대기
        4. BeautifulSoup 으로 과목 목록 파싱
        5. MongoDB ObjectID 형식의 course_id 추출
        6. Course 모델로 변환하여 반환
    """
    raise NotImplementedError("Day 5-7 에 구현 예정")
