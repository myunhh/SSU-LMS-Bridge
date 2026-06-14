"""WS/POST /api/chat — Origin 검증·이벤트 포워딩·입력 상한 회귀 테스트 (오프라인).

CORS 미들웨어는 REST 요청만 보호하고 WebSocket 핸드셰이크에는 적용되지 않는다.
chat_ws 는 accept 전에 Origin 헤더를 settings.cors_origins 와 대조해
허용되지 않은 브라우저 출처의 연결(Cross-Site WebSocket Hijacking)을 차단해야 한다.

검증 항목
---------
Origin (CSWSH):
- 악성 Origin(http://evil.example) → accept 전 close(1008) 로 핸드셰이크 거부
- 'Origin: null'(file:// 등)        → 허용 목록에 없으므로 거부
- 허용 Origin(프론트 dev 서버)       → 연결 성공
- Origin 헤더 없음(비브라우저)        → 연결 성공 (curl/wscat/TestClient 워크플로 보존)

이벤트 포워딩 (#10):
- WS: stream() 이 yield 한 text/tool_call/tool_result/text/done 이벤트가
  순서·스키마 그대로 클라이언트에 전달되는지 (receive_json 순차 단언)
- WS: 더미가 받은 messages 를 기록 → payload(role/content)가 stream() 까지
  정상 전달되는지
- POST: text 누적("안"+"녕") + error 시 단축 반환

입력 상한 (#8):
- POST/WS: 메시지 개수 / 개별 content 길이 / 총합 길이 초과 시 거부

외부 의존 0 — get_chat_service 는 더미로 교체한다
(test_connectors_status.py 의 경량 앱 + settings 격리 패턴).
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.deps import get_chat_service
from app.api.routes import chat
from app.config import settings


class _DummyChatService:
    """LLM/MCP 를 전혀 호출하지 않는 더미 — 핸드셰이크 검증에는 stream 불필요."""

    async def stream(self, messages):
        yield {"type": "done"}


# stream() 이 내보내는 전형적인 이벤트 시퀀스 (text → tool_call → tool_result →
# text → done). 포워딩 루프가 이 순서·스키마를 그대로 전달하는지 검증한다.
_EVENT_SEQUENCE = [
    {"type": "text", "delta": "안"},
    {"type": "tool_call", "name": "lms__list_deadlines", "args": {"x": 1}},
    {"type": "tool_result", "name": "lms__list_deadlines", "result": "[]"},
    {"type": "text", "delta": "녕"},
    {"type": "done"},
]


class _RecordingChatService:
    """고정 이벤트 시퀀스를 yield 하고, 받은 messages 를 기록하는 더미."""

    def __init__(self, events):
        self._events = events
        self.received = None  # 마지막 stream() 호출이 받은 messages

    async def stream(self, messages):
        self.received = messages
        for ev in self._events:
            yield ev


@pytest.fixture(autouse=True)
def fixed_frontend_port(monkeypatch):
    """cors_origins 가 실제 .env 값에 흔들리지 않도록 포트 고정."""
    monkeypatch.setattr(settings, "frontend_port", 3000)


@pytest.fixture()
def client():
    """chat 라우터만 올린 경량 앱 (lifespan/스케줄러 미기동)."""
    app = FastAPI()
    app.include_router(chat.router, prefix="/api")
    app.dependency_overrides[get_chat_service] = lambda: _DummyChatService()
    return TestClient(app)


def _assert_handler_alive(ws) -> None:
    """accept 이후 핸들러 루프가 살아있는지 — ChatService 호출 없이 검증 가능한
    JSON 파싱 오류 경로로 확인한다."""
    ws.send_text("json 아님")
    assert ws.receive_json() == {"type": "error", "message": "JSON 파싱 실패"}


# ── 거부 케이스 ────────────────────────────────────────────────


def test_ws_rejects_unallowed_origin(client):
    """허용 목록에 없는 Origin → accept 전 close(1008) 로 핸드셰이크 거부."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/chat", headers={"origin": "http://evil.example"}):
            pass
    assert exc_info.value.code == 1008


def test_ws_rejects_null_origin(client):
    """file:// 등에서 오는 'Origin: null' 도 허용 목록에 없으므로 거부."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/chat", headers={"origin": "null"}):
            pass
    assert exc_info.value.code == 1008


# ── 허용 케이스 ────────────────────────────────────────────────


def test_ws_accepts_allowed_origin(client):
    """프론트 dev 서버 출처(settings.cors_origins)는 연결 허용."""
    with client.websocket_connect("/api/chat", headers={"origin": "http://localhost:3000"}) as ws:
        _assert_handler_alive(ws)


def test_ws_accepts_allowed_origin_127(client):
    """127.0.0.1 변형 출처도 cors_origins 에 포함되므로 허용."""
    with client.websocket_connect("/api/chat", headers={"origin": "http://127.0.0.1:3000"}) as ws:
        _assert_handler_alive(ws)


def test_ws_accepts_missing_origin(client):
    """Origin 헤더가 없는 비브라우저 클라이언트(curl/wscat/TestClient)는 허용."""
    with client.websocket_connect("/api/chat") as ws:
        _assert_handler_alive(ws)


# ── 이벤트 포워딩 루프 (#10) ──────────────────────────────────────


@pytest.fixture()
def recording_service():
    return _RecordingChatService(_EVENT_SEQUENCE)


@pytest.fixture()
def recording_client(recording_service):
    """stream() 이 고정 시퀀스를 yield 하는 더미를 주입한 경량 앱."""
    app = FastAPI()
    app.include_router(chat.router, prefix="/api")
    app.dependency_overrides[get_chat_service] = lambda: recording_service
    return TestClient(app)


def test_ws_forwards_events_in_order(recording_client, recording_service):
    """stream() 의 각 이벤트가 순서·스키마 그대로 WS 로 전달된다 (#10)."""
    with recording_client.websocket_connect("/api/chat") as ws:
        ws.send_json({"messages": [{"role": "user", "content": "안녕"}]})
        received = [ws.receive_json() for _ in _EVENT_SEQUENCE]
    # 순서·스키마 완전 일치 — 포워딩 루프가 이벤트를 변형하지 않아야 한다.
    assert received == _EVENT_SEQUENCE


def test_ws_passes_messages_to_stream(recording_client, recording_service):
    """클라이언트가 보낸 messages(role/content)가 stream() 까지 정상 전달된다."""
    payload = [{"role": "user", "content": "이번 주 마감 과제 알려줘"}]
    with recording_client.websocket_connect("/api/chat") as ws:
        ws.send_json({"messages": payload})
        for _ in _EVENT_SEQUENCE:
            ws.receive_json()
    # 더미가 기록한 messages — ChatRequest model_dump 로 {role, content} 만 남는다.
    assert recording_service.received == payload


def test_post_accumulates_text_and_tool_log(recording_client):
    """POST 는 text 델타를 누적("안"+"녕")하고 tool 호출을 로그로 모은다 (#10)."""
    resp = recording_client.post(
        "/api/chat", json={"messages": [{"role": "user", "content": "안녕"}]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "안녕"
    assert body["tools"] == [
        {"call": "lms__list_deadlines", "args": {"x": 1}},
        {"result_for": "lms__list_deadlines", "result": "[]"},
    ]
    assert "error" not in body


def test_post_error_short_circuits(client):
    """stream() 이 error 이벤트를 내면 POST 는 즉시 단축 반환한다 (#10)."""
    error_events = [
        {"type": "text", "delta": "부분"},
        {"type": "error", "message": "LLM 실패"},
        {"type": "text", "delta": "여기는 안 옴"},
    ]
    app = FastAPI()
    app.include_router(chat.router, prefix="/api")
    app.dependency_overrides[get_chat_service] = lambda: _RecordingChatService(error_events)
    c = TestClient(app)
    resp = c.post("/api/chat", json={"messages": [{"role": "user", "content": "x"}]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] == "LLM 실패"
    assert body["text"] == "부분"  # error 이전 텍스트만 누적, 이후 이벤트 무시


# ── 입력 상한 (#8) ───────────────────────────────────────────────


def test_post_rejects_too_many_messages(client):
    """메시지 개수 상한 초과 → POST 422 (pydantic Field)."""
    over = settings.chat_max_messages + 1
    msgs = [{"role": "user", "content": "x"} for _ in range(over)]
    resp = client.post("/api/chat", json={"messages": msgs})
    assert resp.status_code == 422


def test_post_rejects_too_long_content(client):
    """개별 content 길이 상한 초과 → POST 422."""
    big = "가" * (settings.chat_max_content_chars + 1)
    resp = client.post("/api/chat", json={"messages": [{"role": "user", "content": big}]})
    assert resp.status_code == 422


def test_post_rejects_total_over_limit(client, monkeypatch):
    """개별은 통과하나 합산이 총합 상한 초과 → POST 422."""
    # 개별 상한은 넉넉히, 총합 상한만 낮춰 합산 초과 경로를 정확히 친다.
    monkeypatch.setattr(settings, "chat_max_total_chars", 10)
    msgs = [{"role": "user", "content": "12345"}, {"role": "user", "content": "67890!"}]
    resp = client.post("/api/chat", json={"messages": msgs})
    assert resp.status_code == 422


def test_ws_rejects_too_long_content(client):
    """WS 도 동일 검증 — 과대 content 는 error 이벤트로 거부(연결 유지)."""
    big = "나" * (settings.chat_max_content_chars + 1)
    with client.websocket_connect("/api/chat") as ws:
        ws.send_json({"messages": [{"role": "user", "content": big}]})
        ev = ws.receive_json()
        assert ev["type"] == "error"


def test_ws_rejects_too_many_messages(client):
    """WS 메시지 개수 상한 초과 → error 이벤트."""
    over = settings.chat_max_messages + 1
    msgs = [{"role": "user", "content": "x"} for _ in range(over)]
    with client.websocket_connect("/api/chat") as ws:
        ws.send_json({"messages": msgs})
        ev = ws.receive_json()
        assert ev["type"] == "error"
