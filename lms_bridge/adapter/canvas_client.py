"""
lms_bridge/adapter/canvas_client.py
──────────────────────────────────────────────────────────────
canvas.ssu.ac.kr/learningx/api/v1/ REST API 클라이언트.

로그인 분석 결과:
  - Auth: Authorization: Bearer {xn_api_token} 헤더
  - xn_api_token 은 lms.ssu.ac.kr mypage 방문 시 canvas.ssu.ac.kr 에서 설정되는 쿠키
  - 세션 쿠키: _legacy_normandy_session, _normandy_session (HttpOnly)

사용 예::

    async with LMSAuth() as auth:
        async with CanvasClient.from_auth(auth) as client:
            terms = await client.get_terms()
            courses = await client.get_courses(terms)
"""

from __future__ import annotations

from typing import Any

import httpx

from lms_bridge.config import settings
from lms_bridge.logger import logger

CANVAS_BASE = "https://canvas.ssu.ac.kr/learningx/api/v1"
CANVAS_REFERER = f"https://canvas.ssu.ac.kr/learningx/dashboard?user_login={settings.lms_username}&locale=ko"

_DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": CANVAS_REFERER,
    "Origin": "https://canvas.ssu.ac.kr",
}


class CanvasAPIError(Exception):
    """Canvas API 오류."""

    def __init__(self, status: int, url: str, message: str = "") -> None:
        self.status = status
        self.url = url
        super().__init__(f"[{status}] {url} — {message}")


class CanvasClient:
    """Canvas API httpx 클라이언트.

    컨텍스트 매니저로 사용::

        async with CanvasClient(token, cookies) as client:
            terms = await client.get_terms()
    """

    def __init__(self, token: str, cookies: dict[str, str]) -> None:
        self._token = token
        self._cookies = cookies
        self._client: httpx.AsyncClient | None = None

    # ────────────────────────────────────────────────────────────────────────
    # 팩토리
    # ────────────────────────────────────────────────────────────────────────

    @classmethod
    async def from_auth(cls, auth) -> "CanvasClient":
        """LMSAuth 인스턴스에서 CanvasClient 를 생성한다."""
        token = await auth.get_canvas_token()
        cookies = await auth.get_canvas_cookies()
        return cls(token=token, cookies=cookies)

    # ────────────────────────────────────────────────────────────────────────
    # 컨텍스트 매니저
    # ────────────────────────────────────────────────────────────────────────

    async def __aenter__(self) -> "CanvasClient":
        self._client = httpx.AsyncClient(
            headers={**_DEFAULT_HEADERS, "Authorization": f"Bearer {self._token}"},
            cookies=self._cookies,
            follow_redirects=True,
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ────────────────────────────────────────────────────────────────────────
    # 내부 헬퍼
    # ────────────────────────────────────────────────────────────────────────

    async def _get(self, path: str, params: dict | None = None) -> Any:
        if self._client is None:
            raise CanvasAPIError(0, path, "클라이언트가 초기화되지 않았습니다. async with 를 사용하세요.")
        url = f"{CANVAS_BASE}{path}"
        logger.debug(f"GET {url}")
        resp = await self._client.get(url, params=params)
        if resp.status_code >= 400:
            raise CanvasAPIError(resp.status_code, url, resp.text[:200])
        return resp.json()

    # ────────────────────────────────────────────────────────────────────────
    # 학기 API
    # ────────────────────────────────────────────────────────────────────────

    async def get_terms(self) -> list[dict]:
        """활성화된 학기 목록을 반환한다.

        Returns:
            [{"id": 46, "name": "2026년 1학기", "start_at": ..., "default": True}, ...]
        """
        data = await self._get(
            f"/users/{settings.lms_username}/terms",
            params={"include_invited_course_contained": "true"},
        )
        terms = data.get("enrollment_terms", [])
        active = [t for t in terms if t.get("workflow_state") == "active"]
        logger.info(f"활성 학기 {len(active)}개: {[t['name'] for t in active]}")
        return active

    def get_current_term(self, terms: list[dict]) -> dict | None:
        """terms 목록에서 현재(default=True, 정규 학기) 학기를 반환한다."""
        for t in terms:
            if t.get("default") and "학기" in t.get("name", ""):
                return t
        return terms[0] if terms else None

    # ────────────────────────────────────────────────────────────────────────
    # 강의 API
    # ────────────────────────────────────────────────────────────────────────

    async def get_courses(self, terms: list[dict] | None = None) -> list[dict]:
        """수강 강의 목록을 반환한다.

        Args:
            terms: get_terms() 반환값. None 이면 자동으로 가져온다.

        Returns:
            [{"id": 44172, "name": "고급AI수학 (2150164004)", "professors": "...", ...}, ...]
        """
        if terms is None:
            terms = await self.get_terms()
        params = {f"term_ids[{i}]": t["id"] for i, t in enumerate(terms)}
        data = await self._get("/learn_activities/courses", params=params)
        courses = data if isinstance(data, list) else []
        logger.info(f"수강 강의 {len(courses)}개 로드")
        return courses

    async def get_course_detail(self, course_id: int) -> dict:
        """특정 과목 상세 정보를 반환한다."""
        return await self._get(f"/courses/{course_id}")

    # ────────────────────────────────────────────────────────────────────────
    # 공지사항 API
    # ────────────────────────────────────────────────────────────────────────

    async def get_announcements(self, course_id: int, page_size: int = 50) -> list[dict]:
        """과목 공지사항 목록을 반환한다."""
        try:
            data = await self._get(
                f"/learn_activities/courses/{course_id}/announcements",
                params={"page_size": page_size},
            )
            items = data if isinstance(data, list) else data.get("announcements", [])
            logger.info(f"공지사항 {len(items)}개 (course_id={course_id})")
            return items
        except CanvasAPIError as e:
            logger.warning(f"공지사항 로드 실패 (course_id={course_id}): {e}")
            return []

    # ────────────────────────────────────────────────────────────────────────
    # 과제 API
    # ────────────────────────────────────────────────────────────────────────

    async def get_assignments(self, course_id: int) -> list[dict]:
        """과목 과제 목록을 반환한다."""
        try:
            data = await self._get(f"/learn_activities/courses/{course_id}/assignments")
            items = data if isinstance(data, list) else data.get("assignments", [])
            logger.info(f"과제 {len(items)}개 (course_id={course_id})")
            return items
        except CanvasAPIError as e:
            logger.warning(f"과제 로드 실패 (course_id={course_id}): {e}")
            return []

    async def get_all_todos(self, terms: list[dict] | None = None) -> dict:
        """전체 과목 할일(미제출 과제, 안읽은 공지 등)을 반환한다."""
        if terms is None:
            terms = await self.get_terms()
        params = {f"term_ids[{i}]": t["id"] for i, t in enumerate(terms)}
        return await self._get("/learn_activities/to_dos", params=params)

    # ────────────────────────────────────────────────────────────────────────
    # 강의 자료 API
    # ────────────────────────────────────────────────────────────────────────

    async def get_resources(self, course_id: int) -> list[dict]:
        """과목 강의 자료(파일) 목록을 반환한다.

        Note:
            현재 LMS 구조 분석 결과, 강의 자료는 모듈의 attendance_item → commons 콘텐츠
            형태로 저장되어 있다. get_modules() 결과를 파싱하는 것이 권장 방법이다.
            이 메서드는 호환성을 위해 남겨두며, 내부적으로 get_modules 를 호출한다.
        """
        modules = await self.get_modules(course_id)
        resources = []
        for mod in modules:
            for item in mod.get("module_items", []):
                if item.get("content_type") == "attendance_item":
                    resources.append({
                        "week": mod.get("position", 0),
                        "week_title": mod.get("title", ""),
                        "module_item_id": item.get("module_item_id"),
                        "title": item.get("title", ""),
                        "content_type": item.get("content_type"),
                        "content_id": item.get("content_id"),
                        "content_data": item.get("content_data", {}),
                    })
        logger.info(f"강의 자료(attendance_item) {len(resources)}개 (course_id={course_id})")
        return resources

    async def get_modules(self, course_id: int, per_page: int = 100) -> list[dict]:
        """과목 모듈(주차별 강의 및 아이템) 목록을 반환한다.

        LMS 분석 결과 확인된 API:
            GET /courses/{id}/modules?per_page=100
            → [{"module_id": ..., "title": "1주차", "module_items": [...]}]

        각 module_item:
            - content_type: "attendance_item" (강의 영상/자료)
                           "wiki_page" (텍스트 페이지)
            - content_data.item_content_type: "commons" (공유 콘텐츠)
            - content_data.item_content_id: MongoDB ObjectID (파일 참조)
        """
        try:
            data = await self._get(f"/courses/{course_id}/modules", params={"per_page": per_page})
            modules = data if isinstance(data, list) else []
            total_items = sum(len(m.get("module_items", [])) for m in modules)
            logger.info(f"모듈 {len(modules)}주차 / 아이템 {total_items}개 (course_id={course_id})")
            return modules
        except CanvasAPIError as e:
            logger.warning(f"모듈 로드 실패 (course_id={course_id}): {e}")
            return []

    async def get_attendance_item(self, course_id: int, item_id: int) -> dict | None:
        """attendance_item 상세 정보를 반환한다.

        LMS 분석 결과 확인된 API:
            GET /courses/{course_id}/attendance_items/{item_id}
            → {"item_id": ..., "item_content_type": "commons", "item_content_id": "..."}
        """
        try:
            return await self._get(f"/courses/{course_id}/attendance_items/{item_id}")
        except CanvasAPIError as e:
            logger.warning(f"attendance_item 로드 실패 (item_id={item_id}): {e}")
            return None
