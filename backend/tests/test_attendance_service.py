"""attendance_service — 출석율(출결현황) 계산 회귀 테스트 (오프라인).

검증
----
- attendance_rate: 출석/결석/지각/미진행 혼합에서 (출석 일수, 진행 일수) 계산
- 캐시 round-trip + cached_rate
- compute_and_cache: launch URL 해석·브라우저·캡처를 가짜로 → 출석율 계산·캐시
- list_courses 가 출석율 캐시를 progress 로 우선 사용 (Canvas 진도 위에 덮어씀)

네트워크/브라우저 금지 — _resolve_launch_urls·_browser_context·_capture_attendances 를
가짜로 패치하고 CACHE_PATH 를 tmp 로 격리한다.
"""
from contextlib import asynccontextmanager
from types import SimpleNamespace

from app.adapter.courses import list_courses
from app.services import attendance_service as A


# ── 순수: attendance_rate ────────────────────────────────────
def test_attendance_rate_basic():
    lessons = [
        {"attendance_status": "attendance"},
        {"attendance_status": "attendance"},
        {"attendance_status": "absent"},
    ]
    assert A.attendance_rate(lessons) == (2, 3)   # 출석 2 / 진행 3


def test_attendance_rate_excludes_unheld():
    """미진행(none/빈값)은 전체(분모)에서 제외한다."""
    lessons = [
        {"attendance_status": "attendance"},
        {"attendance_status": "absent"},
        {"attendance_status": "none"},   # 아직 안 한 수업 → 제외
        {"attendance_status": ""},        # 제외
        {"attendance_status": None},      # 제외
    ]
    assert A.attendance_rate(lessons) == (1, 2)   # 출석 1 / 진행 2


def test_attendance_rate_late_not_counted_as_present():
    """지각(late)은 진행엔 포함되지만 '출석'으로는 안 친다 (사용자 '출석' 기준)."""
    lessons = [
        {"attendance_status": "attendance"},
        {"attendance_status": "late"},
        {"attendance_status": "absent"},
    ]
    assert A.attendance_rate(lessons) == (1, 3)


def test_attendance_rate_none_when_nothing_held():
    assert A.attendance_rate([{"attendance_status": "none"}, {"attendance_status": ""}]) is None
    assert A.attendance_rate([]) is None


# ── 캐시 ──────────────────────────────────────────────────────
def test_cache_roundtrip_and_cached_rate(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "CACHE_PATH", tmp_path / "attendance.json")
    A.save_cache({"201": {"present": 27, "total": 29, "rate": 93.1}})
    assert A.load_cache()["201"]["rate"] == 93.1
    assert A.cached_rate(201) == 93.1
    assert A.cached_rate(999) is None   # 없는 과목


# ── 오케스트레이터 ────────────────────────────────────────────
async def test_compute_and_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "CACHE_PATH", tmp_path / "attendance.json")
    # 세션 파일(가짜)
    sf = tmp_path / "session.json"
    sf.write_text('{"cookies": [], "origins": []}', encoding="utf-8")

    async def _urls(course_ids, session_file):
        return {201: "https://lms/launch/201", 202: "https://lms/launch/202"}
    monkeypatch.setattr(A, "_resolve_launch_urls", _urls)

    @asynccontextmanager
    async def _ctx(storage):
        yield SimpleNamespace(name="dummy")
    monkeypatch.setattr(A, "_browser_context", _ctx)

    async def _capture(ctx, url):
        if url.endswith("201"):
            return [{"attendance_status": "attendance"}, {"attendance_status": "attendance"},
                    {"attendance_status": "absent"}]   # 2/3 = 66.7
        return [{"attendance_status": "attendance"}, {"attendance_status": "none"}]  # 1/1 = 100
    monkeypatch.setattr(A, "_capture_attendances", _capture)

    rates = await A.compute_and_cache([201, 202], str(sf))
    assert rates == {201: 66.7, 202: 100.0}
    cache = A.load_cache()
    assert cache["201"] == {"present": 2, "total": 3, "rate": 66.7}
    assert cache["202"]["rate"] == 100.0


async def test_compute_and_cache_skips_courses_without_data(monkeypatch, tmp_path):
    """캡처 실패(None)한 과목은 캐시/결과에서 빠지고 sync 를 깨지 않는다."""
    monkeypatch.setattr(A, "CACHE_PATH", tmp_path / "attendance.json")
    sf = tmp_path / "session.json"
    sf.write_text('{"cookies": [], "origins": []}', encoding="utf-8")

    async def _urls(course_ids, session_file):
        return {201: "u"}
    monkeypatch.setattr(A, "_resolve_launch_urls", _urls)

    @asynccontextmanager
    async def _ctx(storage):
        yield SimpleNamespace()
    monkeypatch.setattr(A, "_browser_context", _ctx)

    async def _capture(ctx, url):
        return None   # 런치 실패
    monkeypatch.setattr(A, "_capture_attendances", _capture)

    rates = await A.compute_and_cache([201], str(sf))
    assert rates == {}


# ── list_courses 가 출석율 캐시를 progress 로 사용 ────────────
class _FakeClient:
    def __init__(self, routes):
        self.routes = routes

    async def get(self, path, params=None, use_canvas=False):
        r = self.routes.get(path)
        if r is None:
            raise KeyError(path)
        return r

    async def get_all_pages(self, path, params=None, use_canvas=False):
        return await self.get(path, params, use_canvas)


async def test_list_courses_uses_attendance_cache_as_progress(monkeypatch):
    """출석율 캐시가 있으면 progress 를 그 값(출석율)으로 채운다."""
    monkeypatch.setattr(A, "load_cache", lambda: {"301": {"present": 9, "total": 10, "rate": 90.0}})
    client = _FakeClient({
        "/courses": [{"id": 301, "name": "DB", "course_progress": {"requirement_count": 10, "requirement_completed_count": 1}}],
        "/courses/301/users": [],
        "/courses/301/modules": [],
    })
    courses = await list_courses(client)
    assert courses[0].progress == 90.0   # course_progress(10%) 대신 출석율 90%


async def test_list_courses_falls_back_without_attendance_cache(monkeypatch):
    """출석율 캐시가 없으면 기존 Canvas 진도 로직으로 폴백."""
    monkeypatch.setattr(A, "load_cache", lambda: {})
    client = _FakeClient({
        "/courses": [{"id": 302, "name": "OS", "course_progress": {"requirement_count": 4, "requirement_completed_count": 1}}],
        "/courses/302/users": [],
        "/courses/302/modules": [],
    })
    courses = await list_courses(client)
    assert courses[0].progress == 25.0   # course_progress 1/4
