"""
lms_bridge/models.py
──────────────────────────────────────────────────────────────
프로젝트 전역에서 공유하는 Pydantic 데이터 모델.
LMS에서 파싱한 데이터를 타입-안전하게 전달한다.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl


# ── 공통 ──────────────────────────────────────────────────────────────────────

class Semester(str, Enum):
    SPRING = "spring"
    SUMMER = "summer"
    FALL = "fall"
    WINTER = "winter"


# ── 강의 ──────────────────────────────────────────────────────────────────────

class Course(BaseModel):
    """수강 과목 하나를 나타낸다."""

    id: str = Field(..., description="LMS MongoDB ObjectID 형식 강의 ID")
    name: str = Field(..., description="과목명")
    professor: str = Field("", description="담당 교수")
    credits: int = Field(0, ge=0, description="학점")
    year: int = Field(..., description="연도")
    semester: Semester = Field(..., description="학기")
    url: str = Field("", description="강의 LMS URL")


# ── 강의 자료 ─────────────────────────────────────────────────────────────────

class MaterialFile(BaseModel):
    """강의 자료 첨부 파일 하나."""

    filename: str
    lms_url: str
    size_bytes: int = 0
    sha256: str = ""
    local_path: Path | None = None
    downloaded_at: datetime | None = None


class CourseMaterial(BaseModel):
    """주차별 강의 자료."""

    course_id: str
    week: int = Field(..., ge=0, description="주차 (0 = 미지정)")
    title: str
    description: str = ""
    files: list[MaterialFile] = Field(default_factory=list)
    created_at: datetime | None = None


# ── 공지사항 ──────────────────────────────────────────────────────────────────

class Notice(BaseModel):
    """강의 공지사항 하나."""

    id: str
    course_id: str
    title: str
    body: str = ""
    author: str = ""
    created_at: datetime | None = None
    url: str = ""


# ── 과제 ──────────────────────────────────────────────────────────────────────

class AssignmentStatus(str, Enum):
    SUBMITTED = "submitted"
    NOT_SUBMITTED = "not_submitted"
    LATE = "late"
    GRADED = "graded"


class Assignment(BaseModel):
    """강의 과제 하나."""

    id: str
    course_id: str
    title: str
    description: str = ""
    due_at: datetime | None = None
    status: AssignmentStatus = AssignmentStatus.NOT_SUBMITTED
    score: float | None = None
    max_score: float | None = None
    url: str = ""


# ── 동기화 결과 ───────────────────────────────────────────────────────────────

class SyncResult(BaseModel):
    """동기화 작업 결과 요약."""

    success: bool
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{'✅' if self.success else '❌'} "
            f"생성={self.created} 업데이트={self.updated} "
            f"스킵={self.skipped} 실패={self.failed}"
        )
