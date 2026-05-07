"""
tests/test_models.py
──────────────────────────────────────────────────────────────
데이터 모델(models.py) 단위 테스트.
"""

from __future__ import annotations

from datetime import datetime

from lms_bridge.models import (
    Assignment,
    AssignmentStatus,
    Course,
    CourseMaterial,
    MaterialFile,
    Notice,
    Semester,
    SyncResult,
)


class TestCourse:
    def test_create_course(self):
        c = Course(
            id="60ee8dc20897dd1d8b517cd8",
            name="고급AI수학",
            professor="홍길동",
            credits=3,
            year=2026,
            semester=Semester.SPRING,
        )
        assert c.id == "60ee8dc20897dd1d8b517cd8"
        assert c.semester == Semester.SPRING

    def test_default_values(self):
        c = Course(id="abc123", name="테스트", year=2026, semester=Semester.FALL)
        assert c.professor == ""
        assert c.credits == 0
        assert c.url == ""


class TestAssignment:
    def test_assignment_not_submitted(self, dummy_assignment):
        assert dummy_assignment.status == AssignmentStatus.NOT_SUBMITTED
        assert dummy_assignment.max_score == 100.0
        assert dummy_assignment.score is None

    def test_due_date(self, dummy_assignment):
        assert dummy_assignment.due_at == datetime(2026, 3, 15, 23, 59, 0)


class TestSyncResult:
    def test_summary_success(self):
        r = SyncResult(success=True, created=3, updated=1, skipped=2)
        summary = r.summary()
        assert "✅" in summary
        assert "생성=3" in summary
        assert "업데이트=1" in summary

    def test_summary_failure(self):
        r = SyncResult(success=False, failed=2, errors=["에러1", "에러2"])
        summary = r.summary()
        assert "❌" in summary
        assert "실패=2" in summary


class TestCourseMaterial:
    def test_create_with_files(self):
        f = MaterialFile(
            filename="week01_slides.pdf",
            lms_url="https://lms.ssu.ac.kr/files/1",
        )
        m = CourseMaterial(
            course_id="abc",
            week=1,
            title="1주차 강의자료",
            files=[f],
        )
        assert len(m.files) == 1
        assert m.files[0].filename == "week01_slides.pdf"
