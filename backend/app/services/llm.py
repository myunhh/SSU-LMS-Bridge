# backend/app/services/llm.py
# litellm 래퍼 — openai / gemini / anthropic 멀티 프로바이더
"""LLM 채팅 서비스 — litellm 스트리밍 + MCP tool-use 루프.

흐름:
  1) registry 에서 MCP tool 목록을 OpenAI 함수 호출 스펙으로 가져옴
  2) litellm.acompletion(stream=True, tools=...) 호출
  3) 청크에 텍스트가 있으면 그대로 yield, tool_calls 가 누적되면 종료 후 dispatch
  4) tool 실행 결과를 messages 에 붙여 다시 호출 (multi-turn)
  5) finish_reason == "stop" 까지 반복

yield 이벤트 (UI 가 그대로 소비):
  {"type": "text",        "delta": str}
  {"type": "tool_call",   "name": str, "args": dict}
  {"type": "tool_result", "name": str, "result": str}
  {"type": "error",       "message": str}
  {"type": "done"}
"""
import json
from collections.abc import AsyncIterator
from typing import Any

import litellm
from loguru import logger

from app.config import Settings
from app.mcp_client.registry import McpRegistry


SYSTEM_PROMPT = """\
너는 숭실대학교 LMS(스마트캠퍼스) 데이터를 도와주는 학습 도우미야.

[사용 가능한 도구]
- Notion MCP (notion__*) : 공지/과제가 저장된 Notion DB 조회 · 갱신
- Obsidian MCP (obsidian__*) : 강의자료가 저장된 Vault 조회 · 검색 · 작성

[Notion DB ID 사용 규칙]
- 공지/과제 조회 전, 반드시 notion__ensure_db 로 db_id 를 먼저 얻어.
  공지 DB 의 title = "공지사항", 과제 DB 의 title = "과제".
- properties 인자는 DB 생성 시에만 의미가 있고 이미 있는 DB 면 무시되니,
  호출은 notion__ensure_db(title="공지사항", properties={}) 정도로 충분.
- 그렇게 얻은 db_id 를 notion__query_notices / notion__query_assignments 에 넘겨 조회.

[답변 규칙]
- 답은 한국어로, 가능한 구체적이고 친절하게.
- 도구 결과(JSON) 를 사용자에게 그대로 dump 하지 말고, 자연어로 정리해서 전달.
- 마감일은 "MM월 DD일 (요일)" 형태로 가독성 있게.
"""


class ChatService:
    def __init__(self, settings: Settings, registry: McpRegistry) -> None:
        self.settings = settings
        self.registry = registry
        # litellm 모델명: 프로바이더별 prefix 가 가장 안전
        provider = settings.llm_provider.lower()
        if provider == "openai":
            self.model = settings.llm_model
        else:
            self.model = f"{provider}/{settings.llm_model}"
        self.api_key = settings.llm_api_key

    async def stream(
        self,
        user_messages: list[dict[str, str]],
        max_iterations: int = 8,
    ) -> AsyncIterator[dict[str, Any]]:
        tools = await self.registry.list_tools_openai()
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(user_messages)

        for _ in range(max_iterations):
            tool_calls_acc: dict[int, dict[str, str]] = {}
            assistant_text = ""
            finish_reason: str | None = None

            try:
                response = await litellm.acompletion(
                    model=self.model,
                    messages=messages,
                    tools=tools or None,
                    stream=True,
                    api_key=self.api_key or None,
                )
            except Exception as e:
                logger.exception("[LLM] acompletion 실패")
                yield {"type": "error", "message": str(e)}
                return

            async for chunk in response:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta

                # 텍스트 델타
                content = getattr(delta, "content", None)
                if content:
                    assistant_text += content
                    yield {"type": "text", "delta": content}

                # tool_calls 델타 (chunk 별로 부분 누적)
                for tc in (getattr(delta, "tool_calls", None) or []):
                    idx = getattr(tc, "index", 0)
                    slot = tool_calls_acc.setdefault(idx, {"id": "", "name": "", "args": ""})
                    if getattr(tc, "id", None):
                        slot["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn:
                        if getattr(fn, "name", None):
                            slot["name"] = fn.name
                        if getattr(fn, "arguments", None):
                            slot["args"] += fn.arguments

                if choice.finish_reason:
                    finish_reason = choice.finish_reason

            # 스트림 종료 — 분기
            if finish_reason in ("stop", "length", "end_turn") and not tool_calls_acc:
                yield {"type": "done"}
                return

            if not tool_calls_acc:
                # tool_calls 도 finish 도 없는 비정상 종료
                yield {"type": "done"}
                return

            # tool_calls 누적분 → assistant 메시지로 messages 에 추가
            tc_list: list[dict[str, Any]] = []
            for idx in sorted(tool_calls_acc.keys()):
                t = tool_calls_acc[idx]
                tc_list.append({
                    "id": t["id"] or f"call_{idx}",
                    "type": "function",
                    "function": {"name": t["name"], "arguments": t["args"] or "{}"},
                })
            messages.append({
                "role": "assistant",
                "content": assistant_text or None,
                "tool_calls": tc_list,
            })

            # 각 tool 실행 → tool 결과 메시지 추가
            for tc in tc_list:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield {"type": "tool_call", "name": name, "args": args}

                try:
                    result = await self.registry.call(name, args)
                except Exception as e:
                    logger.exception(f"[MCP] tool 호출 실패: {name}")
                    result = f"ERROR: {e}"

                yield {"type": "tool_result", "name": name, "result": result}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": result,
                })

        yield {"type": "error", "message": f"max_iterations={max_iterations} 초과"}
