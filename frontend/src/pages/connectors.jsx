/* Connectors view */
import { useState as cnS } from 'react';
import { CONNECTORS as CN } from './data';
import Icn from './icons';

/* ============== Connectors ============== */
function ConnectorsView() {
  const [selected, setSelected] = cnS('llm');
  const conn = CN.find(c => c.id === selected) || CN[0];

  const Logo = ({ id }) => {
    const cls = "h-9 w-9 rounded-xl flex items-center justify-center";
    if (id === 'lms')      return <div className={`${cls} accent-bg text-white`}><Icn.Book size={18}/></div>;
    if (id === 'notion')   return <div className={`${cls} bg-zinc-900 text-white`}><Icn.Notion size={18}/></div>;
    if (id === 'obsidian') return <div className={`${cls} bg-violet-600 text-white`}><Icn.Obsidian size={18}/></div>;
    if (id === 'llm')      return <div className={`${cls} bg-orange-500 text-white`}><Icn.Sparkles size={18}/></div>;
    if (id === 'gmail')    return <div className={`${cls} bg-rose-500 text-white`}><Icn.Mail size={18}/></div>;
    return <div className={cls}/>;
  };

  return (
    <div className="px-7 py-6 max-w-[1200px]">
      <div className="grid grid-cols-12 gap-5">
        <section className="col-span-12 lg:col-span-7 ssu-card overflow-hidden">
          <header className="px-5 pt-4 pb-3 flex items-center justify-between border-b border-[var(--line)]">
            <div>
              <div className="text-[14.5px] font-semibold">커넥터</div>
              <div className="text-[11.5px] text-zinc-500">5개 중 4개 연결됨 · 마지막 동기화 7분 전</div>
            </div>
            <button className="h-8 px-3 rounded-md border border-[var(--line)] bg-white text-[12px] flex items-center gap-1.5 hover:bg-zinc-50">
              <Icn.Plus size={13}/> 추가
            </button>
          </header>
          <div className="divide-y divide-[var(--line-2)]">
            {CN.map(c => {
              const active = selected === c.id;
              return (
                <button key={c.id} onClick={() => setSelected(c.id)}
                  className={`w-full px-5 py-3.5 flex items-center gap-3.5 text-left ${active ? 'bg-[var(--accent-soft)]/50' : 'hover:bg-[var(--line-2)]/40'}`}>
                  <Logo id={c.id}/>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[13.5px] font-medium">{c.name}</span>
                      <span className={`text-[10.5px] mono px-1.5 py-0.5 rounded-md flex items-center gap-1
                        ${c.status === 'connected'
                          ? 'bg-emerald-50 text-[var(--ok)]'
                          : 'bg-zinc-100 text-zinc-500'}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${c.status==='connected' ? 'bg-[var(--ok)]' : 'bg-zinc-400'}`}/>
                        {c.status === 'connected' ? '연결됨' : '미연결'}
                      </span>
                    </div>
                    <div className="text-[11.5px] text-zinc-500 mt-0.5 mono truncate">{c.kind} · {c.host}</div>
                  </div>
                  <div className="text-right hidden sm:block">
                    <div className="text-[11.5px] text-zinc-700">{c.meta}</div>
                    <div className="text-[10.5px] mono text-zinc-400 mt-0.5">{c.last}</div>
                  </div>
                  <Icn.Chev size={15} className="text-zinc-400 ml-1 shrink-0"/>
                </button>
              );
            })}
          </div>
        </section>

        {/* Detail panel */}
        <section className="col-span-12 lg:col-span-5 space-y-5">
          <div className="ssu-card p-5">
            <div className="flex items-center gap-3">
              <Logo id={conn.id}/>
              <div className="flex-1">
                <div className="text-[15px] font-semibold tracking-tight">{conn.name}</div>
                <div className="text-[11.5px] text-zinc-500 mono">{conn.kind}</div>
              </div>
              <button className="text-[11.5px] mono text-zinc-500 hover:text-zinc-900 flex items-center gap-1">
                <Icn.External size={12}/> docs
              </button>
            </div>

            {conn.id === 'llm' && (
              <div className="mt-5 space-y-3">
                <Field label="Provider">
                  <select defaultValue="anthropic" className="ssu-input">
                    <option value="anthropic">Anthropic — Claude Haiku 4.5</option>
                    <option>OpenAI — GPT-4o-mini</option>
                    <option>Google — Gemini 2.0 Flash</option>
                  </select>
                </Field>
                <Field label="API Key" mono>
                  <input type="password" defaultValue="sk-ant-•••••••••••••••••rL2k" className="ssu-input mono"/>
                </Field>
                <Field label="모델 별칭" mono>
                  <input defaultValue="claude-haiku-4-5" className="ssu-input mono"/>
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Temperature" mono><input defaultValue="0.4" className="ssu-input mono"/></Field>
                  <Field label="Max tokens" mono><input defaultValue="2048" className="ssu-input mono"/></Field>
                </div>
                <div className="rounded-lg bg-zinc-50 border border-[var(--line)] p-3 text-[11.5px]">
                  <div className="flex items-center justify-between mono text-zinc-500">
                    <span>24h 사용량</span><span className="text-zinc-900">14,219 / 200,000 tok</span>
                  </div>
                  <div className="h-1.5 bg-zinc-200 rounded-full mt-2 overflow-hidden">
                    <div className="h-full accent-bg rounded-full" style={{ width: '7.1%' }}/>
                  </div>
                </div>
              </div>
            )}

            {conn.id === 'lms' && (
              <div className="mt-5 space-y-3">
                <Field label="학번"><input defaultValue="20231234" className="ssu-input mono"/></Field>
                <Field label="비밀번호"><input type="password" defaultValue="••••••••••" className="ssu-input mono"/></Field>
                <Field label="LMS Base URL" mono><input defaultValue="https://lms.ssu.ac.kr" className="ssu-input mono"/></Field>
                <Field label="로그인 방식"><input defaultValue="xn-sso-dir-sso" className="ssu-input mono"/></Field>
                <div className="rounded-lg bg-emerald-50 border border-emerald-200/60 p-3 flex items-start gap-2 text-[12px]">
                  <Icn.Check size={14} className="text-[var(--ok)] mt-0.5"/>
                  <div>
                    <div className="text-[var(--ok)] font-medium">세션 캐시 활성</div>
                    <div className="text-zinc-600 mt-0.5">storage_state.json · 재사용 시 0.5초 (12배 가속)</div>
                  </div>
                </div>
              </div>
            )}

            {conn.id === 'notion' && (
              <div className="mt-5 space-y-3">
                <Field label="Internal Token"><input type="password" defaultValue="secret_•••••••••••••" className="ssu-input mono"/></Field>
                <Field label="루트 페이지 ID" mono><input defaultValue="33b65931485c800b8075fa58f68f8992" className="ssu-input mono"/></Field>
                <Field label="동기화 항목">
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {['공지', '과제', '메타데이터', '강의 목록'].map(t => (
                      <span key={t} className="text-[11.5px] px-2 py-1 rounded-md bg-[var(--accent-soft)] text-[var(--accent)]">{t}</span>
                    ))}
                  </div>
                </Field>
              </div>
            )}

            {conn.id === 'obsidian' && (
              <div className="mt-5 space-y-3">
                <Field label="Auth Code"><input type="password" defaultValue="obs_•••••••••••" className="ssu-input mono"/></Field>
                <Field label="Vault 경로"><input defaultValue="LMS_Bridge_Vault" className="ssu-input mono"/></Field>
                <Field label="MCP Endpoint" mono><input defaultValue="http://localhost:27124/mcp" className="ssu-input mono"/></Field>
                <div className="text-[11.5px] mono text-zinc-500">파일 153개 · _manifest.json SHA-256 해시 추적 중</div>
              </div>
            )}

            {conn.id === 'gmail' && (
              <div className="mt-5">
                <div className="rounded-lg border border-dashed border-[var(--line)] p-5 text-center">
                  <Icn.Mail size={22} className="mx-auto text-zinc-400"/>
                  <div className="text-[13px] mt-2 font-medium">Gmail에 연결</div>
                  <div className="text-[11.5px] text-zinc-500 mt-1">마감 24시간 전 메일 알림을 받습니다.</div>
                  <button className="mt-3 h-9 px-4 rounded-lg accent-bg text-white text-[12.5px]">OAuth로 연결</button>
                </div>
              </div>
            )}

            <div className="mt-5 pt-4 border-t border-[var(--line)] flex items-center justify-between">
              <div className="text-[11.5px] mono text-zinc-500">마지막 점검 · {conn.last}</div>
              <div className="flex items-center gap-1.5">
                <button className="h-8 px-3 rounded-md border border-[var(--line)] bg-white text-[12px] flex items-center gap-1.5 hover:bg-zinc-50">
                  <Icn.Sync size={13}/> 연결 테스트
                </button>
                <button className="h-8 px-3 rounded-md accent-bg text-white text-[12px]">저장</button>
              </div>
            </div>
          </div>

          <div className="ssu-card p-5">
            <div className="text-[13px] font-semibold mb-3">동기화 스케줄러</div>
            <div className="space-y-2.5">
              <Toggle label="자동 동기화" sub="매일 새벽 4시 (LMS 갱신 후) · APScheduler" on/>
              <Toggle label="파일 다운로드" sub="강의 교안을 Vault에 자동 저장" on/>
              <Toggle label="마감 24시간 전 알림" sub="브라우저 푸시 + 데스크탑 알림"/>
              <Toggle label="새 공지 즉시 푸시" sub="LMS 폴링 주기 5분"/>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

const Field = ({ label, children, mono }) => (
  <label className="block">
    <div className={`text-[10.5px] uppercase tracking-[0.08em] text-zinc-500 font-medium mb-1.5 ${mono?'mono':''}`}>{label}</div>
    {children}
  </label>
);

const Toggle = ({ label, sub, on }) => {
  const [v, setV] = cnS(!!on);
  return (
    <button onClick={() => setV(!v)} className="w-full flex items-center gap-3 py-1.5 text-left">
      <div className="flex-1">
        <div className="text-[12.5px] font-medium">{label}</div>
        <div className="text-[11px] text-zinc-500 mt-0.5">{sub}</div>
      </div>
      <span className={`relative inline-block h-5 w-9 rounded-full transition ${v ? 'accent-bg' : 'bg-zinc-300'}`}>
        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition ${v ? 'left-[18px]' : 'left-0.5'}`}/>
      </span>
    </button>
  );
};

export { ConnectorsView };
