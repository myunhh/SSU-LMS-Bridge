# backend/app/adapter/notices.py
# 공지사항 파싱
"""공지사항 조회 + HTML→평문 공용 헬퍼 (assignments.py 와 공유)"""
import asyncio
from datetime import UTC, datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from app.logger import logger

from ..models import Notice
from .canvas_client import CanvasClient

# 평문 본문 최대 길이 (팀 컨트랙트: message_text/description_text 공통 8000자)
MAX_TEXT_LEN = 8000

# 과목별 공지 폴백 동시 조회 상한 (httpx.AsyncClient 는 동시 요청 안전, #2)
_NOTICE_CONCURRENCY = 5


def html_to_text(html: str, limit: int = MAX_TEXT_LEN) -> str:
    """HTML 본문 → 평문 추출 (최대 limit 자).

    Notice.message_text / Assignment.description_text 공용 헬퍼.
    script/style 내용은 제거하고, 줄 단위로 공백을 정리한다.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    # 블록 요소 경계에서만 줄바꿈 (인라인 <b>/<i> 등은 이어 붙임)
    for br in soup.find_all("br"):
        br.replace_with("\n")
    block_tags = ["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
                  "ul", "ol", "table", "blockquote", "pre"]
    for tag in soup.find_all(block_tags):
        tag.append("\n")
    raw = soup.get_text()
    lines = (" ".join(line.split()) for line in raw.splitlines())
    text = "\n".join(line for line in lines if line)
    return text[:limit]


def is_session_unauthorized(exc: Exception) -> bool:
    """세션 만료성 401 인지 판정 (어댑터 공용).

    401 은 삼키지 않고 전역 HTTPStatusError 핸들러(→ '재로그인 필요')로
    전파시키기 위한 판별 헬퍼.
    """
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code == 401
    )


def _announcement_window() -> dict:
    """Canvas /announcements 기본 윈도우(start=14일 전, end=start+28일) 무력화.

    ⚠️ end_date 를 빼고 start_date 만 넣으면 윈도우가 [180일 전, 152일 전]으로
    밀려 최근 공지가 통째로 빠진다. 반드시 둘 다 명시할 것.
    """
    now = datetime.now(UTC)
    return {
        "start_date": (now - timedelta(days=180)).date().isoformat(),
        "end_date": (now + timedelta(days=1)).date().isoformat(),
    }


def _ctx_course_id(context_code: str) -> int:
    """'course_44176' → 44176"""
    if context_code and context_code.startswith("course_"):
        try:
            return int(context_code.split("_", 1)[1])
        except ValueError:
            return 0
    return 0


def _to_notice(n: dict, course_id: int) -> Notice:
    """Canvas announcement JSON → Notice 변환 (본문 평문 포함)."""
    message = n.get("message") or ""
    return Notice(
        id=n["id"],
        course_id=course_id,
        title=n.get("title", ""),
        # Notice 모델 필드명은 `message` (전체 본문 HTML 원문).
        message=message,
        message_text=html_to_text(message),  # ✅ HTML 제거 평문 (최대 8000자)
        posted_at=n.get("posted_at", n.get("created_at")),
        author=n.get("author", {}).get("display_name", "") if isinstance(n.get("author"), dict) else "",
        html_url=n.get("html_url", ""),
        is_read=n.get("read_state") == "read",
        # 상단 고정 공지 여부 — None 방어 위해 `or False` (명시적 null 도 False 로)
        pinned=bool(n.get("pinned") or False),
    )


async def list_all_notices(client: CanvasClient, course_ids: list[int]) -> list[Notice]:
    """전 과목 공지를 한 번의 /announcements 호출로 통합 조회 (context_code 로 과목 구분)."""
    if not course_ids:
        return []
    params = {
        "context_codes[]": [f"course_{cid}" for cid in course_ids],
        "per_page": 100,
        **_announcement_window(),  # 기본 14일 윈도우 무력화 (옛 공지 누락 방지)
    }
    try:
        # Link 헤더 페이지네이션 추적 — 첫 페이지(100건) 초과분 누락 방지
        raw = await client.get_all_pages("/announcements", params=params, use_canvas=True)
    except Exception as e:
        # Canvas 통합 호출 실패 → 과목별(Canvas→LearningX 폴백 내장) 개별 조회를 병렬화.
        # return_exceptions=True 로 한 과목 실패가 전체를 막지 않게 하되, 세션 만료(401)만
        # 골라 re-raise 해 두 호스트 모두 401 → 전역 핸들러 전파 정책을 유지한다.
        logger.warning(f"통합 공지 조회 실패 → 과목별 폴백: {e!r}")
        sem = asyncio.Semaphore(_NOTICE_CONCURRENCY)

        async def _fetch(cid: int) -> list[Notice]:
            async with sem:
                return await list_notices(client, cid)

        results = await asyncio.gather(
            *(_fetch(cid) for cid in course_ids), return_exceptions=True
        )
        out: list[Notice] = []
        for cid, result in zip(course_ids, results, strict=True):
            if isinstance(result, BaseException):
                if is_session_unauthorized(result):
                    # 두 호스트 모두 401 → 세션 만료. 삼키지 않고 전역 핸들러로 전파.
                    raise result
                logger.warning(f"과목 {cid} 공지 조회 실패, 건너뜀: {result!r}")
                continue
            out.extend(result)
        return out

    items = raw if isinstance(raw, list) else raw.get("data", [])
    return [_to_notice(n, _ctx_course_id(n.get("context_code", ""))) for n in items if n.get("id")]


async def list_notices(client: CanvasClient, course_id: int) -> list[Notice]:
    try:
        raw = await client.get_all_pages(
            "/announcements",
            params={
                "context_codes[]": f"course_{course_id}",
                "per_page": 50,
                **_announcement_window(),  # 기본 14일 윈도우 무력화
            },
            use_canvas=True,
        )
    except Exception as e:
        # Canvas(쿠키)와 LearningX(Bearer)는 인증이 독립적이므로 401 이어도 폴백 시도.
        # LearningX 호출마저 실패하면 그 예외가 그대로 전파된다 (401 → 전역 핸들러).
        logger.debug(f"과목 {course_id} Canvas 공지 실패 → LearningX 폴백: {e!r}")
        raw = await client.get(
            f"/courses/{course_id}/discussion_topics",
            params={"only_announcements": "true", "per_page": 50},
        )

    items = raw if isinstance(raw, list) else raw.get("data", [])
    return [_to_notice(n, course_id) for n in items if n.get("id")]


async def list_discussions(client: CanvasClient, course_id: int) -> list[Notice]:
    """과목 토론 목록 조회 (공지 탭과 동일 엔드포인트, only_announcements 미지정).

    discussion_topics 는 only_announcements 를 빼면 Canvas 기본값(false)으로
    일반 토론만 반환한다 — 공지 탭과 내용이 겹치지 않는다. 구조는 list_notices 와
    동일한 Canvas→LearningX 이중 호스트 폴백. 폴백마저 실패하면 그 예외(401 포함)가
    그대로 전파되어 전역 HTTPStatusError 핸들러가 처리한다 (per-course 루프가
    없으므로 is_session_unauthorized 분기 불필요). 토론 JSON 의
    title/message/posted_at/author.display_name/html_url/read_state 가 공지와
    1:1 매핑되므로 Notice 모델을 재사용한다 (message_text 8000자 평문 컨트랙트 자동 충족).
    """
    path = f"/courses/{course_id}/discussion_topics"
    try:
        raw = await client.get_all_pages(path, params={"per_page": 50}, use_canvas=True)
    except Exception as e:
        # Canvas(쿠키)와 LearningX(Bearer)는 인증이 독립적이므로 401 이어도 폴백 시도.
        logger.debug(f"과목 {course_id} Canvas 토론 실패 → LearningX 폴백: {e!r}")
        raw = await client.get(path, params={"per_page": 50})

    items = raw if isinstance(raw, list) else raw.get("data", [])
    return [_to_notice(n, course_id) for n in items if n.get("id")]
