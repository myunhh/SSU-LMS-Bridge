# backend/app/services/attendance_service.py
# 출석율(출석 일수 / 전체 일수) 계산 — LMS '출결현황'에서 가져온다.
# ──────────────────────────────────────────────────────────────────────────────
# SSU 는 '진도'를 LearningX 출석으로 관리한다. 과목 메뉴의 '출결현황' 탭이 호출하는
#   GET canvas.ssu.ac.kr/learningx/api/v1/courses/{cid}/lessons/attendances
# 가 교시(lesson)별 출석 상태(attendance/absent/late/…)를 준다. 이 API 는 LTI 세션이
# 있어야 하므로(Bearer/쿠키 단독은 400/401), 과목당 '출결현황' LTI 를 1회 런치해
# 세션을 만든 뒤 그 응답을 가로챈다. '출결현황'은 보기 전용이라 런치해도 출석을 새로
# 찍지 않는다(개별 주차학습 항목 런치와 다름).
#
# 비용(과목당 Playwright 런치 1회)이 크므로 perform_sync 에서 계산해 디스크에 캐시하고,
# adapter/courses.list_courses 는 캐시만 읽는다(대시보드 로드는 추가 호출 0).
# ──────────────────────────────────────────────────────────────────────────────
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from app.config import settings
from app.logger import logger

CACHE_PATH = settings.root_dir / ".cache" / "attendance.json"

# '출석'으로 인정할 상태 — 사용자 정의 '출석으로 찍힌 것'(지각/인정결석 제외, 결석 제외).
PRESENT_STATUSES = {"attendance"}
# 분모(전체 일수)에서 제외할 '미진행/미처리' 상태 — 아직 안 한 수업은 전체에서 뺀다.
_SKIP_STATUSES = {"", "none", "non_attendance", "not_attendance", "not_yet", "pending"}

_LAUNCH_CONCURRENCY = 3  # 동시에 여는 출결현황 LTI 페이지 수


# ── 캐시 ──────────────────────────────────────────────────────────────────────
def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def cached_rate(course_id: int) -> float | None:
    """list_courses 용 — 캐시된 출석율(0~100) 반환. 없으면 None."""
    entry = load_cache().get(str(course_id))
    return entry.get("rate") if isinstance(entry, dict) else None


# ── 순수 계산 (오프라인 테스트 대상) ──────────────────────────────────────────
def attendance_rate(lessons: list) -> tuple[int, int] | None:
    """lessons/attendances 응답 → (출석 일수, 전체 일수). 진행된 수업이 없으면 None.

    전체 = 미진행/미처리(_SKIP_STATUSES) 를 뺀 '진행된 수업' 수,
    출석 = attendance_status 가 PRESENT_STATUSES 인 수.
    """
    counted = [
        x for x in lessons
        if (x.get("attendance_status") or "").strip().lower() not in _SKIP_STATUSES
    ]
    if not counted:
        return None
    present = sum(
        1 for x in counted
        if (x.get("attendance_status") or "").strip().lower() in PRESENT_STATUSES
    )
    return present, len(counted)


# ── IO 경계 (테스트에서 monkeypatch) ─────────────────────────────────────────
async def _capture_attendances(ctx, launch_url: str) -> list | None:
    """출결현황 LTI 를 런치하고 lessons/attendances 응답(교시별 출석 상태)을 가로챈다."""
    pg = await ctx.new_page()
    box: dict = {}

    async def on_resp(r):
        if "lessons/attendances" in r.url and r.request.method == "GET":
            try:
                box["data"] = await r.json()
            except Exception:
                pass

    pg.on("response", lambda r: asyncio.create_task(on_resp(r)))
    try:
        await pg.goto(launch_url, wait_until="networkidle", timeout=40000)
        await pg.wait_for_timeout(5000)
    except Exception as e:
        logger.debug(f"[출석] 출결현황 런치 실패({launch_url}): {e!r}")
    finally:
        await pg.close()
    return box.get("data")


async def _attendance_tab_url(client, course_id: int) -> str | None:
    """과목 네비에서 '출결현황' 탭의 LTI launch URL 을 찾는다."""
    try:
        tabs = await client.get(f"/courses/{course_id}/tabs", use_canvas=True)
    except Exception as e:
        logger.debug(f"[출석] 과목 {course_id} 탭 조회 실패: {e!r}")
        return None
    if not isinstance(tabs, list):
        tabs = tabs.get("data", [])
    tab = next((t for t in tabs if "출결현황" in (t.get("label") or "")), None)
    if not tab:
        return None
    return tab.get("full_url") or tab.get("html_url")


@asynccontextmanager
async def _browser_context(storage: dict):
    """헤드리스 Chromium 컨텍스트(세션 쿠키 주입)를 yield. 테스트 monkeypatch 경계."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.playwright_headless)
        try:
            yield await browser.new_context(storage_state=storage, ignore_https_errors=True)
        finally:
            await browser.close()


async def _resolve_launch_urls(course_ids: list[int], session_file: str) -> dict[int, str]:
    """과목별 출결현황 탭 launch URL 수집 (Canvas 쿠키). 테스트 monkeypatch 경계."""
    from app.adapter.canvas_client import CanvasClient

    urls: dict[int, str] = {}
    async with CanvasClient(session_file=session_file) as client:
        for cid in course_ids:
            url = await _attendance_tab_url(client, cid)
            if url:
                urls[cid] = url
    return urls


# ── 오케스트레이터 ────────────────────────────────────────────────────────────
async def compute_and_cache(course_ids: list[int], session_file: str) -> dict:
    """전 과목 출석율을 계산해 캐시에 쓰고, {course_id: rate} 를 반환.

    과목당: 출결현황 탭 URL 조회(Canvas 쿠키) → LTI 런치(Playwright) → lessons/attendances
    가로채기 → 출석율. 실패한 과목은 건너뛰고(부분 결과) 캐시는 성공분만 갱신한다.
    """
    raw = json.loads(Path(session_file).read_text(encoding="utf-8"))
    storage = {"cookies": raw.get("cookies", []), "origins": raw.get("origins", [])}

    launch_urls = await _resolve_launch_urls(course_ids, session_file)
    if not launch_urls:
        return {}

    cache = load_cache()
    rates: dict[int, float] = {}
    sem = asyncio.Semaphore(_LAUNCH_CONCURRENCY)

    async with _browser_context(storage) as ctx:
        async def _one(cid: int, url: str):
            async with sem:
                lessons = await _capture_attendances(ctx, url)
            if not lessons:
                return
            rt = attendance_rate(lessons)
            if rt is None:
                return
            present, total = rt
            rate = round(present / total * 100, 1)
            cache[str(cid)] = {"present": present, "total": total, "rate": rate}
            rates[cid] = rate

        await asyncio.gather(*[_one(cid, url) for cid, url in launch_urls.items()])

    save_cache(cache)
    logger.info(f"[출석] 출석율 계산 — {len(rates)}/{len(course_ids)}개 과목 갱신")
    return rates
