# backend/app/models.py
"""
SSU LMS Bridge 공유 데이터 모델 (Pydantic v2)
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ──────────────────────────────────────────
# Canvas submission_type → 한글 표시 라벨 (백엔드 단일 소스)
# ──────────────────────────────────────────
# Notion '유형' select 에는 online_upload 같은 원시 Canvas 코드가 아니라
# 앱 화면과 통일된 한글 라벨이 들어가야 한다 (#12). sync.py 가 payload 의 'type'
# 을 이 dict 로 매핑해 Notion·Obsidian 양쪽에 같은 라벨을 보낸다.
# 프론트 api/index.js 의 SUBMISSION_TYPE_MAP(report/essay/quiz 표시 키)과
# 의미가 어긋나지 않게 유지할 것 — 한쪽을 바꾸면 다른 쪽도 검토.
SUBMISSION_TYPE_LABELS: dict[str, str] = {
    "online_upload": "과제(보고서)",     # 파일 업로드 → 프론트 'report'
    "online_text_entry": "에세이",        # 텍스트 입력 → 프론트 'essay'
    "online_quiz": "퀴즈",                # 퀴즈 → 프론트 'quiz'
    "discussion_topic": "토론",           # 토론 → 프론트 'essay'
}

# 매핑되지 않는 코드/빈 값의 폴백 — Notion select 빈 문자열 거부 회피.
SUBMISSION_TYPE_FALLBACK = "기타"


def submission_type_label(raw: str | None) -> str:
    """원시 Canvas submission_type 코드를 한글 표시 라벨로 변환.

    None / 빈 값 / 미등록 코드는 '기타' 로 폴백한다.
    """
    return SUBMISSION_TYPE_LABELS.get(raw or "", SUBMISSION_TYPE_FALLBACK)


# ──────────────────────────────────────────
# 강의 (Course)
# ──────────────────────────────────────────
class Course(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    course_code: str = ""
    term: str = ""
    professor: str = ""
    credits: float | None = None
    progress: float | None = None
    materials: int = 0              # ✅ 강의 모듈 아이템 총 개수


# ──────────────────────────────────────────
# 공지사항 (Notice)
# ──────────────────────────────────────────
class Notice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    course_id: int
    title: str
    message: str = ""               # ✅ 전체 본문 (HTML 원문)
    message_text: str = ""          # ✅ HTML 제거된 전체 본문 평문 (최대 8000자)
    posted_at: str | None = None
    author: str = ""
    html_url: str = ""
    is_read: bool = False
    pinned: bool = False            # ✅ 상단 고정 공지 (Canvas discussion_topics.pinned) — Notion '중요' 체크박스 원천


# ──────────────────────────────────────────
# 과제 (Assignment)
# ──────────────────────────────────────────
class Assignment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    course_id: int
    title: str
    due_at: str | None = None
    points_possible: float | None = None
    submission_types: list[str] = []
    html_url: str = ""
    description: str = ""           # ✅ 전체 본문 (HTML 원문)
    description_text: str = ""      # ✅ HTML 제거된 전체 본문 평문 (최대 8000자)
    submitted: bool = False

    @property
    def due_date(self) -> datetime | None:
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
    model_config = ConfigDict(extra="ignore")

    id: int
    course_id: int
    module_name: str = ""
    title: str = ""
    item_type: str = ""
    url: str | None = None
    position: int = 0


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
