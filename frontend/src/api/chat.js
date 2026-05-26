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
    ws = new WebSocket(`${WS_BASE}/api/chat`);
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

  return close;
}
