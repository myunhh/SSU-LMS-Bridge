"""ChatService.stream — litellm 스트리밍 + MCP tool-use 루프 단위 테스트.

litellm.acompletion 을 patch 해서 chunk sequence 를 가짜로 흘려보내고,
ChatService 가 yield 하는 이벤트 순서와 messages 누적 로직을 검증한다.
실제 LLM 키 / SSE 연결 없이 동작.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import litellm

from app.services.llm import ChatService

# ── 헬퍼 ──────────────────────────────────────────────────────

def _settings(provider="anthropic", model="claude-haiku-4-5", api_key="dummy"):
    return SimpleNamespace(
        llm_provider=provider, llm_model=model, llm_api_key=api_key,
    )


def _registry(tools=None, call_result="tool_output"):
    reg = SimpleNamespace()
    reg.list_tools_openai = AsyncMock(return_value=tools or [])
    reg.call = AsyncMock(return_value=call_result)
    return reg


def _chunk(content=None, tool_calls=None, finish_reason=None):
    """litellm chunk 모양: chunk.choices[0].delta(.content / .tool_calls), .finish_reason."""
    delta = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _tc(index, id_, name=None, args=None):
    """tool_call chunk delta — id/name 은 첫 chunk 에만, args 는 여러 chunk 에 걸쳐 부분 누적."""
    return SimpleNamespace(
        index=index,
        id=id_,
        function=SimpleNamespace(name=name, arguments=args),
    )


async def _async_iter(chunks):
    for c in chunks:
        yield c


async def _broken_iter(chunks, exc):
    """chunk 들을 흘려보낸 뒤 mid-stream 예외를 raise 하는 async iterator."""
    for c in chunks:
        yield c
    raise exc


# ── 모델명 prefix 결정 로직 ───────────────────────────────────

def test_model_prefix_anthropic():
    svc = ChatService(_settings(provider="anthropic", model="claude-haiku-4-5"), _registry())
    assert svc.model == "anthropic/claude-haiku-4-5"


def test_model_prefix_openai_keeps_raw():
    svc = ChatService(_settings(provider="openai", model="gpt-4o"), _registry())
    assert svc.model == "gpt-4o"


def test_model_prefix_gemini():
    svc = ChatService(_settings(provider="gemini", model="gemini-2.0-flash"), _registry())
    assert svc.model == "gemini/gemini-2.0-flash"


# ── 단발 텍스트 (tool 없이) ───────────────────────────────────

async def test_stream_plain_text_then_done():
    chunks = [
        _chunk(content="안녕"),
        _chunk(content="하세요"),
        _chunk(finish_reason="stop"),
    ]
    with patch(
        "app.services.llm.litellm.acompletion",
        AsyncMock(return_value=_async_iter(chunks)),
    ):
        svc = ChatService(_settings(), _registry())
        events = [e async for e in svc.stream([{"role": "user", "content": "hi"}])]

    text = "".join(e["delta"] for e in events if e["type"] == "text")
    assert text == "안녕하세요"
    assert events[-1] == {"type": "done"}


# ── 멀티턴: tool_call → dispatch → 결과 주입 → 자연어 답변 ───

async def test_stream_tool_call_dispatched_and_result_fed_back():
    # 턴 1: ensure_db 호출 누적 → finish_reason=tool_calls
    turn1 = [
        _chunk(tool_calls=[_tc(0, "call_123", name="notion__ensure_db")]),
        _chunk(tool_calls=[_tc(0, "", args='{"title":"공지사항"')]),
        _chunk(tool_calls=[_tc(0, "", args=', "properties":{}}')]),
        _chunk(finish_reason="tool_calls"),
    ]
    # 턴 2: 결과 받고 자연어 응답
    turn2 = [
        _chunk(content="DB ID 는 abc 입니다."),
        _chunk(finish_reason="stop"),
    ]
    calls = iter([_async_iter(turn1), _async_iter(turn2)])

    async def fake_acompletion(*args, **kwargs):
        return next(calls)

    reg = _registry(call_result="db-id-abc")
    with patch("app.services.llm.litellm.acompletion", side_effect=fake_acompletion):
        svc = ChatService(_settings(), reg)
        events = [e async for e in svc.stream([{"role": "user", "content": "DB 만들어"}])]

    # tool_call / tool_result 이벤트 검증
    tool_call = next(e for e in events if e["type"] == "tool_call")
    assert tool_call["name"] == "notion__ensure_db"
    assert tool_call["args"] == {"title": "공지사항", "properties": {}}

    tool_result = next(e for e in events if e["type"] == "tool_result")
    assert tool_result["name"] == "notion__ensure_db"
    assert tool_result["result"] == "db-id-abc"

    # registry.call 이 정확한 이름·인자로 한 번 호출됨
    reg.call.assert_awaited_once_with("notion__ensure_db", {"title": "공지사항", "properties": {}})

    # 자연어 응답이 그 다음에 흘러나옴
    text = "".join(e["delta"] for e in events if e["type"] == "text")
    assert "DB ID" in text
    assert events[-1] == {"type": "done"}


# ── tool 실행 실패도 안전하게 처리 ────────────────────────────

async def test_stream_tool_error_yields_error_string_and_continues():
    turn1 = [
        _chunk(tool_calls=[_tc(0, "x", name="notion__broken", args="{}")]),
        _chunk(finish_reason="tool_calls"),
    ]
    turn2 = [
        _chunk(content="실패했어요"),
        _chunk(finish_reason="stop"),
    ]
    calls = iter([_async_iter(turn1), _async_iter(turn2)])

    async def fake_acompletion(*args, **kwargs):
        return next(calls)

    reg = _registry()
    reg.call = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("app.services.llm.litellm.acompletion", side_effect=fake_acompletion):
        svc = ChatService(_settings(), reg)
        events = [e async for e in svc.stream([{"role": "user", "content": "x"}])]

    tool_result = next(e for e in events if e["type"] == "tool_result")
    assert tool_result["result"].startswith("ERROR")
    assert events[-1] == {"type": "done"}


# ── 안전장치: 무한 tool_call 루프는 max_iterations 에서 차단 ──

async def test_stream_max_iterations_safeguard():
    def make_loop_turn():
        return _async_iter([
            _chunk(tool_calls=[_tc(0, "id", name="notion__loop", args="{}")]),
            _chunk(finish_reason="tool_calls"),
        ])

    async def fake_acompletion(*args, **kwargs):
        return make_loop_turn()

    reg = _registry(call_result="x")
    with patch("app.services.llm.litellm.acompletion", side_effect=fake_acompletion):
        svc = ChatService(_settings(), reg)
        events = [e async for e in svc.stream(
            [{"role": "user", "content": "?"}], max_iterations=3,
        )]

    assert events[-1]["type"] == "error"
    assert "max_iterations" in events[-1]["message"]


# ── acompletion 자체가 실패하면 error 한 번만 yield 후 종료 ──

async def test_stream_acompletion_exception_yields_error_event():
    with patch(
        "app.services.llm.litellm.acompletion",
        AsyncMock(side_effect=RuntimeError("connect refused")),
    ):
        svc = ChatService(_settings(), _registry())
        events = [e async for e in svc.stream([{"role": "user", "content": "?"}])]

    assert events == [{"type": "error", "message": "connect refused"}]


# ── 스트림 소비 중(mid-stream) 예외 — error 이벤트 계약 유지 ──

async def test_stream_midstream_exception_yields_error_event():
    """chunk 일부 수신 후 끊겨도 예외가 소비자로 전파되지 않고 error 이벤트로 끝나야 한다."""
    broken = _broken_iter([_chunk(content="부분")], RuntimeError("connection reset"))
    with patch(
        "app.services.llm.litellm.acompletion",
        AsyncMock(return_value=broken),
    ):
        svc = ChatService(_settings(), _registry())
        events = [e async for e in svc.stream([{"role": "user", "content": "?"}])]

    # 이미 흘러나온 텍스트 델타는 유지되고, 마지막 이벤트는 error
    assert events[0] == {"type": "text", "delta": "부분"}
    assert events[-1] == {"type": "error", "message": "connection reset"}


async def test_stream_midstream_auth_error_yields_korean_guide():
    """mid-stream 인증 실패도 acompletion 호출 실패와 동일한 한국어 안내를 yield 후 종료."""
    auth_exc = litellm.AuthenticationError(
        message="bad key", llm_provider="anthropic", model="claude-haiku-4-5",
    )
    broken = _broken_iter([_chunk(content="부분")], auth_exc)
    with patch(
        "app.services.llm.litellm.acompletion",
        AsyncMock(return_value=broken),
    ):
        svc = ChatService(_settings(), _registry())
        events = [e async for e in svc.stream([{"role": "user", "content": "?"}])]

    assert events[0] == {"type": "text", "delta": "부분"}
    assert events[-1]["type"] == "error"
    assert "LLM_API_KEY" in events[-1]["message"]
