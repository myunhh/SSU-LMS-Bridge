# backend/app/models.py
# Pydantic 데이터 모델 (Course, Assignment, Notice 등)
# backend/app/models.py
# Course, Notice, Assignment, Material 데이터 모델
"""
SSU LMS Bridge 공유 데이터 모델 (Pydantic v2)
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ──────────────────────────────────────────
# 강의 (Course)
# ──────────────────────────────────────────
class Course(BaseModel):
    id: int                          # Canvas course_id
    name: str                        # 강의명
    code: str = ""                   # 강의 코드 (예: CS-101)
    term_id: Optional[int] = None    # 학기 ID
    term_name: Optional[str] = None  # 학기명 (예: 2026년 1학기)

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# 강의 자료 (Material)
# ──────────────────────────────────────────
class Material(BaseModel):
    id: int                              # 자료 ID
    course_id: int                       # 소속 강의 ID
    week: Optional[int] = None           # 주차 번호
    title: str                           # 자료 제목
    content_type: Optional[str] = None  # 파일 타입 (pdf, pptx 등)
    url: Optional[str] = None           # 다운로드 URL
    file_name: Optional[str] = None     # 파일명

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# 공지사항 (Notice)
# ──────────────────────────────────────────
class Notice(BaseModel):
    id: int                              # 공지 ID
    course_id: int                       # 소속 강의 ID
    course_name: Optional[str] = None   # 강의명 (표시용)
    title: str                           # 공지 제목
    author: Optional[str] = None        # 작성자
    posted_at: Optional[datetime] = None  # 게시일
    url: Optional[str] = None           # 공지 URL
    is_read: bool = False               # 읽음 여부

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# 과제 (Assignment)
# ──────────────────────────────────────────
class Assignment(BaseModel):
    id: int                              # 과제 ID
    course_id: int                       # 소속 강의 ID
    course_name: Optional[str] = None   # 강의명 (표시용)
    title: str                           # 과제명
    due_at: Optional[datetime] = None   # 마감일시
    points: Optional[float] = None      # 배점
    submitted: bool = False             # 제출 여부
    url: Optional[str] = None           # 과제 URL

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# 동기화 결과 (SyncResult)
# ──────────────────────────────────────────
class SyncResult(BaseModel):
    success: bool
    synced_at: datetime = Field(default_factory=datetime.now)
    courses: int = 0
    notices: int = 0
    assignments: int = 0
    materials: int = 0
    errors: list[str] = Field(default_factory=list)
