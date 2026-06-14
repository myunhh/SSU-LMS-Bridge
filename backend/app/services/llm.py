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

# 외부(클라이언트)에서 받을 수 있는 role — system/tool 은 서버만 주입한다.
# 라우트(chat.py)가 1차 검증하지만, stream() 이 POST 폴백·테스트·다른 호출자에게도
# 직접 노출되므로 여기서도 방어적으로 한 번 더 정규화한다(심층 방어).
_ALLOWED_INPUT_ROLES = ("user", "assistant")


def _sanitize_user_messages(
    user_messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """클라이언트 입력 메시지를 {role, content} 로만 정규화한다.

    - role 이 user/assistant 가 아니면(system/tool 등) 그 메시지는 버린다 —
      프롬프트 탈취(system) · 가짜 tool 결과 주입(tool) 차단.
    - tool_calls / tool_call_id / function_call / name 등 LLM 전용 키는 제거 —
      assistant 메시지로 위장한 tool_calls 주입 차단.
    - content 가 str 이 아니면 버린다(멀티모달/구조화 입력 미지원).
    """
    clean: list[dict[str, Any]] = []
    for m in user_messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role not in _ALLOWED_INPUT_ROLES or not isinstance(content, str):
            continue
        clean.append({"role": role, "content": content})
    return clean


SYSTEM_PROMPT = """\
너는 숭실대학교 LMS(스마트캠퍼스) 데이터를 도와주는 학습 도우미야.

[사용 가능한 도구]
- LMS MCP (lms__*) : 숭실대 LMS 에서 강의·과제·공지·자료를 **실시간 직접 조회** (읽기 전용)
- Notion MCP (notion__*) : 공지/과제가 저장된 Notion DB 조회 · 갱신
- Obsidian MCP (obsidian__*) : 공지·과제 노트가 저장된 Obsidian Vault 조회 · 검색 · 작성
- 학습 도우미 MCP (study__*) : 공지/과제 본문으로 만든 퀴즈·플래시카드 저장 · 조회 · 복습(SRS)

[실시간 조회 우선 규칙]
- 강의/과제/공지/자료 질문은 lms__* 도구로 LMS 를 직접 조회하는 것을 우선해.
  (Notion 은 하루 1회 동기화 스냅샷이라, 최신 마감·신규 공지는 lms__* 가 더 정확.)
- 전 과목 마감은 lms__list_deadlines, 전 과목 공지는 lms__list_notices(course_id 생략).
- 특정 과목 과제/자료/토론은 course_id 가 필요해 — 먼저 lms__list_courses 로 과목 id 를 얻어.
- "LMS 세션이 없습니다 ..." 가 오면 사용자에게 로그인이 필요하다고 안내.

[Notion DB ID 사용 규칙]
- 공지/과제 조회 전, 반드시 notion__ensure_db 로 db_id 를 먼저 얻어.
  공지 DB 의 title = "공지사항", 과제 DB 의 title = "과제".
- properties 인자는 DB 생성 시에만 의미가 있고 이미 있는 DB 면 무시되니,
  호출은 notion__ensure_db(title="공지사항", properties={}) 정도로 충분.
- 그렇게 얻은 db_id 를 notion__query_notices / notion__query_assignments 에 넘겨 조회.

[학습 도우미(study__*) 사용 규칙]
- 퀴즈·플래시카드의 *문항 생성*은 네 몫이야. lms__list_notices / lms__list_assignments
  로 본문을 읽어 직접 문항(질문/정답/해설)·카드(앞면/뒷면)를 만든 뒤,
  study__save_quiz / study__save_deck 로 저장만 해(생성은 MCP 가 하지 않아).
  저장 시 source 에 {kind, course, ref_id} 를 넣어 출처를 남기면 좋아.
- "복습하자/오늘 외울 거" 요청이면 study__review_due 로 due 가 된 카드를 받아
  앞면만 사용자에게 출제하고, 사용자 답을 채점한 뒤 study__grade_card(correct=…)
  로 결과를 반영해(틀리면 다음날 다시, 맞히면 간격이 늘어남).
- 저장된 퀴즈·덱 목록은 study__list_quizzes / study__list_decks, 특정 퀴즈 전체
  (정답 포함)는 study__get_quiz 로 조회해.

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
        # 심층 방어 — 라우트 검증을 우회한 호출자에 대비해 한 번 더 sanitize.
        messages.extend(_sanitize_user_messages(user_messages))

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
            except litellm.AuthenticationError:
                logger.warning("[LLM] 인증 실패 — API 키 미설정/무효")
                yield {
                    "type": "error",
                    "message": "LLM API 키가 설정되지 않았거나 유효하지 않습니다. "
                               ".env 의 LLM_API_KEY 를 확인하세요.",
                }
                return
            except Exception as e:
                logger.exception("[LLM] acompletion 실패")
                yield {"type": "error", "message": str(e)}
                return

            # 스트림 소비 중 예외(레이트리밋·네트워크 단절·mid-stream 오류)도
            # error 이벤트로 변환해야 WS/POST 소비자의 이벤트 계약이 지켜진다.
            # 주의: except 를 BaseException 으로 넓히지 말 것 —
            # GeneratorExit/CancelledError 는 그대로 전파돼야 aclose 정리가 정상 동작.
            try:
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
            except litellm.AuthenticationError:
                logger.warning("[LLM] 인증 실패 — API 키 미설정/무효 (스트림 소비 중)")
                yield {
                    "type": "error",
                    "message": "LLM API 키가 설정되지 않았거나 유효하지 않습니다. "
                               ".env 의 LLM_API_KEY 를 확인하세요.",
                }
                return
            except Exception as e:
                logger.exception("[LLM] 스트림 소비 실패")
                yield {"type": "error", "message": str(e)}
                return

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
