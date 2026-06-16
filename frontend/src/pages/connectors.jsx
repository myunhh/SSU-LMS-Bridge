/* Connectors view */
import { useState as cnS } from 'react';
import { useData } from '../data/DataStore';
import { formatSessionExpiry, formatSessionAge } from '../api/lmsAuth';
import Icn from './icons';

// 커넥터별 공식 문서 URL (gmail 은 미지원이라 제외)
const DOCS = {
  lms: 'https://lms.ssu.ac.kr',
  notion: 'https://developers.notion.com/',
  obsidian: 'https://github.com/coddingtonbear/obsidian-local-rest-api',
  llm: 'https://docs.litellm.ai/',
};

/* ============== Connectors ============== */
function ConnectorsView() {
  const {
    connectors: CN, connectorsLoaded, reloadConnectors, saveConnectorConfig,
    user, lmsSession, lmsBusy, loginLms, refreshLms,
    courses, lastSyncAt, syncHour,
  } = useData();
  const [selected, setSelected] = cnS('llm');
  const [lmsForm, setLmsForm] = cnS({ studentId: user?.studentId || '', password: '' });
  const [cnBusy, setCnBusy] = cnS(false);
  const conn = CN.find(c => c.id === selected) || CN[0];
  const lmsActive = !!lmsSession?.active;
  // LMS 카운트는 lmsSession 실제 상태로 보정 (mockData 의 connected 값 무시)
  const connectedCount = CN.filter(c =>
    c.id === 'lms' ? lmsActive : c.status === 'connected'
  ).length;

  // 커넥터 meta 를 가능한 실데이터로 보정 (LMS=실제 강의 수/학번)
  const metaFor = (c) => {
    if (c.id === 'lms') {
      return lmsActive
        ? `학번 ${user?.studentId || '—'} · ${courses.length}개 강의`
        : '연결되지 않음 — 로그인 필요';
    }
    return c.meta;
  };

  const Logo = ({ id }) => {
    const cls = "h-9 w-9 rounded-xl flex items-center justify-center";
    if (id === 'lms')      return <div className={`${cls} accent-bg text-white`}><Icn.Book size={18}/></div>;
    if (id === 'notion')   return <div className={`${cls} bg-zinc-900 text-white`}><Icn.Notion size={18}/></div>;
    if (id === 'obsidian') return <div className={`${cls} bg-violet-600 text-white`}><Icn.Obsidian size={18}/></div>;
    if (id === 'llm')      return <div className={`${cls} bg-orange-500 text-white`}><Icn.Sparkles size={18}/></div>;
    if (id === 'gmail')    return <div className={`${cls} bg-rose-500 text-white`}><Icn.Mail size={18}/></div>;
    return <div className={cls}/>;
  };

  const refresh = async () => {
    setCnBusy(true);
    try { await reloadConnectors(); } finally { setCnBusy(false); }
  };

  return (
    <div className="px-7 py-6 max-w-[1200px]">
      <div className="grid grid-cols-12 gap-5">
        <section className="col-span-12 lg:col-span-7 ssu-card overflow-hidden">
          <header className="px-5 pt-4 pb-3 flex items-center justify-between border-b border-[var(--line)]">
            <div>
              <div className="text-[14.5px] font-semibold">커넥터</div>
              <div className="text-[11.5px] text-zinc-500">
                {connectorsLoaded ? `${CN.length}개 중 ${connectedCount}개 연결됨` : '상태 확인 중…'}
              </div>
            </div>
            <button
              onClick={refresh} disabled={cnBusy}
              className="h-8 px-3 rounded-md border border-[var(--line)] bg-white text-[12px] flex items-center gap-1.5 hover:bg-zinc-50 disabled:opacity-50"
            >
              <Icn.Sync size={13} className={cnBusy ? 'animate-spin' : ''}/> 새로고침
            </button>
          </header>
          <div className="divide-y divide-[var(--line-2)]">
            {CN.map(c => {
              const active = selected === c.id;
              // LMS 는 실제 lmsSession 상태로 덮어씀. 그 외는 응답 전이면 '확인 중'.
              const pending = !connectorsLoaded && c.id !== 'lms';
              const status = c.id === 'lms' ? (lmsActive ? 'connected' : 'disconnected') : c.status;
              const last   = c.id === 'lms' && lmsActive ? formatSessionAge(lmsSession.savedAt) : c.last;
              const label  = pending ? '확인 중' : status === 'connected' ? '연결됨' : '미연결';
              return (
                <button key={c.id} onClick={() => setSelected(c.id)}
                  className={`w-full px-5 py-3.5 flex items-center gap-3.5 text-left ${active ? 'bg-[var(--accent-soft)]/50' : 'hover:bg-[var(--line-2)]/40'}`}>
                  <Logo id={c.id}/>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[13.5px] font-medium">{c.name}</span>
                      <span className={`text-[10.5px] mono px-1.5 py-0.5 rounded-md flex items-center gap-1
                        ${!pending && status === 'connected'
                          ? 'bg-emerald-50 text-[var(--ok)]'
                          : 'bg-zinc-100 text-zinc-500'}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${!pending && status==='connected' ? 'bg-[var(--ok)]' : 'bg-zinc-400'}`}/>
                        {label}
                      </span>
                    </div>
                    <div className="text-[11.5px] text-zinc-500 mt-0.5 mono truncate">{c.kind} · {c.host}</div>
                  </div>
                  <div className="text-right hidden sm:block">
                    <div className="text-[11.5px] text-zinc-700">{metaFor(c)}</div>
                    <div className="text-[10.5px] mono text-zinc-400 mt-0.5">{last}</div>
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
              {DOCS[conn.id] && (
                <a href={DOCS[conn.id]} target="_blank" rel="noreferrer"
                  className="text-[11.5px] mono text-zinc-500 hover:text-zinc-900 flex items-center gap-1">
                  <Icn.External size={12}/> docs
                </a>
              )}
            </div>

            {/* 비-LMS 커넥터: 키 입력 폼 + 저장 (백엔드 .env 에 upsert) */}
            {conn.id === 'llm' && (
              <div className="mt-5 space-y-3">
                <ReadOnlyMeta meta={conn.meta}/>
                <ConnectorConfigForm
                  saveConnectorConfig={saveConnectorConfig}
                  fields={[
                    { key: 'llm_api_key',  label: 'LLM_API_KEY',  secret: true,  placeholder: '저장됨 — 변경 시 입력' },
                    { key: 'llm_model',    label: 'LLM_MODEL',    placeholder: 'gemini-2.5-flash' },
                    { key: 'llm_provider', label: 'LLM_PROVIDER', placeholder: 'gemini' },
                  ]}
                />
                <EnvNote>
                  <code>LLM_API_KEY</code> / <code>LLM_MODEL</code> / <code>LLM_PROVIDER</code> 는
                  저장 즉시 반영됩니다 (백엔드 재시작 불필요).
                </EnvNote>
              </div>
            )}

            {conn.id === 'lms' && (
              <div className="mt-5 space-y-3">
                <Field label="학번">
                  <input
                    value={lmsForm.studentId}
                    onChange={e => setLmsForm(f => ({ ...f, studentId: e.target.value }))}
                    placeholder={user?.studentId || '학번'}
                    className="ssu-input mono"
                  />
                </Field>
                <Field label="비밀번호" mono>
                  <input
                    type="password"
                    value={lmsForm.password}
                    onChange={e => setLmsForm(f => ({ ...f, password: e.target.value }))}
                    placeholder={lmsActive ? '저장됨 — 변경 시 재로그인' : '스마트캠퍼스 비밀번호'}
                    className="ssu-input mono"
                  />
                </Field>
                <Field label="LMS Base URL" mono><input defaultValue="https://lms.ssu.ac.kr" className="ssu-input mono" readOnly/></Field>
                <Field label="로그인 방식"><input defaultValue="xn-sso-dir-sso" className="ssu-input mono" readOnly/></Field>

                {/* 세션 상태 박스 — 실제 lmsSession 반영 */}
                {lmsActive ? (
                  <div className="rounded-lg bg-emerald-50 border border-emerald-200/60 p-3 flex items-start gap-2 text-[12px]">
                    <Icn.Check size={14} className="text-[var(--ok)] mt-0.5"/>
                    <div className="flex-1">
                      <div className="text-[var(--ok)] font-medium">세션 캐시 활성</div>
                      <div className="text-zinc-600 mt-0.5">
                        Playwright storage_state · {formatSessionExpiry(lmsSession.savedAt)} · 마지막 갱신 {formatSessionAge(lmsSession.savedAt)}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg bg-zinc-50 border border-[var(--line)] p-3 flex items-start gap-2 text-[12px]">
                    <Icn.Clock size={14} className="text-zinc-500 mt-0.5"/>
                    <div className="flex-1">
                      <div className="text-zinc-700 font-medium">세션 없음</div>
                      <div className="text-zinc-500 mt-0.5">
                        아래 "연결 테스트" 를 눌러 LMS 로그인 후 storage_state 를 발급받으세요.
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {conn.id === 'notion' && (
              <div className="mt-5 space-y-3">
                <ReadOnlyMeta meta={conn.meta}/>
                <Field label="동기화 항목">
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {['공지', '과제'].map(t => (
                      <span key={t} className="text-[11.5px] px-2 py-1 rounded-md bg-[var(--accent-soft)] text-[var(--accent)]">{t}</span>
                    ))}
                  </div>
                </Field>
                <ConnectorConfigForm
                  saveConnectorConfig={saveConnectorConfig}
                  fields={[
                    { key: 'notion_token',        label: 'NOTION_TOKEN',        secret: true, placeholder: 'secret_…' },
                    { key: 'notion_root_page_id', label: 'NOTION_ROOT_PAGE_ID', placeholder: '32자리 페이지 ID' },
                  ]}
                />
                <EnvNote>
                  <code>NOTION_TOKEN</code> / <code>NOTION_ROOT_PAGE_ID</code> 저장 후 Notion 동기화는
                  <strong className="font-medium"> 백엔드 재시작 후</strong> 반영됩니다.
                </EnvNote>
              </div>
            )}

            {conn.id === 'obsidian' && (
              <div className="mt-5 space-y-3">
                <ReadOnlyMeta meta={conn.meta}/>
                <ConnectorConfigForm
                  saveConnectorConfig={saveConnectorConfig}
                  fields={[
                    { key: 'obsidian_mcp_auth_code', label: 'OBSIDIAN_MCP_AUTH_CODE', secret: true, placeholder: 'Local REST API API Key' },
                    { key: 'obsidian_base_url',      label: 'OBSIDIAN_BASE_URL',      placeholder: 'http://localhost:27123' },
                    // vault 내부 상대 경로 — 빈 문자열("")도 정상값(vault 루트). 사용자가 명시 입력한 경우에만 전송.
                    { key: 'obsidian_vault_path',    label: 'OBSIDIAN_VAULT_PATH',    placeholder: '비워두면 vault 루트 (예: LMS)', allowEmpty: true },
                  ]}
                />
                <EnvNote>
                  <code>OBSIDIAN_VAULT_PATH</code> 는 vault 내부 상대 경로라
                  <strong className="font-medium"> 빈 값(vault 루트)도 정상</strong>입니다 (절대 경로 아님).
                  저장 후 Obsidian 연동은 <strong className="font-medium">백엔드 재시작 후</strong> 반영됩니다 (Local REST API 플러그인 필요).
                </EnvNote>
              </div>
            )}

            {conn.id === 'gmail' && (
              <div className="mt-5">
                <div className="rounded-lg border border-dashed border-[var(--line)] p-5 text-center">
                  <Icn.Mail size={22} className="mx-auto text-zinc-400"/>
                  <div className="text-[13px] mt-2 font-medium">Gmail 연동</div>
                  <div className="text-[11.5px] text-zinc-500 mt-1">Gmail 연동은 아직 백엔드가 지원하지 않습니다.</div>
                  <button disabled
                    className="mt-3 h-9 px-4 rounded-lg bg-zinc-100 text-zinc-400 text-[12.5px] cursor-not-allowed">
                    준비 중 (로드맵)
                  </button>
                </div>
              </div>
            )}

            <div className="mt-5 pt-4 border-t border-[var(--line)] flex items-center justify-between">
              <div className="text-[11.5px] mono text-zinc-500">
                {conn.id === 'lms' && lmsActive
                  ? `마지막 갱신 · ${formatSessionAge(lmsSession.savedAt)}`
                  : `마지막 점검 · ${conn.last}`}
              </div>
              <div className="flex items-center gap-1.5">
                {/* LMS 만 로그인/갱신 동작. 그 외 커넥터는 상태 새로고침만 (설정은 .env). */}
                {conn.id === 'lms' ? (
                  <>
                    <button
                      onClick={() => lmsActive ? refreshLms() : loginLms(lmsForm.studentId, lmsForm.password)}
                      disabled={lmsBusy || (!lmsActive && (!lmsForm.studentId || !lmsForm.password))}
                      className="h-8 px-3 rounded-md border border-[var(--line)] bg-white text-[12px] flex items-center gap-1.5 hover:bg-zinc-50 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Icn.Sync size={13} className={lmsBusy ? 'animate-spin' : ''}/>
                      {lmsBusy ? '확인 중…' : lmsActive ? '세션 갱신' : '연결 테스트'}
                    </button>
                    <button
                      onClick={() => loginLms(lmsForm.studentId, lmsForm.password)}
                      disabled={lmsBusy || !lmsForm.studentId || !lmsForm.password}
                      className="h-8 px-3 rounded-md accent-bg text-white text-[12px] disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {lmsActive ? '재로그인' : '로그인'}
                    </button>
                  </>
                ) : (
                  <button
                    onClick={refresh} disabled={cnBusy}
                    className="h-8 px-3 rounded-md border border-[var(--line)] bg-white text-[12px] flex items-center gap-1.5 hover:bg-zinc-50 disabled:opacity-50"
                  >
                    <Icn.Sync size={13} className={cnBusy ? 'animate-spin' : ''}/> 상태 새로고침
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* 예약 동기화 — 읽기 전용 (백엔드 .env 의 SYNC_HOUR / APScheduler 관리) */}
          <div className="ssu-card p-5">
            <div className="text-[13px] font-semibold mb-3">예약 동기화</div>
            <div className="space-y-2.5">
              <ScheduleRow
                label="자동 동기화"
                sub={`매일 ${String(syncHour ?? 4).padStart(2, '0')}:00 자동 실행 · APScheduler`}
                badge="활성" tone="ok"
              />
              <ScheduleRow
                label="마지막 동기화"
                sub={lastSyncAt ? lastSyncAt.toLocaleString('ko-KR') : '아직 실행되지 않음'}
              />
              <ScheduleRow label="강의자료 파일 다운로드" sub="PPT/PDF 원본을 Obsidian 에 저장 (DOWNLOAD_FILES)" badge="활성" tone="ok"/>
              <ScheduleRow label="마감 24시간 전 알림" sub="알림 발송 백엔드 미구현" badge="준비 중" dim/>
              <ScheduleRow label="새 공지 즉시 푸시" sub="알림 발송 백엔드 미구현" badge="준비 중" dim/>
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

// 커넥터 키 입력 폼 — Notion/Obsidian/LLM 공용.
// fields: [{ key, label, secret?, placeholder?, allowEmpty? }]
//   - secret    : password 입력 + 저장 성공 시 값 비움(시크릿은 응답에 에코 안 됨)
//   - allowEmpty : 빈 문자열도 정상값(obsidian_vault_path). 사용자가 명시 입력(touched)한 경우에만 전송.
// payload 규약: 빈 입력 필드는 제외. allowEmpty 필드는 touched && 입력값이 있을 때만 포함
//   (빈 문자열 전송은 의도적 '루트로 변경' 이라 touched 라도 빈값은 보내지 않음 — 안전 측 선택).
function ConnectorConfigForm({ fields, saveConnectorConfig }) {
  const [vals, setVals] = cnS(() => Object.fromEntries(fields.map(f => [f.key, ''])));
  const [busy, setBusy] = cnS(false);

  const setField = (key, v) => setVals(s => ({ ...s, [key]: v }));

  // 보낼 게 하나라도 있는지 (모든 필드가 빈값이면 저장 버튼 비활성)
  const hasInput = fields.some(f => (vals[f.key] || '').trim() !== '');

  const onSave = async () => {
    const payload = {};
    for (const f of fields) {
      const v = (vals[f.key] || '').trim();
      if (v) payload[f.key] = v;   // allowEmpty 필드도 입력이 있을 때만 전송
    }
    if (Object.keys(payload).length === 0) return;
    setBusy(true);
    try {
      const res = await saveConnectorConfig(payload);
      // 저장 성공 시 시크릿 입력 필드는 비운다 (값이 응답에 에코되지 않으므로).
      if (res?.ok) {
        setVals(s => {
          const next = { ...s };
          for (const f of fields) if (f.secret) next[f.key] = '';
          return next;
        });
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      {fields.map(f => (
        <Field key={f.key} label={f.label} mono>
          <input
            type={f.secret ? 'password' : 'text'}
            value={vals[f.key]}
            onChange={e => setField(f.key, e.target.value)}
            placeholder={f.placeholder || ''}
            autoComplete="off"
            className="ssu-input mono"
          />
        </Field>
      ))}
      <button
        onClick={onSave}
        disabled={busy || !hasInput}
        className="h-9 px-4 rounded-lg accent-bg text-white text-[12.5px] flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Icn.Check size={13} className={busy ? 'animate-spin' : ''}/>
        {busy ? '저장 중…' : '저장'}
      </button>
    </div>
  );
}

// 백엔드 status meta 를 읽기 전용으로 표시
const ReadOnlyMeta = ({ meta }) => (
  <div className="rounded-lg bg-zinc-50 border border-[var(--line)] p-3 text-[12px] text-zinc-700">
    {meta || '상태 미확인'}
  </div>
);

const EnvNote = ({ children }) => (
  <div className="rounded-lg bg-zinc-50 border border-[var(--line)] p-3 text-[11.5px] text-zinc-500 leading-relaxed [&_code]:mono [&_code]:text-zinc-700">
    {children}
  </div>
);

// 예약 동기화 카드의 읽기 전용 행
const ScheduleRow = ({ label, sub, badge, tone, dim }) => (
  <div className={`flex items-center gap-3 py-1.5 ${dim ? 'opacity-60' : ''}`}>
    <div className="flex-1">
      <div className="text-[12.5px] font-medium">{label}</div>
      <div className="text-[11px] text-zinc-500 mt-0.5">{sub}</div>
    </div>
    {badge && (
      <span className={`text-[10.5px] mono px-1.5 py-0.5 rounded-md
        ${tone === 'ok' ? 'bg-emerald-50 text-[var(--ok)]' : 'bg-zinc-100 text-zinc-500'}`}>
        {badge}
      </span>
    )}
  </div>
);

export { ConnectorsView };
