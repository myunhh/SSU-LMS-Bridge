# backend/app/adapter/canvas_client.py
# canvas.ssu.ac.kr REST API httpx 클라이언트 (CanvasClient)
"""Canvas REST API httpx 클라이언트"""
import os
import json
import httpx
from pathlib import Path
from typing import Any, Optional


class CanvasClient:
    """canvas.ssu.ac.kr REST API 클라이언트"""

    def __init__(self, session_file: str = None):
        if session_file is None:
            session_file = os.getenv("SESSION_CACHE_PATH", ".cache/session_state.json")
        self.session_file = Path(session_file)
        self._client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = None

        # .env의 LMS_BASE_URL 반영
        base = os.getenv("LMS_BASE_URL", "https://lms.ssu.ac.kr")
        self.BASE = f"{base}/learningx/api/v1"
        self.CANVAS_BASE = f"{base}/api/v1"

    async def init(self):
        if not self.session_file.exists():
            raise FileNotFoundError("세션 파일 없음. 먼저 로그인하세요.")

        data = json.loads(self.session_file.read_text("utf-8"))

        jar = httpx.Cookies()
        for c in data.get("cookies", []):
            jar.set(c["name"], c["value"], domain=c.get("domain", ""))

        self._token = self._find_token(data)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://canvas.ssu.ac.kr/",
            "Accept": "application/json",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

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

    async def get(self, path: str, params: dict = None, use_canvas: bool = False) -> Any:
        base = self.CANVAS_BASE if use_canvas else self.BASE
        url = f"{base}{path}" if path.startswith("/") else path
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_all_pages(self, path: str, params: dict = None, use_canvas: bool = False) -> list:
        base = self.CANVAS_BASE if use_canvas else self.BASE
        url = f"{base}{path}" if path.startswith("/") else path
        params = params or {}
        params.setdefault("per_page", 100)
        results = []
        while url:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            results.extend(resp.json())
            url = self._next_link(resp.headers.get("Link", ""))
            params = None
        return results

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
    def _next_link(link_header: str) -> Optional[str]:
        for part in link_header.split(","):
            if 'rel="next"' in part:
                return part.split("<")[1].split(">")[0]
        return None
