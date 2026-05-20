# backend/app/models.py
"""
SSU LMS Bridge 공유 데이터 모델 (Pydantic v2)
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ──────────────────────────────────────────
# 강의 (Course)
# ──────────────────────────────────────────
class Course(BaseModel):
    id: int
    name: str
    course_code: str = ""
    term: str = ""

    class Config:
        extra = "ignore"


# ──────────────────────────────────────────
# 공지사항 (Notice)
# ──────────────────────────────────────────
class Notice(BaseModel):
    id: int
    course_id: int
    title: str
    message_snippet: str = ""
    posted_at: Optional[str] = None
    author: str = ""
    html_url: str = ""
    is_read: bool = False       # ✅ 추가: 읽음 여부

    class Config:
        extra = "ignore"


# ──────────────────────────────────────────
# 과제 (Assignment)
# ──────────────────────────────────────────
class Assignment(BaseModel):
    id: int
    course_id: int
    title: str
    due_at: Optional[str] = None
    points_possible: Optional[float] = None
    submission_types: List[str] = []
    html_url: str = ""
    description_snippet: str = ""
    submitted: bool = False     # ✅ 추가: 제출 여부

    class Config:
        extra = "ignore"

    @property
    def due_date(self) -> Optional[datetime]:
        if self.due_at:
            return datetime.fromisoformat(self.due_at.replace("Z", "+00:00"))
        return None

    @property
    def is_past_due(self) -> bool:
        d = self.due_date
        return d is not None and d < datetime.now(d.tzinfo)


# ──────────────────────────────────────────
# 강의 자료 (Material)
# ──────────────────────────────────────────
class Material(BaseModel):
    id: int
    course_id: int
    module_name: str = ""
    title: str = ""
    item_type: str = ""
    url: Optional[str] = None
    position: int = 0

    class Config:
        extra = "ignore"


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
    errors: List[str] = Field(default_factory=list)
