# backend/app/api/routes/connectors.py
# 커넥터 상태/설정 라우트 — 외부 연동(LMS / Notion / Obsidian / LLM).
# ──────────────────────────────────────────────────────────────────────────────
#   POST /api/connectors/config → 가입 마법사가 입력한 키를 루트 .env 에 저장
#   GET  /api/connectors/status →
#     [ { "id": "lms"|"notion"|"obsidian"|"llm",
#         "status": "connected"|"disconnected",
#         "meta": "<짧은 한국어 설명>",
#         "last": "<문자열 또는 null>" }, ... ]
#
# 규약 (팀 공유 컨트랙트 B — 프론트 커넥터 위젯이 이 형태에 의존):
#   - 4개 항목을 항상 전부 반환하고 HTTP 200 고정.
#   - 개별 판정 중 어떤 예외가 나도 절대 전파하지 않는다 (disconnected 로 강등).
#   - 빈값 / placeholder('xxxx') 설정은 네트워크 호출 없이 disconnected 처리.
#
# 네트워크 핑(_ping_notion / _ping_obsidian)은 모듈 레벨 함수로 분리해
# 테스트에서 monkeypatch 로 대체할 수 있게 했다 (tests/test_connectors_status.py).
# ──────────────────────────────────────────────────────────────────────────────
import asyncio
import inspect
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

# 세션 만료 기준 / 판정 헬퍼는 routes/lms.py 와 공용 (api/session_meta.py)
from app.api.session_meta import SESSION_MAX_AGE, age_seconds, read_session_meta

# placeholder('xxxx') 판정은 routes/sync.py · mcp_client/setup.py 와 공용 (config.py)
# ENV_FILE 은 config.py 모듈 상수 (루트 .env 절대경로)
from app.config import ENV_FILE, is_configured, settings
from app.logger import logger

router = APIRouter()


# ── 네트워크 핑 (테스트에서 monkeypatch 대상) ──────────────────


async def _ping_notion() -> bool:
    """Notion API 생존 확인 — users.me() 를 5초 제한으로 호출."""
    from notion_client import AsyncClient  # 지연 import (미사용 환경 보호)

    client = AsyncClient(auth=settings.notion_token)
    try:
        await asyncio.wait_for(client.users.me(), timeout=5)
        return True
    finally:
        await client.aclose()


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _obsidian_tls_verify() -> bool:
    """비로컬 OBSIDIAN_BASE_URL 에는 인증서 검증 강제.

    자가서명 인증서 예외는 루프백 주소(localhost/127.0.0.1/::1)에만 허용 —
    원격 주소로 바뀌었는데 verify=False 면 MITM 으로 auth_code 가 노출될 수 있다.
    """
    host = urlparse(settings.obsidian_base_url).hostname
    return host not in _LOCAL_HOSTS


async def _ping_obsidian() -> bool:
    """Obsidian Local REST API 생존 확인 — 베이스 URL GET (3초 제한).

    응답이 오기만 하면(5xx 제외) 서버가 살아 있는 것으로 본다.
    TLS: 자가서명 인증서 예외(verify=False)는 루프백 주소에만 적용 —
    비로컬 주소는 정상 검증한다 (_obsidian_tls_verify).
    """
    headers = {"Authorization": f"Bearer {settings.obsidian_mcp_auth_code}"}
    async with httpx.AsyncClient(timeout=3, verify=_obsidian_tls_verify()) as client:
        resp = await client.get(
            f"{settings.obsidian_base_url.rstrip('/')}/", headers=headers
        )
        return resp.status_code < 500


# ── 항목별 판정 ────────────────────────────────────────────────


def _lms_status() -> dict:
    """세션 파일 존재 + saved_at 7일 이내면 connected."""
    item = {"id": "lms", "status": "disconnected", "meta": "세션 없음 · 로그인 필요", "last": None}
    meta = read_session_meta()
    if meta is None:  # 파일 없음 또는 손상(JSON 파싱 실패) → 재로그인 필요
        return item
    saved_at = meta.get("saved_at")
    item["last"] = saved_at
    if age_seconds(saved_at) <= SESSION_MAX_AGE:
        item["status"] = "connected"
        item["meta"] = "세션 활성 · 강의 동기화 가능"
    else:
        item["meta"] = "세션 만료 · 재로그인 필요"
    return item


async def _notion_status() -> dict:
    """토큰/루트 페이지가 실값일 때만 users.me() 핑 (placeholder 면 호출 생략)."""
    item = {"id": "notion", "status": "disconnected", "meta": "NOTION_TOKEN 미설정", "last": None}
    if not is_configured(settings.notion_token, settings.notion_root_page_id):
        return item
    if await _ping_notion():
        item["status"] = "connected"
        item["meta"] = "Notion API 연결됨 · DB 동기화 가능"
    else:
        item["meta"] = "Notion API 응답 없음"
    return item


async def _obsidian_status() -> dict:
    """auth_code 가 실값(빈값/placeholder 'xxxx' 제외)일 때만 Local REST API 핑.

    obsidian_vault_path 는 vault 내부 상대 경로라 빈 문자열("")이 정상 설정이므로
    설정 여부 판단에서 제외한다 (mcp_client/setup.py 의 마운트 조건과 동일).
    """
    item = {"id": "obsidian", "status": "disconnected", "meta": "Obsidian 미설정", "last": None}
    if not is_configured(settings.obsidian_mcp_auth_code):
        return item
    if await _ping_obsidian():
        item["status"] = "connected"
        item["meta"] = "Local REST API 응답 확인 · Vault 사용 가능"
    else:
        item["meta"] = "Obsidian Local REST API 응답 없음"
    return item


def _llm_status() -> dict:
    """API 키 존재 여부만으로 판정 (네트워크 호출 없음)."""
    if not settings.llm_api_key:
        return {"id": "llm", "status": "disconnected", "meta": "LLM_API_KEY 미설정", "last": None}
    return {
        "id": "llm",
        "status": "connected",
        "meta": f"{settings.llm_provider} · {settings.llm_model}",
        "last": None,
    }


# ── 라우트 ─────────────────────────────────────────────────────


@router.get("/connectors/status")
async def connectors_status() -> list[dict]:
    """4개 커넥터 상태를 항상 200 으로 반환. 개별 실패는 disconnected 로 강등."""
    results: list[dict] = []
    for cid, check in (
        ("lms", _lms_status),
        ("notion", _notion_status),
        ("obsidian", _obsidian_status),
        ("llm", _llm_status),
    ):
        try:
            item = check()
            if inspect.isawaitable(item):
                item = await item
        except Exception as e:
            logger.warning(f"[Connectors] {cid} 상태 판정 실패: {e}")
            item = {"id": cid, "status": "disconnected", "meta": "상태 확인 실패", "last": None}
        results.append(item)
    return results


# ── 커넥터 키 저장 (.env upsert) ───────────────────────────────
# 가입 마법사가 입력한 Notion/Obsidian/LLM 키를 루트 .env 에 화이트리스트 저장한다.
# ⚠️ 인증 없이 노출되는 라우트 — /api/lms/login 과 동일하게 로컬 단일 사용자 전제.


class ConnectorConfigIn(BaseModel):
    # 화이트리스트 외 키는 422 로 거부 (임의 .env 키 주입 방지)
    model_config = ConfigDict(extra="forbid")

    notion_token: str | None = None
    notion_root_page_id: str | None = None
    obsidian_mcp_auth_code: str | None = None
    obsidian_base_url: str | None = None
    obsidian_vault_path: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None


# 요청 필드 → .env 키 매핑 (대문자)
_ENV_KEY_MAP = {
    "notion_token": "NOTION_TOKEN",
    "notion_root_page_id": "NOTION_ROOT_PAGE_ID",
    "obsidian_mcp_auth_code": "OBSIDIAN_MCP_AUTH_CODE",
    "obsidian_base_url": "OBSIDIAN_BASE_URL",
    "obsidian_vault_path": "OBSIDIAN_VAULT_PATH",
    "llm_provider": "LLM_PROVIDER",
    "llm_model": "LLM_MODEL",
    "llm_api_key": "LLM_API_KEY",
}

# 빈 문자열("")이 정상값인 필드 — vault 내부 상대 경로라 빈값=vault 루트.
# 이 필드는 빈값 거부 / placeholder 검증에서 제외한다 (config.py 의 obsidian_vault_path 기본값과 동일 규약).
_ALLOW_EMPTY_FIELDS = {"obsidian_vault_path"}


def _env_path() -> Path:
    """저장 대상 .env 경로 — 테스트에서 monkeypatch 대상 (_ping_* 와 같은 이유)."""
    return ENV_FILE


def _upsert_env_file(path: Path, updates: dict[str, str]) -> None:
    """줄 단위로 KEY= 매칭 줄을 교체, 없으면 말미에 append (주석·무관 줄 보존).

    .env 에 LMS 자격증명이 들어 있으므로 부분 기록 손상을 막기 위해 tmp 파일에
    먼저 쓰고 os.replace 로 원자적 교체한다.
    """
    lines = path.read_text("utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        replaced = False
        for key, val in list(remaining.items()):
            if re.match(rf"^\s*{re.escape(key)}\s*=", line):
                out.append(f"{key}={val}")
                del remaining[key]
                replaced = True
                break
        if not replaced:
            out.append(line)
    for key, val in remaining.items():
        out.append(f"{key}={val}")

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, path)


@router.post("/connectors/config")
async def save_connector_config(body: ConnectorConfigIn) -> dict:
    """입력된 커넥터 키를 루트 .env 에 저장. 시크릿 값은 응답에 에코하지 않는다."""
    provided = {k: v for k, v in body.model_dump().items() if v is not None}
    if not provided:
        raise HTTPException(status_code=400, detail="저장할 키가 없습니다.")

    mapped: dict[str, str] = {}
    for field, raw in provided.items():
        v = raw.strip()
        # obsidian_vault_path 는 빈 문자열("")이 정상값(vault 루트) — 빈값/placeholder 검증 생략
        if not v:
            if field in _ALLOW_EMPTY_FIELDS:
                mapped[_ENV_KEY_MAP[field]] = ""
                continue
            raise HTTPException(status_code=400, detail=f"'{field}' 값이 비어 있습니다.")
        # .env 인젝션 방지 — 개행/공백/따옴표/#/백슬래시 금지
        if re.search(r"[\s\"'#\\]", v):
            raise HTTPException(
                status_code=400,
                detail=f"'{field}' 값에 허용되지 않는 문자(공백/따옴표/# 등)가 있습니다.",
            )
        if not is_configured(v):
            raise HTTPException(
                status_code=400,
                detail=f"'{field}' 값에 'xxxx' 가 포함돼 placeholder 로 간주됩니다.",
            )
        mapped[_ENV_KEY_MAP[field]] = v

    _upsert_env_file(_env_path(), mapped)

    # 라이브 적용은 LLM 키(api_key/provider/model)만 — ChatService 는 요청마다 생성되고
    # _llm_status 도 호출 시점에 settings 를 읽으므로 즉시 반영된다. notion/obsidian 키는
    # setup_mcp 마운트가 부팅 시 고정이라 라이브 적용 시 deps._build_registry 가 미마운트
    # URL 에 클라이언트를 등록하게 되므로(deps.py 규약) 적용하지 않는다 — 재시작 후 반영.
    _live_llm_fields = {
        "llm_api_key": "LLM_API_KEY",
        "llm_provider": "LLM_PROVIDER",
        "llm_model": "LLM_MODEL",
    }
    applied_now: list[str] = []
    for field, env_key in _live_llm_fields.items():
        if field in provided:
            setattr(settings, field, provided[field].strip())
            applied_now.append(env_key)

    restart_keys = {
        "NOTION_TOKEN",
        "NOTION_ROOT_PAGE_ID",
        "OBSIDIAN_MCP_AUTH_CODE",
        "OBSIDIAN_BASE_URL",
        "OBSIDIAN_VAULT_PATH",
    }
    restart_required = bool(restart_keys & set(mapped))
    detail = (
        "키를 저장했습니다. Notion/Obsidian 연동은 백엔드 재시작 후 반영됩니다."
        if restart_required
        else "키를 저장했습니다."
    )
    return {
        "saved": list(mapped.keys()),
        "applied_now": applied_now,
        "restart_required": restart_required,
        "detail": detail,
    }
