/* Chat / LLM Assistant view */
import { useState as chS, useEffect as chE, useRef as chR } from 'react';
import { COURSES as chCS, ASSIGNMENTS as chAS, CHAT_SEED, SUGGESTIONS, CONVERSATIONS, NOW } from '../data/mockData';
import { CHAT_MODEL_LABEL, CHAT_FOOTER_NOTE, CHAT_RAG_ENABLED } from '../data/uiConfig';
import Ich from './icons';

const dU = (iso) => {
  const ms = new Date(iso) - NOW;
  if (ms < 0) return { label: '지남', tone: 'text-zinc-400' };
  const days = Math.floor(ms / 86400000);
  if (days === 0) return { label: '오늘', tone: 'text-[var(--danger)]' };
  if (days <= 3)  return { label: `D-${days}`, tone: 'text-[var(--warn)]' };
  return { label: `D-${days}`, tone: 'text-zinc-500' };
};

/* ============== Chat ============== */
function ChatView() {
  const [msgs, setMsgs] = chS(CHAT_SEED);
  const [input, setInput] = chS('');
  const [streaming, setStreaming] = chS(false);
  const scrollRef = chR(null);

  chE(() => { scrollRef.current?.scrollTo({ top: 99999, behavior: 'smooth' }); }, [msgs, streaming]);

  const send = (text) => {
    const v = text ?? input;
    if (!v.trim()) return;
    const now = new Date();
    const t = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
    setMsgs(m => [...m, { role: 'user', text: v, t }]);
    setInput('');
    setStreaming(true);
    setTimeout(() => {
      setMsgs(m => [...m, { role: 'assistant', t, text:
        '강의자료를 살펴봤어요. 아래에 정리해 드릴게요. 더 깊이 알아보고 싶은 부분이 있으면 알려주세요.',
        rich: 'generic' }]);
      setStreaming(false);
    }, 1100);
  };

  return (
    <div className="flex h-[calc(100vh-58px)]">
      {/* Conversation list */}
      <aside className="w-[260px] shrink-0 border-r border-[var(--line)] bg-[#faf9f6] flex flex-col">
        <div className="p-3 border-b border-[var(--line)]">
          <button className="w-full h-9 rounded-lg accent-bg text-white text-[12.5px] font-medium flex items-center justify-center gap-2 hover:opacity-90">
            <Ich.Plus size={14}/> 새 대화
          </button>
        </div>
        <div className="flex-1 overflow-y-auto scroll-hide p-2 space-y-1">
          {CONVERSATIONS.map((c) => (
            <button key={c.id} className={`w-full text-left px-3 py-2 rounded-lg text-[12.5px] ${c.active ? 'bg-white border border-[var(--line)]' : 'hover:bg-white/60'}`}>
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
            {msgs.map((m, i) => <Bubble key={i} m={m}/>)}
            {streaming && <Bubble m={{ role: 'assistant', text: '', streaming: true, t: '' }}/>}
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
        <div className="ssu-card p-4 text-[13.5px] leading-relaxed text-zinc-800">
          {m.streaming ? <span className="typing">자료 검색 중</span> : <RichAnswer kind={m.rich} text={m.text}/>}
        </div>
      </div>
    </div>
  );
}

function RichAnswer({ kind, text }) {
  if (kind === 'deadlines') {
    const list = chAS.filter(a=>!a.submitted).slice(0,4);
    return (
      <div>
        <p>이번 주 마감 4건을 추렸어요. 비중과 권장 착수 시점을 함께 정리했습니다.</p>
        <div className="mt-3 grid gap-2">
          {list.map(a => {
            const c = chCS.find(x=>x.id===a.course);
            const d = dU(a.due);
            return (
              <div key={a.id} className="rounded-lg border border-[var(--line)] p-3 flex items-center gap-3">
                <span className="h-2 w-2 rounded-sm" style={{ background: c.color }}/>
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate text-[13px]">{a.title}</div>
                  <div className="text-[11px] mono text-zinc-500">{c.code} · 비중 {a.weight}% · 권장 착수 D-3</div>
                </div>
                <span className={`text-[11.5px] mono ${d.tone}`}>{d.label}</span>
              </div>
            );
          })}
        </div>
        <p className="mt-3 text-[12.5px] text-zinc-600">
          가장 비중이 높은 건 <span className="font-medium">Transformer 구현 (20%)</span> 입니다. 화/수에 모델 학습 루프부터 시작하시는 걸 권장해요.
        </p>
      </div>
    );
  }
  if (kind === 'ridge') {
    return (
      <div>
        <p>두 정규화 모두 손실 함수에 가중치 페널티를 더해 과적합을 줄여요.</p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          {[
            { t: 'Ridge (L2)', s: '∑ wᵢ²', d: '계수를 0에 가깝게 줄임 · 모든 변수 유지', use: '다중공선성 강함' },
            { t: 'Lasso (L1)', s: '∑ |wᵢ|', d: '일부 계수를 정확히 0 · 자동 변수 선택', use: '희소 모델 필요' },
          ].map((x,i) => (
            <div key={i} className="rounded-lg border border-[var(--line)] p-3">
              <div className="text-[11px] mono text-zinc-500">{x.t}</div>
              <div className="font-mono text-[15px] my-1">{x.s}</div>
              <div className="text-[12px] text-zinc-700">{x.d}</div>
              <div className="text-[11px] mono text-[var(--accent)] mt-1.5">쓸 때: {x.use}</div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[12.5px] text-zinc-600">10주차 슬라이드 18–24, 11주차 슬라이드 6–11에 식 유도가 있어요.</p>
        <div className="flex flex-wrap gap-1.5 mt-3">
          {['10주차 슬라이드 열기','연습 문제 만들어줘','파이썬 예제 보기'].map((s,i)=>(
            <span key={i} className="text-[11px] px-2 py-1 rounded-md bg-[var(--accent-soft)] text-[var(--accent)]">{s}</span>
          ))}
        </div>
      </div>
    );
  }
  return <div>{text || '응답 준비 중…'}</div>;
}

export { ChatView };
