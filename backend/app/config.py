# backend/app/config.py
# pydantic-settings 기반 환경 변수 설정
# ──────────────────────────────────────────────────────────────────────────────
# 루트 .env (LMS-Bridge 백엔드 비밀값) 를 읽어 타입이 있는 Settings 객체로 노출한다.
#   - frontend/.env 의 VITE_* 변수는 여기서 다루지 않는다 (브라우저 빌드 전용).
#   - .env 에 없는 키는 아래 기본값을 사용한다.
#   - .env 에 있지만 여기 정의되지 않은 키는 extra="ignore" 로 무시된다.
#
# MCP(Notion / Obsidian) 클라이언트가 붙을 SSE URL 은 setup_mcp() 가 같은
# 백엔드 프로세스에 마운트한 엔드포인트로, notion_mcp_url / obsidian_mcp_url
# 프로퍼티가 backend_port 로부터 조립해서 제공한다.
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
    lms_password: str = ""
    lms_base_url: str = "https://lms.ssu.ac.kr"
    lms_login_type: str = "xn-sso-dir-sso"

    # ── Notion ──────────────────────────────────────────────────
    notion_token: str = ""
    notion_root_page_id: str = ""

    # ── Obsidian ────────────────────────────────────────────────
    obsidian_vault_path: str = ""
    obsidian_mcp_auth_code: str = ""
    obsidian_vault_name: str = "LMS_Bridge_Vault"

    # ── LLM ─────────────────────────────────────────────────────
    llm_provider: str = "anthropic"
    llm_api_key: str = ""
    llm_model: str = "claude-haiku-4-5"

    # ── 세션 캐시 ────────────────────────────────────────────────
    # Playwright storage_state / 쿠키 저장 경로 (CanvasClient 가 읽음)
    session_cache_path: str = ".cache/session_state.json"

    # ── 동기화 설정 ─────────────────────────────────────────────
    sync_interval_hours: int = 24
    sync_hour: int = 4
    download_files: bool = True

    # ── 웹 서버 포트 ─────────────────────────────────────────────
    backend_port: int = 8000
    frontend_port: int = 3000

    # ── 개발 / 디버그 ────────────────────────────────────────────
    log_level: str = "INFO"
    playwright_headless: bool = True

    # ── 파생 값: MCP 클라이언트가 붙을 내부 SSE URL ──────────────
    # setup_mcp() 가 같은 백엔드 프로세스에 마운트한 엔드포인트.
    # services/notion_services.py · services/vault_service.py 가 이 값을 받아 SSE 연결을 연다.
    @property
    def notion_mcp_url(self) -> str:
        return f"http://localhost:{self.backend_port}/mcp/notion/sse"

    @property
    def obsidian_mcp_url(self) -> str:
        return f"http://localhost:{self.backend_port}/mcp/obsidian/sse"

    # ── 파생 값: 경로 / CORS ────────────────────────────────────
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
