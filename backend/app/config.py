# backend/app/config.py
# pydantic-settings 기반 환경 변수 설정
"""환경 변수(.env) 로딩 및 파생 설정 제공.

MCP 부분만 우선 채워둠. 다른 영역(LMS·LLM·동기화)은 .env.example 키를
그대로 받아두기만 하고, 실제 사용 코드는 담당자가 채울 예정.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LMS 계정 ─────────────────────────────────────────
    lms_username: str = ""
    lms_password: str = ""
    lms_base_url: str = "https://lms.ssu.ac.kr"
    lms_login_type: str = "xn-sso-dir-sso"

    # ── Notion ───────────────────────────────────────────
    notion_token: str = ""
    notion_root_page_id: str = ""

    # ── Obsidian ─────────────────────────────────────────
    obsidian_vault_path: str = ""
    obsidian_mcp_auth_code: str = ""
    obsidian_vault_name: str = "LMS_Bridge_Vault"

    # ── LLM ──────────────────────────────────────────────
    llm_provider: str = "anthropic"
    llm_api_key: str = ""
    llm_model: str = "claude-haiku-4-5"

    # ── 세션 캐시 ────────────────────────────────────────
    session_cache_path: str = ".cache/session_state.json"

    # ── 동기화 ───────────────────────────────────────────
    sync_interval_hours: int = 24
    sync_hour: int = 4
    download_files: bool = True

    # ── 웹 서버 포트 ─────────────────────────────────────
    backend_port: int = 8000
    frontend_port: int = 3000

    # ── 개발 / 디버그 ────────────────────────────────────
    log_level: str = "INFO"
    playwright_headless: bool = True

    # ── 파생 값: MCP 클라이언트가 붙을 내부 SSE URL ──────
    # setup_mcp() 가 같은 백엔드 프로세스에 마운트한 엔드포인트.
    # services/notion_services.py · services/vault_service.py 가 이 값을 받아 SSE 연결을 연다.
    @property
    def notion_mcp_url(self) -> str:
        return f"http://localhost:{self.backend_port}/mcp/notion/sse"

    @property
    def obsidian_mcp_url(self) -> str:
        return f"http://localhost:{self.backend_port}/mcp/obsidian/sse"


@lru_cache
def get_settings() -> Settings:
    return Settings()
