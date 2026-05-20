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
from pydantic import BaseModel

from app.api.deps import get_chat_service
from app.services.llm import ChatService


router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@router.websocket("/chat")
async def chat_ws(ws: WebSocket, chat: ChatService = Depends(get_chat_service)) -> None:
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "JSON 파싱 실패"})
                continue

            user_messages = payload.get("messages", [])
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
