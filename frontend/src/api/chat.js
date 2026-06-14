// frontend/src/api/chat.js
// ──────────────────────────────────────────────────────────────────────────────
// 백엔드 WebSocket /api/chat 스트리밍 클라이언트.
//
// 백엔드(ChatService.stream)가 보내는 이벤트:
//   { type: "text",        delta }
//   { type: "tool_call",   name, args }
//   { type: "tool_result", name, result }
//   { type: "error",       message }
//   { type: "done" }
//
// 클라이언트는 연결 직후 { messages: [{role, content}, ...] } 를 1회 전송한다.
// ──────────────────────────────────────────────────────────────────────────────
import { WS_BASE } from '../data/uiConfig';

/**
 * 채팅 스트림을 연다.
 * @returns {() => void} 취소(WS 닫기) 함수
 */
export function openChatStream({ messages, onText, onToolCall, onToolResult, onError, onDone }) {
  let ws;
  try {
    // WS_BASE 미설정 시(frontend/.env 없음) 현재 페이지 호스트로 폴백 —
    // vite dev proxy(ws: true)가 /api/chat 업그레이드를 백엔드로 중계한다.
    // 구형 브라우저는 상대 URL WebSocket 에서 SyntaxError 를 던지므로 절대 URL 필수.
    const base = WS_BASE
      || `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;
    ws = new WebSocket(`${base}/api/chat`);
  } catch {
    onError?.('채팅 서버에 연결할 수 없습니다.');
    return () => {};
  }

  let closed = false;
  const close = () => {
    if (!closed) { closed = true; try { ws.close(); } catch { /* noop */ } }
  };

  ws.onopen = () => ws.send(JSON.stringify({ messages }));

  ws.onmessage = (e) => {
    if (closed) return; // close() 직후 수신 큐에 남아 있던 이벤트가 콜백을 다시 부르는 것 차단
    let ev;
    try { ev = JSON.parse(e.data); } catch { return; }
    switch (ev.type) {
      case 'text':        onText?.(ev.delta || ''); break;
      case 'tool_call':   onToolCall?.(ev.name, ev.args); break;
      case 'tool_result': onToolResult?.(ev.name, ev.result); break;
      case 'error':       onError?.(ev.message || '알 수 없는 오류'); close(); break;
      case 'done':        onDone?.(); close(); break;
      default: break;
    }
  };

  ws.onerror = () => { onError?.('채팅 연결 오류 (백엔드 실행을 확인하세요).'); close(); };

  // done/error 이벤트 없이 소켓이 닫힌 경우(uvicorn 재시작, 네트워크 단절 등) —
  // 콜백이 한 번도 불리지 않으면 호출 측 streaming 상태가 영원히 풀리지 않으므로 여기서 통지한다.
  // 정상 경로(done/error/onerror)는 모두 close()로 closed=true 가 된 뒤라 중복 호출 없음.
  ws.onclose = () => {
    if (!closed) {
      closed = true;
      onError?.('연결이 종료되었습니다. 다시 시도해 주세요.');
    }
  };

  return close;
}
