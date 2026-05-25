# backend/app/adapter/canvas_client.py
# SSU LMS REST 클라이언트 (httpx)
# ──────────────────────────────────────────────────────────────────────────────
# SSU 는 두 개의 호스트로 나뉜다.
#   - LearningX API : lms.ssu.ac.kr/learningx/api/v1   → Bearer xn_api_token 인증
#   - Canvas   API : canvas.ssu.ac.kr/api/v1           → 세션 쿠키(_normandy_session) 인증
#
# ⚠️ Canvas 는 Authorization: Bearer 를 세션 쿠키보다 우선 평가한다.
#    유효하지 않은 토큰을 Bearer 로 보내면 멀쩡한 쿠키 세션마저 "Invalid access token"(401)
#    으로 거부된다. 따라서 Canvas 호출에는 Bearer 를 절대 싣지 않고 쿠키로만 인증한다.
#    (LearningX 호출에만 Bearer xn_api_token 을 싣는다.)
# ──────────────────────────────────────────────────────────────────────────────
"""SSU LMS / Canvas REST httpx 클라이언트"""
import os
import json
import httpx
from pathlib import Path
from typing import Any, Optional


class CanvasClient:
    def __init__(self, session_file: str = None):
        if session_file is None:
            session_file = os.getenv("SESSION_CACHE_PATH", ".cache/session_state.json")
        self.session_file = Path(session_file)
        self._client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = None   # xn_api_token (LearningX Bearer)
        self._csrf: Optional[str] = None    # _csrf_token (Canvas mutating 요청용)

        # LearningX 호스트(lms)와 Canvas 호스트(canvas)는 다르다.
        lms_base = os.getenv("LMS_BASE_URL", "https://lms.ssu.ac.kr").rstrip("/")
        # CANVAS_BASE_URL 이 없으면 lms 호스트에서 canvas 로 치환 추론.
        canvas_base = os.getenv("CANVAS_BASE_URL", "").rstrip("/") or lms_base.replace("//lms.", "//canvas.")
        self.BASE = f"{lms_base}/learningx/api/v1"
        self.CANVAS_BASE = f"{canvas_base}/api/v1"

    async def init(self):
        if not self.session_file.exists():
            raise FileNotFoundError("세션 파일 없음. 먼저 로그인하세요.")

        data = json.loads(self.session_file.read_text("utf-8"))

        jar = httpx.Cookies()
        for c in data.get("cookies", []):
            jar.set(c["name"], c["value"], domain=c.get("domain", ""))

        self._token = self._find_token(data)
        self._csrf = self._find_cookie(data, "_csrf_token") or self._find_cookie(data, "XSRF-TOKEN")

        # 기본 헤더에는 Authorization 을 넣지 않는다 (Canvas 쿠키 인증 보호).
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        self._client = httpx.AsyncClient(
            cookies=jar,
            headers=headers,
            timeout=30.0,
            follow_redirects=True,
        )

    async def close(self):
        if self._client:
            await self._client.aclose()

    async def __aenter__(self):
        await self.init()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    def _headers_for(self, use_canvas: bool) -> dict:
        """호스트별 인증 헤더. Canvas=쿠키(+CSRF), LearningX=Bearer."""
        if use_canvas:
            h = {"Referer": "https://canvas.ssu.ac.kr/"}
            if self._csrf:
                h["X-CSRF-Token"] = self._csrf
            return h
        h = {"Referer": "https://lms.ssu.ac.kr/"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def get(self, path: str, params: dict = None, use_canvas: bool = False) -> Any:
        base = self.CANVAS_BASE if use_canvas else self.BASE
        url = f"{base}{path}" if path.startswith("/") else path
        resp = await self._client.get(url, params=params, headers=self._headers_for(use_canvas))
        resp.raise_for_status()
        return resp.json()

    async def get_all_pages(self, path: str, params: dict = None, use_canvas: bool = False) -> list:
        base = self.CANVAS_BASE if use_canvas else self.BASE
        url = f"{base}{path}" if path.startswith("/") else path
        headers = self._headers_for(use_canvas)
        params = params or {}
        params.setdefault("per_page", 100)
        results = []
        while url:
            resp = await self._client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            results.extend(resp.json())
            url = self._next_link(resp.headers.get("Link", ""))
            params = None
        return results

    async def download_file(self, url: str) -> bytes:
        """강의자료 등 바이너리 파일 다운로드 (vault_service 가 사용)."""
        resp = await self._client.get(url)
        resp.raise_for_status()
        return resp.content

    @staticmethod
    def _find_token(session_data: dict) -> Optional[str]:
        for origin in session_data.get("storage_state", {}).get("origins", []):
            for item in origin.get("localStorage", []):
                if item.get("name") in ("xn_api_token", "access_token", "token"):
                    return item["value"]
        for c in session_data.get("cookies", []):
            if c["name"] == "xn_api_token":
                return c["value"]
        return None

    @staticmethod
    def _find_cookie(session_data: dict, name: str) -> Optional[str]:
        for c in session_data.get("cookies", []):
            if c.get("name") == name:
                return c.get("value")
        return None

    @staticmethod
    def _next_link(link_header: str) -> Optional[str]:
        for part in link_header.split(","):
            if 'rel="next"' in part:
                return part.split("<")[1].split(">")[0]
        return None
