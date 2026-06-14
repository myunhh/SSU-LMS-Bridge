"""이메일 디제스트 과목명 주입 회귀 테스트 (#9) — 전부 오프라인.

배경
----
scan_and_notify 가 어댑터에서 받는 것은 course_id 만 가진 Assignment/Notice
모델이다(models.py — course_name 필드 없음). 정규화 없이 그대로 순수함수에
넘기면 _field 가 course_name 을 ''로 폴백해 render_digest 의 '[과목]' 접두가
항상 비어 제목만 출력되는 갭이 있었다. 여기서는 모델 입력 경로를 직접 검증한다:
_with_course_name 이 course_id→과목명 맵으로 course_name 을 채우면,
upcoming_deadlines/new_notices 가 그 값을 읽어 render_digest 가 '[과목]' 접두를
출력하는지 확인한다.

기존 test_notify_service.py 는 dict 입력에 course_name 을 직접 넣어 통과하므로
이 모델 입력 경로 갭을 드러내지 못한다 — 그 보완용.
"""
from datetime import UTC, datetime, timedelta

from app.models import Assignment, Notice
from app.services import notify_service

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── _with_course_name 단위 ────────────────────────────────────


def test_with_course_name_fills_from_map_for_model():
    """course_name 필드가 없는 Assignment 모델에 맵의 과목명이 주입된다."""
    a = Assignment(
        id=1, course_id=10, title="모델과제",
        due_at=_iso(NOW + timedelta(hours=3)), submitted=False,
    )
    out = notify_service._with_course_name([a], {10: "고급프로그래밍"})
    assert out[0]["course_name"] == "고급프로그래밍"
    assert out[0]["title"] == "모델과제"


def test_with_course_name_unknown_course_id_blank():
    """맵에 없는 course_id 는 빈 문자열로 둔다(크래시 없이 제목만)."""
    n = Notice(id=1, course_id=999, title="모델공지", posted_at=_iso(NOW))
    out = notify_service._with_course_name([n], {10: "DB"})
    assert out[0]["course_name"] == ""


def test_with_course_name_preserves_existing():
    """이미 course_name 이 있는 dict 입력은 맵으로 덮어쓰지 않는다."""
    item = {"course_id": 10, "title": "x", "course_name": "원래과목"}
    out = notify_service._with_course_name([item], {10: "다른과목"})
    assert out[0]["course_name"] == "원래과목"


# ── 모델 입력 → render_digest '[과목]' 접두까지의 통합 경로 ──────


def test_model_deadlines_render_course_prefix():
    """모델 과제 리스트가 과목명 주입 후 디제스트에서 '[과목]' 접두로 출력된다."""
    assignments = [Assignment(
        id=1, course_id=10, title="기말과제",
        due_at=_iso(NOW + timedelta(hours=5)), submitted=False,
    )]
    name_map = {10: "고급프로그래밍"}
    deadlines = notify_service.upcoming_deadlines(
        notify_service._with_course_name(assignments, name_map),
        within_hours=24, now=NOW,
    )
    assert deadlines and deadlines[0]["course_name"] == "고급프로그래밍"

    subject, body = notify_service.render_digest(deadlines, [])
    assert "[고급프로그래밍] 기말과제" in body


def test_model_notices_render_course_prefix():
    """모델 공지 리스트가 과목명 주입 후 디제스트에서 '[과목]' 접두로 출력된다."""
    notices = [Notice(
        id=1, course_id=20, title="휴강안내",
        posted_at=_iso(NOW - timedelta(hours=1)),
    )]
    name_map = {20: "데이터베이스"}
    since = NOW - timedelta(hours=2)
    fresh = notify_service.new_notices(
        notify_service._with_course_name(notices, name_map),
        since=since, now=NOW,
    )
    assert fresh and fresh[0]["course_name"] == "데이터베이스"

    subject, body = notify_service.render_digest([], fresh)
    assert "[데이터베이스] 휴강안내" in body
