# backend/app/api/routes/chat.py
# WebSocket /api/chat  — litellm 스트리밍 LLM 채팅 + MCP tool-use
# POST      /api/chat  — 단일 요청 폴백
"""채팅 엔드포인트.

- WS  /api/chat : 토큰 단위 스트리밍. 클라이언트는 {messages: [...]} 를 보내고,
                   서버는 {type, ...} 이벤트들을 순차적으로 전송한다.
- POST /api/chat: 스트리밍 없이 최종 텍스트 + tool 로그만 반환.
"""
import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from loguru import logger
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.api.deps import get_chat_service
from app.config import settings
from app.services.llm import ChatService

router = APIRouter()

# 클라이언트가 보낼 수 있는 role 화이트리스트.
# system/tool 은 서버가 주입하는 역할이므로 외부 입력에서 차단한다
# (system → 프롬프트 탈취, tool → 가짜 tool 결과 주입).
ALLOWED_CLIENT_ROLES = ("user", "assistant")


class ChatMessage(BaseModel):
    # content 길이 상한 (#8) — 무제한 입력은 토큰 비용·메모리·DoS 위험.
    role: str
    content: str = Field(max_length=settings.chat_max_content_chars)

    @field_validator("role")
    @classmethod
    def _role_whitelist(cls, v: str) -> str:
        # role 화이트리스트 — system/tool 등은 거부.
        if v not in ALLOWED_CLIENT_ROLES:
            raise ValueError(f"허용되지 않은 role: {v!r}")
        return v


class ChatRequest(BaseModel):
    # messages 개수 상한 (#8) — pydantic Field 로 POST 진입 시 422 거부.
    # WS 는 동일 모델을 재사용하므로 개수/개별 길이 검사가 함께 적용된다.
    messages: list[ChatMessage] = Field(max_length=settings.chat_max_messages)

    @field_validator("messages")
    @classmethod
    def _total_chars_limit(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        # 개별 길이는 ChatMessage.content 에서 막지만, 메시지가 많으면 합산이
        # 폭증할 수 있으므로 전체 content 합산도 제한한다 (#8).
        total = sum(len(m.content) for m in v)
        if total > settings.chat_max_total_chars:
            raise ValueError(
                f"전체 메시지 길이가 상한({settings.chat_max_total_chars}자)을 초과했습니다."
            )
        return v


@router.websocket("/chat")
async def chat_ws(ws: WebSocket, chat: ChatService = Depends(get_chat_service)) -> None:
    # CSWSH(Cross-Site WebSocket Hijacking) 방어 — CORS 미들웨어는 REST 만 보호하고
    # WS 핸드셰이크에는 적용되지 않으므로 accept 전에 Origin 을 직접 검증한다.
    # 허용 목록은 REST CORS 정책과 단일 소스인 settings.cors_origins 를 재사용.
    # Origin 헤더가 없는 연결(curl/wscat/TestClient 등 비브라우저)은 허용 —
    # 브라우저는 WS 핸드셰이크에 Origin 을 항상 첨부하므로 CSWSH 방어에 충분하다.
    origin = ws.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        logger.warning(f"[Chat] 허용되지 않은 Origin 의 WS 연결 거부: {origin}")
        await ws.close(code=1008)  # accept 전 close → 핸드셰이크가 HTTP 403 으로 거부됨
        return
    await ws.accept()
    # 한 프레임 원시 길이 상한 (#8) — JSON 파싱·검증 이전에 과대 프레임을 빠르게
    # 차단해 메모리/파싱 비용을 막는다. JSON 구조·이스케이프 오버헤드를 감안해
    # 총합 상한의 2배를 여유로 둔다.
    raw_limit = settings.chat_max_total_chars * 2
    try:
        while True:
            raw = await ws.receive_text()
            if len(raw) > raw_limit:
                logger.warning(f"[Chat] WS 과대 프레임 차단 — {len(raw)}자")
                await ws.send_json(
                    {"type": "error", "message": "메시지가 너무 깁니다."}
                )
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "JSON 파싱 실패"})
                continue

            # POST 와 동일하게 입력을 검증한다 — WS 라고 무검증으로 stream() 에 넘기면
            # 외부에서 role=system/tool 주입(프롬프트 탈취·가짜 tool 결과)이나
            # tool_calls 등 LLM 전용 키 주입이 가능해진다. ChatRequest 로 화이트리스트
            # 검증 + 개수/길이 상한(#8) + model_dump 로 {role, content} 만 남겨
            # 정규화한 뒤 stream() 에 전달.
            try:
                req = ChatRequest(messages=payload.get("messages", []))
            except ValidationError:
                logger.warning("[Chat] WS 메시지 검증 실패 — 차단")
                await ws.send_json(
                    {"type": "error", "message": "messages 형식이 올바르지 않습니다."}
                )
                continue

            user_messages = [m.model_dump() for m in req.messages]
            async for event in chat.stream(user_messages):
                await ws.send_json(event)
    except WebSocketDisconnect:
        logger.info("[Chat] WS 연결 종료")
    except Exception as e:
        logger.exception("[Chat] WS 오류")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


@router.post("/chat")
async def chat_http(
    req: ChatRequest,
    chat: ChatService = Depends(get_chat_service),
) -> dict:
    """스트리밍을 못 쓰는 환경(테스트·디버그·SSR 등) 용 폴백.

    동일한 tool-use 루프를 끝까지 돌린 뒤, 최종 텍스트와 tool 호출 로그를 반환.
    """
    text_parts: list[str] = []
    tool_log: list[dict] = []
    user_messages = [m.model_dump() for m in req.messages]

    async for event in chat.stream(user_messages):
        t = event["type"]
        if t == "text":
            text_parts.append(event["delta"])
        elif t == "tool_call":
            tool_log.append({"call": event["name"], "args": event["args"]})
        elif t == "tool_result":
            tool_log.append({
                "result_for": event["name"],
                "result": event["result"][:500],
            })
        elif t == "error":
            return {"error": event["message"], "text": "".join(text_parts), "tools": tool_log}

    return {"text": "".join(text_parts), "tools": tool_log}
