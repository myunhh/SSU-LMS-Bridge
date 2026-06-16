/* Chat / LLM Assistant view */
import { useState as chS, useEffect as chE, useRef as chR } from 'react';
import { useData } from '../data/DataStore';
import { openChatStream } from '../api/chat';
import { CHAT_MODEL_LABEL, CHAT_FOOTER_NOTE, CHAT_TOOLS_LABEL } from '../data/uiConfig';
import Ich from './icons';

/* ============== Chat ============== */
function ChatView() {
  const {
    suggestions: SUGGESTIONS,
    conversations: CONVERSATIONS,
    activeConversationId, activeMessages,
    startNewConversation, selectConversation, saveActiveMessages, deleteConversation,
    connectors,
    pendingChatPrompt, clearPendingChatPrompt,
  } = useData();

  // 푸터 모델 라벨 — connectors 의 llm 항목 meta('provider · model')에서 모델명만 표시.
  // 미연결/미로딩이면 CHAT_MODEL_LABEL(uiConfig) 폴백. meta 가 'provider · model' 형식일
  // 때만 ' · ' 뒤 모델명을 쓰고, '상태 미확인'·'LLM_API_KEY 미설정' 같은 안내 문구는 폴백.
  const llm = connectors?.find(c => c.id === 'llm');
  const modelLabel = (() => {
    if (llm?.status === 'connected' && typeof llm.meta === 'string' && llm.meta.includes(' · ')) {
      const model = llm.meta.split(' · ').pop().trim();
      if (model) return model;
    }
    return CHAT_MODEL_LABEL;
  })();

  // 화면에 그릴 메시지 버퍼. 진리값은 DataStore(activeMessages) — 전환/새로고침 시
  // 아래 effect 가 다시 로드한다. 스트리밍은 이 버퍼에서 매끄럽게 누적하고,
  // 매 갱신마다 saveActiveMessages 로 영속 스토어에 반영한다.
  const [msgs, setMsgs] = chS(activeMessages);
  const [input, setInput] = chS('');
  const [streaming, setStreaming] = chS(false);
  const scrollRef = chR(null);
  const closeRef = chR(null); // 진행 중인 채팅 스트림의 close 함수 — 언마운트/새 대화 시 닫기 위해 보관
  // 직전에 본 활성 대화 id. 복원 effect 가 '진짜 대화 전환'과
  // 'send 가 첫 전송 시 새 대화를 만들어 null→c<ts> 로 바뀐 것'을 구분하는 기준.
  const prevConvIdRef = chR(activeConversationId);
  // send 가 활성 대화 없이(첫 전송) 스트림을 열면 true. 이때 saveActiveMessages 가
  // null→새 대화 를 만들어 activeConversationId 가 바뀌어도 복원 effect 는 한 번 건너뛴다.
  const sendCreatedConvRef = chR(false);

  // 활성 대화가 바뀌면(사이드바 전환·새 대화·삭제) 그 대화의 메시지를 버퍼로 복원.
  // 스트리밍 중이면 진행 중 스트림을 닫고 새 대화로 전환한다.
  chE(() => {
    const prev = prevConvIdRef.current;
    prevConvIdRef.current = activeConversationId;
    // send 가 첫 전송에서 null→새 대화 로 만든 전환이면(스트림은 이미 열려 있음)
    // 복원하지 않는다 — 안 그러면 방금 연 WS 를 닫고 placeholder 까지 날려 무음 실패가 된다.
    if (sendCreatedConvRef.current && !prev && activeConversationId) {
      sendCreatedConvRef.current = false;
      return;
    }
    sendCreatedConvRef.current = false;
    closeRef.current?.();
    closeRef.current = null;
    setStreaming(false);
    setMsgs(activeMessages);
    // activeMessages 는 매 렌더 새 참조라 deps 에 넣으면 매번 덮어써 스트리밍이 끊긴다.
    // 전환 신호는 activeConversationId 하나로 충분.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeConversationId]);

  chE(() => { scrollRef.current?.scrollTo({ top: 99999, behavior: 'smooth' }); }, [msgs, streaming]);

  // 언마운트 시 열려 있는 스트림 정리 — 언마운트된 컴포넌트에 setMsgs 가 호출되는 누수 방지
  chE(() => () => { closeRef.current?.(); }, []);

  // 백엔드 WS /api/chat 로 스트리밍 — ChatService(litellm + MCP tool-use)
  const send = (text) => {
    const v = text ?? input;
    if (!v.trim() || streaming) return;
    const now = new Date();
    const t = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
    const userMsg = { role: 'user', text: v, t };

    // 직전 실제 대화 + 새 user 메시지 → 백엔드 페이로드
    const history = [...msgs, userMsg]
      .filter(m => m.text && !m.error)
      .map(m => ({ role: m.role, content: m.text }));

    // user 메시지 + 스트리밍될 assistant placeholder 추가.
    // user 메시지가 들어오는 순간 영속화 → 제목이 즉시 사이드바에 반영되고
    // 응답 도중 새로고침해도 질문은 보존된다 (placeholder 는 저장에서 제외).
    // 마지막 user 발화 직전 버퍼를 보관해 두면 스트림 종료 시 최종본을 만들 수 있다.
    const baseMsgs = [...msgs, userMsg];
    setMsgs([...baseMsgs, { role: 'assistant', t, text: '', live: true }]);
    // 활성 대화가 없으면(첫 전송·마지막 대화 삭제 직후) saveActiveMessages 가 새 대화를
    // 만들며 activeConversationId 를 null→c<ts> 로 바꾼다. 그 전환을 복원 effect 가
    // '대화 전환'으로 오인해 방금 연 스트림을 닫지 않도록 플래그를 세워 둔다.
    if (!activeConversationId) sendCreatedConvRef.current = true;
    saveActiveMessages(baseMsgs);   // 질문 즉시 영속화 (side-effect 는 updater 밖에서)
    setInput('');
    setStreaming(true);

    let acc = '';
    // 진행 중인 MCP 도구명 — replaceLast 가 메시지를 통째로 재구성하므로 onText 에서도 함께 실어야 유지됨
    let liveTool = null;
    const replaceLast = (patch) => setMsgs(m => {
      const copy = [...m];
      copy[copy.length - 1] = { role: 'assistant', t, ...patch };
      return copy;
    });

    // 스트림 종료 시 최종 메시지를 영속 스토어에 반영.
    // live 플래그를 떼고(저장은 정적 스냅샷) 저장한다. side-effect 는 updater 밖에서.
    const persist = (finalText, extra = {}) => {
      const finalMsgs = [...baseMsgs, { role: 'assistant', t, text: finalText, ...extra }];
      setMsgs(finalMsgs);
      saveActiveMessages(finalMsgs);
    };

    closeRef.current = openChatStream({
      messages: history,
      onText: (delta) => { acc += delta; replaceLast({ text: acc, live: true, tool: liveTool }); },
      // MCP 도구 실행 구간 표시 — tool_call 에서 도구명 노출, tool_result 에서 제거
      onToolCall: (name) => { liveTool = name; replaceLast({ text: acc, live: true, tool: name }); },
      onToolResult: () => { liveTool = null; replaceLast({ text: acc, live: true }); },
      onError: (msg) => { persist(acc || `⚠️ ${msg}`, { error: true }); setStreaming(false); closeRef.current = null; },
      onDone: () => { persist(acc || '(응답이 비어 있습니다)'); setStreaming(false); closeRef.current = null; },
    });
  };

  // 항상 최신 send 참조 — 아래 자동 전송 effect 가 stale closure 를 쓰지 않도록.
  const sendRef = chR(send);
  sendRef.current = send;

  // 다른 페이지(MCP '실행' 버튼)가 예약한 프롬프트를 자동 전송한다.
  // setTimeout(0) 으로 활성 대화 복원 effect 이후로 미뤄 안전하게 전송한다.
  // ⚠️ clear 는 반드시 전송 '후'(timeout 콜백 안)에 한다 — 전송 전에 clear 하면
  //    pendingChatPrompt 변경 → 리렌더 → 이 effect 의 cleanup 이 timeout 을 취소해
  //    전송이 영영 안 된다(StrictMode 면 더 확실히 취소됨).
  chE(() => {
    if (!pendingChatPrompt) return;
    const prompt = pendingChatPrompt;
    const id = setTimeout(() => {
      sendRef.current?.(prompt);
      clearPendingChatPrompt();
    }, 0);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingChatPrompt]);

  return (
    <div className="flex h-[calc(100vh-58px)]">
      {/* Conversation list */}
      <aside className="w-[260px] shrink-0 border-r border-[var(--line)] bg-[#faf9f6] flex flex-col">
        <div className="p-3 border-b border-[var(--line)]">
          <button
            onClick={() => {
              // 스트리밍 중이던 스트림을 먼저 닫아야 빈 msgs 배열에 좀비 쓰기가 발생하지 않음.
              // 전환 effect(activeConversationId)가 새 빈 대화의 메시지로 버퍼를 비운다.
              closeRef.current?.();
              closeRef.current = null;
              setStreaming(false);
              startNewConversation();
            }}
            className="w-full h-9 rounded-lg accent-bg text-white text-[12.5px] font-medium flex items-center justify-center gap-2 hover:opacity-90"
          >
            <Ich.Plus size={14}/> 새 대화
          </button>
        </div>
        <div className="flex-1 overflow-y-auto scroll-hide p-2 space-y-1">
          {CONVERSATIONS.length === 0 && (
            <div className="px-3 py-6 text-center text-[11.5px] text-zinc-400">
              아직 대화가 없습니다.
            </div>
          )}
          {CONVERSATIONS.map((c) => (
            <div
              key={c.id}
              className={`group relative w-full rounded-lg ${c.active ? 'bg-white border border-[var(--line)]' : 'hover:bg-white/60'}`}
            >
              <button
                onClick={() => selectConversation(c.id)}
                className="w-full text-left px-3 py-2 text-[12.5px]"
              >
                <div className="font-medium truncate pr-5">{c.title}</div>
                <div className="text-[10.5px] mono text-zinc-500 truncate">{c.sub}</div>
              </button>
              {/* 대화 삭제 — hover 시 노출 (icons.jsx 는 읽기전용이라 인라인 SVG) */}
              <button
                onClick={(e) => { e.stopPropagation(); deleteConversation(c.id); }}
                title="대화 삭제"
                className="absolute top-1.5 right-1.5 h-6 w-6 rounded-md hidden group-hover:flex items-center justify-center text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
                  fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13"/>
                </svg>
              </button>
            </div>
          ))}
        </div>
        <div className="p-3 border-t border-[var(--line)] text-[10.5px] mono text-zinc-500">
          모델 <span className="text-zinc-800">{modelLabel}</span>{CHAT_TOOLS_LABEL ? ` · ${CHAT_TOOLS_LABEL}` : ''}
        </div>
      </aside>

      {/* Conversation */}
      <div className="flex-1 flex flex-col bg-[var(--bg)]">
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
          <div className="max-w-[760px] mx-auto space-y-5">
            {msgs.length === 0 && (
              <div className="text-center text-[12.5px] text-zinc-400 mt-20">
                강의·과제·공지에 대해 무엇이든 물어보세요.
              </div>
            )}
            {msgs.map((m, i) => <Bubble key={i} m={m}/>)}
          </div>
        </div>

        <div className="border-t border-[var(--line)] px-6 py-4 bg-white/60 backdrop-blur">
          <div className="max-w-[760px] mx-auto">
            <div className="flex flex-wrap gap-1.5 mb-2.5">
              {SUGGESTIONS.map((s,i) => (
                <button key={i} onClick={() => send(s)}
                  className="text-[11.5px] px-2.5 h-7 rounded-full ssu-chip hover:bg-zinc-50 text-zinc-700">
                  {s}
                </button>
              ))}
            </div>
            <div className="ssu-card flex items-end gap-2 p-2.5">
              <textarea
                rows={1} value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
                placeholder="강의·과제·공지에 대해 무엇이든 물어보세요…"
                className="flex-1 resize-none bg-transparent outline-none text-[13.5px] leading-relaxed px-1 py-1 placeholder:text-zinc-400 max-h-[120px]"/>
              <div className="flex items-center gap-1.5 shrink-0">
                <span className="text-[10.5px] mono text-zinc-400">⌘ ↵ 전송</span>
                <button onClick={() => send()} disabled={!input.trim()}
                  className={`h-8 w-8 rounded-md flex items-center justify-center ${input.trim() ? 'accent-bg text-white' : 'bg-zinc-100 text-zinc-400'}`}>
                  <Ich.Send size={15}/>
                </button>
              </div>
            </div>
            <div className="text-[10.5px] mono text-zinc-500 mt-2 text-center">
              {CHAT_FOOTER_NOTE}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Bubble({ m }) {
  if (m.role === 'user') return (
    <div className="flex justify-end fade-in">
      {/* Shift+Enter 멀티라인 줄바꿈 보존 — whitespace-pre-wrap(+긴 단어 줄바꿈) */}
      <div className="max-w-[78%] rounded-2xl rounded-tr-sm px-4 py-2.5 bg-zinc-900 text-white text-[13.5px] leading-relaxed whitespace-pre-wrap break-words">
        {m.text}
        <div className="text-[10px] mono text-zinc-400 mt-1 text-right">{m.t}</div>
      </div>
    </div>
  );
  return (
    <div className="flex gap-3 fade-in">
      <div className="h-7 w-7 rounded-md accent-bg text-white flex items-center justify-center shrink-0">
        <Ich.Sparkles size={14}/>
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[11px] mono text-zinc-500 mb-1">학습 비서 · {m.t}</div>
        {/* 스크린리더 — 스트리밍 응답을 polite 로 읽어주고, 진행 중이면 aria-busy 로 알림 */}
        <div
          aria-live="polite"
          aria-busy={!!m.live}
          className={`ssu-card p-4 text-[13.5px] leading-relaxed text-zinc-800 ${m.error ? 'border-rose-200 bg-rose-50/40' : ''}`}
        >
          {(m.live && !m.text) ? <span className="typing">생각 중…</span> : <Markdown text={m.text} />}
          {/* MCP 도구 실행 중 표시 — prefix__name 원문 그대로 (예: notion__query_assignments) */}
          {m.live && m.tool && (
            <div className="mt-2 text-[11px] mono text-zinc-500">
              <span className="typing">도구 실행 중</span> · {m.tool}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ============== 경량 마크다운 렌더러 ==============
 * 외부 라이브러리 없이 LLM 답변의 흔한 마크다운만 처리:
 * 코드블록(```), 제목(#), 리스트(-, *, 1.), 인용(>),
 * 인라인(**굵게**, *기울임*, `코드`, [링크](url)).
 */
function renderInline(text) {
  // 토큰: `code` | **bold** | *italic* | [text](url)
  const parts = [];
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(\[[^\]]+\]\([^)]+\))/g;
  let last = 0, m, key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith('`')) {
      parts.push(<code key={key++} className="px-1 py-0.5 rounded bg-zinc-100 text-[12px] font-mono text-zinc-800">{tok.slice(1, -1)}</code>);
    } else if (tok.startsWith('**')) {
      parts.push(<strong key={key++} className="font-semibold">{tok.slice(2, -2)}</strong>);
    } else if (tok.startsWith('*')) {
      parts.push(<em key={key++}>{tok.slice(1, -1)}</em>);
    } else {
      const mm = tok.match(/\[([^\]]+)\]\(([^)]+)\)/);
      // javascript: 등 위험 스킴 차단 — http/https/mailto만 링크로 렌더 (그 외는 텍스트로)
      const url = mm[2].trim();
      const isSafe = /^(https?:|mailto:)/i.test(url);
      if (isSafe) {
        parts.push(<a key={key++} href={url} target="_blank" rel="noopener noreferrer" className="text-[var(--accent)] hover:underline">{mm[1]}</a>);
      } else {
        parts.push(mm[1]);
      }
    }
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function Markdown({ text }) {
  if (!text) return <span className="text-zinc-400">응답 준비 중…</span>;

  const lines = text.split('\n');
  const blocks = [];
  let i = 0, key = 0;

  while (i < lines.length) {
    const line = lines[i];

    // 코드블록 ```
    if (line.trim().startsWith('```')) {
      const buf = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) { buf.push(lines[i]); i++; }
      i++; // 닫는 ```
      blocks.push(
        <pre key={key++} className="my-2 p-3 rounded-lg bg-zinc-900 text-zinc-100 text-[12px] font-mono overflow-x-auto">
          <code>{buf.join('\n')}</code>
        </pre>
      );
      continue;
    }

    // 제목 #
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    if (h) {
      const lvl = h[1].length;
      const sz = lvl === 1 ? 'text-[16px]' : lvl === 2 ? 'text-[15px]' : 'text-[14px]';
      blocks.push(<div key={key++} className={`font-semibold ${sz} mt-3 mb-1`}>{renderInline(h[2])}</div>);
      i++;
      continue;
    }

    // 리스트 (-, *, 1.) — 연속 묶음
    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const items = [];
      const ordered = /^\s*\d+\.\s+/.test(line);
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, ''));
        i++;
      }
      const ListTag = ordered ? 'ol' : 'ul';
      blocks.push(
        <ListTag key={key++} className={`my-1.5 pl-5 space-y-0.5 ${ordered ? 'list-decimal' : 'list-disc'}`}>
          {items.map((it, j) => <li key={j}>{renderInline(it)}</li>)}
        </ListTag>
      );
      continue;
    }

    // 인용 >
    if (line.trim().startsWith('>')) {
      blocks.push(
        <blockquote key={key++} className="my-1.5 pl-3 border-l-2 border-[var(--line)] text-zinc-600">
          {renderInline(line.replace(/^\s*>\s?/, ''))}
        </blockquote>
      );
      i++;
      continue;
    }

    // 빈 줄
    if (line.trim() === '') { i++; continue; }

    // 일반 문단
    blocks.push(<p key={key++} className="my-1.5">{renderInline(line)}</p>);
    i++;
  }

  return <div>{blocks}</div>;
}

export { ChatView };
