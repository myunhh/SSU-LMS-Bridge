/* MCP 서버 뷰 — SSU LMS Bridge in-process MCP 4종(lms/study/notion/obsidian)의
 * 현재 상태 + 노출 도구 목록·도구별 설명을 모아 보여주는 전용 페이지.
 * 데이터: DataStore.mcpServers (GET /api/mcp/status), reloadConnectors 로 갱신. */
import { useState as mS } from 'react';
import { useNavigate } from 'react-router-dom';
import { useData } from '../data/DataStore';
import Icn from './icons';

// 로딩 전 표시용 시드 (백엔드 /api/mcp/status 응답으로 대체됨)
const MCP_FALLBACK = [
  { id: 'lms',      name: 'LMS MCP',      status: 'disconnected', tools: 0, toolList: [], meta: '강의·과제·마감·공지·자료·토론 실시간 조회' },
  { id: 'study',    name: 'Study MCP',    status: 'disconnected', tools: 0, toolList: [], meta: '퀴즈·플래시카드(SM-2 SRS) 저장/복습' },
  { id: 'notion',   name: 'Notion MCP',   status: 'disconnected', tools: 0, toolList: [], meta: 'Notion DB 동기화·질의' },
  { id: 'obsidian', name: 'Obsidian MCP', status: 'disconnected', tools: 0, toolList: [], meta: 'Vault 노트·파일 읽기/쓰기' },
];

// MCP 별 항상-마운트 여부 (안내 문구용) — lms·study 는 토큰 없이 항상 켜진다.
const ALWAYS_ON = new Set(['lms', 'study']);

const Logo = ({ id }) => {
  const cls = 'h-9 w-9 rounded-xl flex items-center justify-center shrink-0';
  if (id === 'lms')      return <div className={`${cls} accent-bg text-white`}><Icn.Book size={18}/></div>;
  if (id === 'study')    return <div className={`${cls} bg-emerald-600 text-white`}><Icn.Quiz size={18}/></div>;
  if (id === 'notion')   return <div className={`${cls} bg-zinc-900 text-white`}><Icn.Notion size={18}/></div>;
  if (id === 'obsidian') return <div className={`${cls} bg-violet-600 text-white`}><Icn.Obsidian size={18}/></div>;
  return <div className={`${cls} bg-zinc-200`}><Icn.Code size={18}/></div>;
};

function McpServerCard({ m, loaded, onRun }) {
  const ok = m.status === 'connected';
  const [open, setOpen] = mS(true);   // 도구 목록 기본 펼침 (페이지 목적이 '도구 보기')
  const tools = m.toolList || [];

  return (
    <div className="ssu-card overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full px-5 py-4 flex items-center gap-3.5 text-left hover:bg-[var(--line-2)]/30"
      >
        <Logo id={m.id}/>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[14px] font-semibold">{m.name}</span>
            <code className="text-[10.5px] mono text-zinc-400">{m.id}__*</code>
            {ALWAYS_ON.has(m.id) && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-[var(--accent-soft)] text-[var(--accent)]">상시</span>
            )}
          </div>
          <div className="text-[11.5px] text-zinc-500 mt-0.5 truncate">{m.meta}</div>
        </div>
        <span className={`text-[10.5px] mono px-1.5 py-0.5 rounded-md flex items-center gap-1 shrink-0
          ${!loaded ? 'bg-zinc-100 text-zinc-500' : ok ? 'bg-emerald-50 text-[var(--ok)]' : 'bg-zinc-100 text-zinc-500'}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${loaded && ok ? 'bg-[var(--ok)]' : 'bg-zinc-400'}`}/>
          {!loaded ? '확인 중' : ok ? `도구 ${m.tools}개` : '미연결'}
        </span>
        <Icn.Chev size={15} className={`text-zinc-400 ml-1 shrink-0 transition-transform ${open ? 'rotate-90' : ''}`}/>
      </button>

      {open && (
        <div className="border-t border-[var(--line)] divide-y divide-[var(--line-2)]">
          {tools.length === 0 ? (
            <div className="px-5 py-5 text-center text-[12px] text-zinc-500">
              {ok ? '노출된 도구가 없습니다.'
                : ALWAYS_ON.has(m.id) ? '서버 응답 없음 — 백엔드 상태를 확인하세요.'
                : '미마운트 — 키를 설정하고 백엔드를 재시작하면 도구가 노출됩니다.'}
            </div>
          ) : tools.map((t, i) => (
            <div key={t.name + i} className="px-5 py-3 flex gap-3 items-start">
              <Icn.Code size={13} className="text-zinc-400 mt-1 shrink-0"/>
              <div className="min-w-0 flex-1">
                <code className="text-[12.5px] mono font-medium text-zinc-800">{m.id}__{t.name}</code>
                <div className="text-[12px] text-zinc-600 mt-0.5 leading-relaxed">
                  {t.description || '설명 없음'}
                </div>
              </div>
              {/* 학습 비서로 이 도구를 실제 호출하고 결과를 응답받는다 */}
              <button
                onClick={() => onRun(m.id, t.name)}
                title="학습 비서로 이 도구를 호출"
                className="shrink-0 h-7 px-2.5 rounded-md border border-[var(--line)] bg-white text-[11.5px] flex items-center gap-1 hover:bg-[var(--accent-soft)] hover:border-[var(--accent)]/40"
              >
                <Icn.Sparkles size={12}/> 실행
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function McpView() {
  const { mcpServers, mcpLoaded, reloadConnectors, askAssistant } = useData();
  const navigate = useNavigate();
  const [busy, setBusy] = mS(false);
  const servers = (mcpServers && mcpServers.length) ? mcpServers : MCP_FALLBACK;
  const connected = servers.filter(s => s.status === 'connected').length;
  const totalTools = servers.reduce((n, s) => n + (s.tools || 0), 0);

  const refresh = async () => {
    setBusy(true);
    try { await reloadConnectors(); } finally { setBusy(false); }
  };

  // '실행' — 학습 비서에게 해당 MCP 도구를 호출하라고 예약하고 채팅으로 이동.
  // LLM 은 prefix__name 도구를 tools 목록에서 찾아 호출하고 결과를 응답한다.
  const runTool = (serverId, toolName) => {
    askAssistant(
      `\`${serverId}__${toolName}\` MCP 도구를 호출해서 결과를 보여줘. ` +
      `필요한 입력값이 있으면 합리적인 기본값으로 호출하고, 부족하면 나에게 물어봐줘.`
    );
    navigate('/chat');
  };

  return (
    <div className="px-7 py-6 max-w-[1100px]">
      <section className="ssu-card p-5 mb-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[14.5px] font-semibold">MCP 서버</div>
            <div className="text-[11.5px] text-zinc-500 mt-0.5">
              {mcpLoaded
                ? `${connected}/${servers.length}개 연결됨 · 도구 ${totalTools}개 · 학습 비서(LLM)가 이 도구들로 LMS·Notion·Obsidian 을 다룹니다`
                : '상태 확인 중…'}
            </div>
          </div>
          <button
            onClick={refresh} disabled={busy}
            className="h-8 px-3 rounded-md border border-[var(--line)] bg-white text-[12px] flex items-center gap-1.5 hover:bg-zinc-50 disabled:opacity-50"
          >
            <Icn.Sync size={13} className={busy ? 'animate-spin' : ''}/> 새로고침
          </button>
        </div>
        <div className="mt-3 pt-3 border-t border-[var(--line)] text-[11.5px] text-zinc-500 leading-relaxed">
          네 MCP 서버는 백엔드와 <strong className="font-medium">같은 프로세스</strong>에 SSE 로 마운트됩니다.
          <code className="mono text-zinc-700"> lms</code>·<code className="mono text-zinc-700">study</code> 는 토큰 없이 항상 켜지고,
          <code className="mono text-zinc-700"> notion</code>·<code className="mono text-zinc-700">obsidian</code> 은
          키를 설정하면 마운트됩니다(변경 후 백엔드 재시작 필요). 각 카드를 펼쳐 도구별 기능을 확인하세요.
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4">
        {servers.map(m => <McpServerCard key={m.id} m={m} loaded={mcpLoaded} onRun={runTool}/>)}
      </div>
    </div>
  );
}

export { McpView };
