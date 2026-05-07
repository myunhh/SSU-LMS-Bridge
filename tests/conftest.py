"""
tests/conftest.py
──────────────────────────────────────────────────────────────
pytest 공통 픽스처 및 설정.
"""

from __future__ import annotations

import os

import pytest


# 테스트 환경에서는 더미 .env 값을 사용해 settings 초기화 오류 방지
os.environ.setdefault("LMS_USERNAME", "test_student")
os.environ.setdefault("LMS_PASSWORD", "test_password")


@pytest.fixture
def dummy_course():
    """테스트용 더미 Course 객체."""
    from lms_bridge.models import Course, Semester

    return Course(
        id="60ee8dc20897dd1d8b517cd8",
        name="고급AI수학",
        professor="홍길동",
        credits=3,
        year=2026,
        semester=Semester.SPRING,
        url="https://lms.ssu.ac.kr/courses/60ee8dc20897dd1d8b517cd8",
    )


@pytest.fixture
def dummy_notice(dummy_course):
    """테스트용 더미 Notice 객체."""
    from datetime import datetime

    from lms_bridge.models import Notice

    return Notice(
        id="notice_001",
        course_id=dummy_course.id,
        title="1주차 강의 안내",
        body="다음 주 강의는 온라인으로 진행됩니다.",
        author="홍길동",
        created_at=datetime(2026, 3, 2, 10, 0, 0),
    )


@pytest.fixture
def dummy_assignment(dummy_course):
    """테스트용 더미 Assignment 객체."""
    from datetime import datetime

    from lms_bridge.models import Assignment, AssignmentStatus

    return Assignment(
        id="assign_001",
        course_id=dummy_course.id,
        title="1주차 과제",
        description="선형대수 1장 문제 풀이",
        due_at=datetime(2026, 3, 15, 23, 59, 0),
        status=AssignmentStatus.NOT_SUBMITTED,
        max_score=100.0,
    )
