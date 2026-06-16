# backend/app/api/routes/mcp.py
# MCP 서버 상태 라우트 — SSU LMS Bridge in-process MCP 4종.
# ──────────────────────────────────────────────────────────────────────────────
#   GET /api/mcp/status →
#     [ { "id": "lms"|"study"|"notion"|"obsidian",
#         "name": "<표시명>", "status": "connected"|"disconnected",
#         "meta": "<짧은 한국어 설명>", "tools": <int>,
#         "toolList": [ { "name": "<도구명>", "description": "<한 줄 설명>" }, ... ],
#         "url": "<SSE 엔드포인트>" }, ... ]
#
# 같은 백엔드 프로세스에 마운트된 4개 MCP 서버(mcp_client/setup.py 와 짝).
# lms·study 는 항상 마운트, notion·obsidian 은 설정 시에만 마운트된다.
# "현재 상태" = 각 SSE 엔드포인트에 핸드셰이크해 list_tools 를 실제로 받아보는 실측 핑.
#
# 컨트랙트 (connectors_status 와 동일): 항상 4개 항목·HTTP 200 고정, 개별 핑 실패는
# disconnected 로 강등하고 절대 전파하지 않는다. 네트워크 핑(_ping_mcp)은 모듈 레벨
# 함수로 분리해 테스트에서 monkeypatch 로 대체한다 (tests/test_mcp_status.py).
# ──────────────────────────────────────────────────────────────────────────────
import asyncio

from fastapi import APIRouter

from app.config import settings
from app.logger import logger
from app.mcp_client.base import MCPClientBase

router = APIRouter()

_MCP_SERVERS = [
    ("lms", "LMS MCP", "강의·과제·마감·공지·자료·토론 실시간 조회"),
    ("study", "Study MCP", "퀴즈·플래시카드(SM-2 SRS) 저장/복습"),
    ("notion", "Notion MCP", "Notion DB 동기화·질의"),
    ("obsidian", "Obsidian MCP", "Vault 노트·파일 읽기/쓰기"),
]


def _mcp_url(sid: str) -> str:
    return {
        "lms": settings.lms_mcp_url,
        "study": settings.study_mcp_url,
        "notion": settings.notion_mcp_url,
        "obsidian": settings.obsidian_mcp_url,
    }[sid]


def _tool_summary(description: str) -> str:
    """여러 줄 description 의 첫 문장(또는 첫 줄)만 짧게 — 카드 가독성용."""
    text = " ".join((description or "").split())  # 개행/연속공백 정리
    # 첫 마침표('.'·'。') 까지를 한 줄 요약으로. 없으면 120자 컷.
    for sep in (". ", "。"):
        if sep in text:
            return text.split(sep)[0] + sep.strip()
    return text[:120] + ("…" if len(text) > 120 else "")


async def _ping_mcp(url: str) -> list[dict] | None:
    """MCP SSE 엔드포인트에 핸드셰이크 + list_tools (5초 제한).

    성공 시 [{name, description}] 목록(description 은 한 줄 요약), 미마운트(404)/
    응답 없음/타임아웃이면 None. 테스트에서 monkeypatch 대상.
    """
    try:
        tools = await asyncio.wait_for(MCPClientBase(server_url=url).list_tools(), timeout=5)
        return [{"name": t.name, "description": _tool_summary(t.description)} for t in tools]
    except Exception:
        return None


async def _mcp_status() -> list[dict]:
    """4개 MCP 서버 상태를 항상 전부 반환. 개별 핑 실패는 disconnected 로 강등."""

    async def _one(sid: str, name: str, desc: str) -> dict:
        url = _mcp_url(sid)
        item = {"id": sid, "name": name, "status": "disconnected",
                "meta": desc, "tools": 0, "toolList": [], "url": url}
        try:
            tool_list = await _ping_mcp(url)
        except Exception as e:
            logger.warning(f"[MCP] {sid} 상태 핑 실패: {e}")
            tool_list = None
        if tool_list is not None:
            item["status"] = "connected"
            item["tools"] = len(tool_list)
            item["toolList"] = tool_list
            item["meta"] = f"{desc} · 도구 {len(tool_list)}개"
        elif sid in ("notion", "obsidian"):
            # 토큰 미설정이면 마운트 자체가 안 됨(setup.py). 설정했는데도 미마운트면 재시작 필요.
            item["meta"] = f"{desc} · 미마운트(키 미설정 또는 재시작 필요)"
        else:
            item["meta"] = f"{desc} · 응답 없음"
        return item

    # 4개를 병렬 핑 — gather(return_exceptions) 로 한 개 실패가 전체를 막지 않게.
    results = await asyncio.gather(
        *[_one(sid, name, desc) for sid, name, desc in _MCP_SERVERS],
        return_exceptions=True,
    )
    out: list[dict] = []
    for (sid, name, desc), r in zip(_MCP_SERVERS, results):
        if isinstance(r, dict):
            out.append(r)
        else:  # gather 가 잡은 예외 — disconnected 로 강등
            out.append({"id": sid, "name": name, "status": "disconnected",
                        "meta": f"{desc} · 상태 확인 실패", "tools": 0, "toolList": [],
                        "url": _mcp_url(sid)})
    return out


@router.get("/mcp/status")
async def mcp_status() -> list[dict]:
    """SSU LMS Bridge in-process MCP 서버 4종의 현재 상태 + 도구 목록(항상 200)."""
    try:
        return await _mcp_status()
    except Exception as e:  # 방어적 — _mcp_status 는 자체로 예외를 안 던지지만 200 보장
        logger.warning(f"[MCP] 상태 일괄 조회 실패: {e}")
        return [
            {"id": sid, "name": name, "status": "disconnected",
             "meta": f"{desc} · 상태 확인 실패", "tools": 0, "toolList": [], "url": _mcp_url(sid)}
            for sid, name, desc in _MCP_SERVERS
        ]
