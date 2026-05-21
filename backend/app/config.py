# backend/app/config.py
# pydantic-settings 기반 환경 변수 설정
# ──────────────────────────────────────────────────────────────────────────────
# 루트 .env (LMS-Bridge 백엔드 비밀값) 를 읽어 타입이 있는 Settings 객체로 노출한다.
#   - frontend/.env 의 VITE_* 변수는 여기서 다루지 않는다 (브라우저 빌드 전용).
#   - .env 에 없는 키는 아래 기본값을 사용한다.
#   - .env 에 있지만 여기 정의되지 않은 키는 extra="ignore" 로 무시된다.
# ──────────────────────────────────────────────────────────────────────────────
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py → parents[2] = 프로젝트 루트
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LMS 계정 ────────────────────────────────────────────────
    lms_username: str = ""
    lms_base_url: str = "https://lms.ssu.ac.kr"
    lms_login_type: str = "xn-sso-dir-sso"

    # ── Notion ──────────────────────────────────────────────────
    notion_token: str = ""
    notion_root_page_id: str = ""
    # MCP SSE 엔드포인트 (서버를 별도로 띄울 경우). 비면 MCP 동기화 비활성.
    notion_mcp_url: str = ""

    # ── Obsidian ────────────────────────────────────────────────
    obsidian_vault_path: str = ""
    obsidian_mcp_auth_code: str = ""
    obsidian_vault_name: str = "LMS_Bridge_Vault"
    obsidian_mcp_url: str = ""

    # ── 세션 캐시 ────────────────────────────────────────────────
    # Playwright storage_state / 쿠키 저장 경로 (CanvasClient 가 읽음)
    session_cache_path: str = "ssu_lms_session.json"

    # ── 동기화 설정 ─────────────────────────────────────────────
    sync_interval_hours: int = 24
    sync_hour: int = 4
    download_files: bool = True

    # ── LLM ─────────────────────────────────────────────────────
    llm_provider: str = "anthropic"
    llm_api_key: str = ""
    llm_model: str = "claude-haiku-4-5"

    # ── 웹 서버 포트 ─────────────────────────────────────────────
    backend_port: int = 8000
    frontend_port: int = 3000

    # ── 개발 / 디버그 ────────────────────────────────────────────
    log_level: str = "INFO"
    playwright_headless: bool = True

    # ── 파생값 ──────────────────────────────────────────────────
    @property
    def root_dir(self) -> Path:
        return ROOT_DIR

    @property
    def session_cache_abspath(self) -> Path:
        """session_cache_path 가 상대경로면 루트 기준 절대경로로 변환."""
        p = Path(self.session_cache_path)
        return p if p.is_absolute() else (ROOT_DIR / p)

    @property
    def cors_origins(self) -> list[str]:
        """프론트 dev 서버 출처. 운영 배포 시 도메인 추가 필요."""
        return [
            f"http://localhost:{self.frontend_port}",
            f"http://127.0.0.1:{self.frontend_port}",
        ]


@lru_cache
def get_settings() -> Settings:
    """프로세스 전역 단일 Settings 인스턴스 (캐시)."""
    return Settings()


# 편의를 위한 모듈 레벨 싱글턴
settings = get_settings()
