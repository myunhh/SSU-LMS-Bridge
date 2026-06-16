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
    # obsidian_vault_path 는 vault 내부 상대 경로 (보통 빈 문자열이 정상, 예: "LMS")
    obsidian_vault_path: str = ""
    obsidian_mcp_auth_code: str = ""
    obsidian_vault_name: str = "LMS_Bridge_Vault"
    # Obsidian Local REST API 베이스 URL.
    # 플러그인 기본값: 27124=HTTPS(자가서명), 27123=HTTP.
    # 아래 기본값은 기존 하드코딩(http://…:27124)을 승계한 것이라 스킴-포트가 어긋날 수
    # 있으므로, 실제 환경에 맞게 .env 의 OBSIDIAN_BASE_URL 로 명시 설정을 권장.
    obsidian_base_url: str = "http://localhost:27124"

    # ── LLM ─────────────────────────────────────────────────────
    # 기본 프로바이더는 Gemini — Google AI Studio 키 사용,
    # litellm 모델명은 ChatService 가 "gemini/<model>" 로 prefix 한다.
    llm_provider: str = "gemini"
    llm_api_key: str = ""
    llm_model: str = "gemini-2.5-flash"

    # ── 세션 캐시 ────────────────────────────────────────────────
    # Playwright storage_state / 쿠키 저장 경로 (CanvasClient 가 읽음)
    session_cache_path: str = ".cache/session_state.json"

    # ── 동기화 설정 ─────────────────────────────────────────────
    sync_interval_hours: int = 24
    sync_hour: int = 4
    # 동기화 시 강의자료 '원본 파일'(PPT/PDF/문서 등)을 commons 에서 받아 Obsidian 에
    # 저장할지 여부. True 면 perform_sync 가 services/material_service.py 를 호출한다.
    # ⚠️ 원본 파일 위치(content_id)를 알아내려면 강의자료 LTI 를 1회 런치해야 하고,
    #    그 과정에서 '출결/진도'가 기록될 수 있다. 그래서 항목별 content_id 를
    #    매니페스트에 캐시해 **항목당 평생 1번만** 런치하고, 이후 동기화는 신규 자료만
    #    처리한다(이미 Obsidian 에 있는 파일은 런치 없이 건너뜀). Obsidian 미설정이면
    #    download_files=True 라도 동작하지 않는다(저장할 곳이 없으므로).
    download_files: bool = True

    # ── 채팅 입력 상한 (#8) ──────────────────────────────────────
    # WS/POST /api/chat 진입부에서 검사. 무제한 입력은 토큰 비용·메모리·DoS
    # 위험이 있으므로 메시지 개수·개별 길이·총합을 제한한다. 초과 시 거부
    # (POST 는 422/400, WS 는 error 이벤트).
    chat_max_messages: int = 50          # 한 요청당 메시지 개수 상한
    chat_max_content_chars: int = 16000  # 메시지 1건 content 길이 상한
    chat_max_total_chars: int = 64000    # 전체 content 합산 길이 상한

    # ── /api/lms/login rate limit (#6) ──────────────────────────
    # 무인증 로그인 엔드포인트의 무차별 대입/남용 방지. 프로세스 메모리 기반
    # 인-메모리 카운터(재시작 시 초기화)라 외부 의존 0. 학번+클라이언트 IP 키별로
    # 윈도 내 시도 횟수를 세고, 연속 실패가 누적되면 backoff 로 추가 차단한다.
    login_rate_limit_window_seconds: int = 60   # 윈도 길이(초)
    login_rate_limit_max_attempts: int = 5      # 윈도 내 허용 시도 횟수
    login_rate_limit_backoff_seconds: int = 300  # 연속 실패 임계 초과 시 차단(초)
    login_rate_limit_failure_threshold: int = 10  # backoff 발동 연속 실패 횟수

    # ── 이메일 알림 (#9) ─────────────────────────────────────────
    # 마감 임박 과제 / 신규 공지를 이메일로 발송. 전부 기본 빈값 — is_configured
    # 로 미설정을 판정하며, 미설정이면 발송 함수가 no-op(예외 없음)이고 스캔 job
    # 등록도 건너뛴다(services/notify_service.py, main.py). 실제 푸시(FCM/웹푸시)는
    # 범위 밖이라 이메일만 구현한다.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    notify_from: str = ""           # 발신 주소
    notify_to: str = ""             # 수신 주소 (콤마 구분 다중 허용)
    # 마감 임박 알림 임계(시간) / 스캔 주기(분)
    notify_deadline_hours: int = 24
    notify_scan_interval_minutes: int = 60

    # ── 웹 서버 포트 ─────────────────────────────────────────────
    backend_port: int = 8000
    frontend_port: int = 3000

    # ── 개발 / 디버그 ────────────────────────────────────────────
    log_level: str = "INFO"
    playwright_headless: bool = True

    # ── 파생 값: MCP 클라이언트가 붙을 내부 SSE URL ──────────────
    # setup_mcp() 가 같은 백엔드 프로세스에 마운트한 엔드포인트.
    # services/notion_services.py (notion_mcp_url) · services/vault_service.py
    # (obsidian_mcp_url) 가 이 값을 받아 SSE 연결을 연다.
    @property
    def lms_mcp_url(self) -> str:
        return f"http://localhost:{self.backend_port}/mcp/lms/sse"

    @property
    def study_mcp_url(self) -> str:
        # 학습 도우미 MCP(study__*) — lms 와 동일하게 토큰 없이 무조건 마운트.
        return f"http://localhost:{self.backend_port}/mcp/study/sse"

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


def is_configured(*vals) -> bool:
    """값이 실제로 채워졌는지 (빈값 / placeholder 'xxxx' 제외).

    .env.example 의 `secret_xxxx` 같은 견본 값을 실값으로 오인하지 않기 위한
    팀 공유 규칙 — routes/sync.py · routes/connectors.py · mcp_client/setup.py ·
    api/deps.py 가 모두 이 함수 하나를 사용한다 (복붙 금지).
    """
    return all(v and "xxxx" not in str(v).lower() for v in vals)


@lru_cache
def get_settings() -> Settings:
    """프로세스 전역 단일 Settings 인스턴스 (캐시)."""
    return Settings()


# 편의를 위한 모듈 레벨 싱글턴
settings = get_settings()
