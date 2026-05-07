"""
lms_bridge/config.py
──────────────────────────────────────────────────────────────
pydantic-settings 기반 중앙 설정 관리.
.env 파일 또는 환경 변수에서 자동으로 값을 읽어들인다.

사용 예:
    from lms_bridge.config import settings
    print(settings.lms_base_url)
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LMS 계정 ────────────────────────────────────────────────────────────
    lms_username: str = Field(..., description="숭실대 학번")
    lms_password: str = Field(..., description="LMS 비밀번호")
    lms_base_url: str = Field("https://lms.ssu.ac.kr", description="LMS 기본 URL")
    lms_login_type: str = Field(
        "xn-sso-dir-sso",
        description="로그인 방식: xn-sso-dir-sso(통합) | xn-sso-dir-general(일반)",
    )

    # ── Notion ──────────────────────────────────────────────────────────────
    notion_token: str = Field("", description="Notion Integration 토큰")
    notion_root_page_id: str = Field("", description="Notion LMS-Bridge 루트 페이지 ID")

    # ── Obsidian Vault ───────────────────────────────────────────────────────
    obsidian_vault_path: Path = Field(
        Path.home() / "ObsidianVault" / "LMS",
        description="강의 교안 파일을 저장할 Obsidian Vault 경로",
    )

    # ── 세션 캐시 ────────────────────────────────────────────────────────────
    session_cache_path: Path = Field(
        Path(".cache") / "session_state.json",
        description="Playwright storage_state 캐시 파일 경로",
    )

    # ── 동기화 설정 ──────────────────────────────────────────────────────────
    sync_interval_hours: int = Field(24, ge=1, description="동기화 주기 (시간)")
    sync_hour: int = Field(4, ge=0, le=23, description="일일 동기화 실행 시각")
    download_files: bool = Field(True, description="교안 파일 자동 다운로드 여부")

    # ── 개발 / 디버그 ─────────────────────────────────────────────────────────
    log_level: str = Field("INFO", description="로그 레벨: DEBUG | INFO | WARNING | ERROR")
    playwright_headless: bool = Field(True, description="Playwright 헤드리스 모드 여부")

    # ── 파생 프로퍼티 ─────────────────────────────────────────────────────────
    @property
    def login_url(self) -> str:
        return f"{self.lms_base_url}/login?type={self.lms_login_type}"

    @property
    def session_cache_dir(self) -> Path:
        return self.session_cache_path.parent

    # ── 유효성 검사 ───────────────────────────────────────────────────────────
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level 은 {allowed} 중 하나여야 합니다.")
        return upper

    @field_validator("lms_login_type")
    @classmethod
    def validate_login_type(cls, v: str) -> str:
        allowed = {"xn-sso-dir-sso", "xn-sso-dir-general"}
        if v not in allowed:
            raise ValueError(f"lms_login_type 은 {allowed} 중 하나여야 합니다.")
        return v

    def ensure_dirs(self) -> None:
        """필요한 디렉토리를 미리 생성한다."""
        self.obsidian_vault_path.mkdir(parents=True, exist_ok=True)
        self.session_cache_dir.mkdir(parents=True, exist_ok=True)


# 전역 싱글턴 인스턴스
settings = Settings()  # type: ignore[call-arg]
