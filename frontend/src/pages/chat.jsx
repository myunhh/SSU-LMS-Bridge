/* Chat / LLM Assistant view */
import { useState as chS, useEffect as chE, useRef as chR } from 'react';
import { useData } from '../data/DataStore';
import { openChatStream } from '../api/chat';
import { CHAT_MODEL_LABEL, CHAT_FOOTER_NOTE, CHAT_RAG_ENABLED } from '../data/uiConfig';
import Ich from './icons';

/* ============== Chat ============== */
function ChatView() {
  const {
    chatSeed, suggestions: SUGGESTIONS,
    conversations: CONVERSATIONS,
    appendChatMessage, startNewConversation, selectConversation,
  } = useData();

  // 실제 LLM 채팅은 빈 대화로 시작 (mock seed 카드는 사용하지 않음)
  const [msgs, setMsgs] = chS([]);
  const [input, setInput] = chS('');
  const [streaming, setStreaming] = chS(false);
  const scrollRef = chR(null);

  chE(() => { scrollRef.current?.scrollTo({ top: 99999, behavior: 'smooth' }); }, [msgs, streaming]);

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

    // user 메시지 + 스트리밍될 assistant placeholder 추가
    setMsgs(m => [...m, userMsg, { role: 'assistant', t, text: '', live: true }]);
    setInput('');
    setStreaming(true);

    let acc = '';
    const replaceLast = (patch) => setMsgs(m => {
      const copy = [...m];
      copy[copy.length - 1] = { role: 'assistant', t, ...patch };
      return copy;
    });

    openChatStream({
      messages: history,
      onText: (delta) => { acc += delta; replaceLast({ text: acc, live: true }); },
      onError: (msg) => { replaceLast({ text: acc || `⚠️ ${msg}`, error: true }); setStreaming(false); },
      onDone: () => { replaceLast({ text: acc || '(응답이 비어 있습니다)' }); setStreaming(false); },
    });
  };

  return (
    <div className="flex h-[calc(100vh-58px)]">
      {/* Conversation list */}
      <aside className="w-[260px] shrink-0 border-r border-[var(--line)] bg-[#faf9f6] flex flex-col">
        <div className="p-3 border-b border-[var(--line)]">
          <button
            onClick={() => { startNewConversation(); setMsgs([]); }}
            className="w-full h-9 rounded-lg accent-bg text-white text-[12.5px] font-medium flex items-center justify-center gap-2 hover:opacity-90"
          >
            <Ich.Plus size={14}/> 새 대화
          </button>
        </div>
        <div className="flex-1 overflow-y-auto scroll-hide p-2 space-y-1">
          {CONVERSATIONS.map((c) => (
            <button
              key={c.id}
              onClick={() => selectConversation(c.id)}
              className={`w-full text-left px-3 py-2 rounded-lg text-[12.5px] ${c.active ? 'bg-white border border-[var(--line)]' : 'hover:bg-white/60'}`}
            >
              <div className="font-medium truncate">{c.title}</div>
              <div className="text-[10.5px] mono text-zinc-500 truncate">{c.sub}</div>
            </button>
          ))}
        </div>
        <div className="p-3 border-t border-[var(--line)] text-[10.5px] mono text-zinc-500">
          모델 <span className="text-zinc-800">{CHAT_MODEL_LABEL}</span>{CHAT_RAG_ENABLED ? ' · RAG 켜짐' : ''}
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
              <button className="h-8 w-8 rounded-md hover:bg-zinc-100 flex items-center justify-center text-zinc-500"><Ich.Plus size={16}/></button>
              <textarea
                rows={1} value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
                placeholder="강의자료에 대해 무엇이든 물어보세요…"
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
      <div className="max-w-[78%] rounded-2xl rounded-tr-sm px-4 py-2.5 bg-zinc-900 text-white text-[13.5px] leading-relaxed">
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
        <div className={`ssu-card p-4 text-[13.5px] leading-relaxed text-zinc-800 ${m.error ? 'border-rose-200 bg-rose-50/40' : ''}`}>
          {(m.live && !m.text) ? <span className="typing">생각 중…</span> : <Markdown text={m.text} />}
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
      parts.push(<a key={key++} href={mm[2]} target="_blank" rel="noopener noreferrer" className="text-[var(--accent)] hover:underline">{mm[1]}</a>);
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
