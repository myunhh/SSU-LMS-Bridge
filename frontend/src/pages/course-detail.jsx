/* Course Detail view */
import { useState as uS, useEffect as uE, useRef as uR, useMemo as uM } from 'react';
import { useData } from '../data/DataStore';
import * as Api from '../api/index';
import I2 from './icons';

const fmt2 = (iso) => {
  const d = new Date(iso);
  return `${d.getMonth()+1}/${d.getDate()} (${'일월화수목금토'[d.getDay()]}) ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
};
const dUFor = (iso, NOW) => {
  const ms = new Date(iso) - NOW;
  if (ms < 0) return { label: '지남', tone: 'text-zinc-400' };
  const days = Math.floor(ms/86400000);
  if (days === 0) return { label: '오늘', tone: 'text-[var(--danger)]' };
  if (days <= 3)  return { label: `D-${days}`, tone: 'text-[var(--warn)]' };
  return { label: `D-${days}`, tone: 'text-zinc-500' };
};

// Canvas module item_type → 한글 라벨
const TYPE_LABEL = {
  ExternalTool: '자료', Assignment: '과제', File: '파일', Page: '페이지',
  Quiz: '퀴즈', Discussion: '토론', ExternalUrl: '링크', SubHeader: '',
};
const _typeLabel = (t) => TYPE_LABEL[t] ?? (t || '');

/* ============== Course Detail ============== */
function CourseDetail({ courseId, openChat }) {
  const {
    now: NOW, getCourseById, getAssignmentsByCourse, getNoticesByCourse,
    markNoticeRead, toggleAssignmentSubmit,
  } = useData();
  const c = getCourseById(courseId);
  const [tab, setTab] = uS('materials');

  // 펼쳐진 공지/과제 id — 클릭 시 snippet(200자 미리보기) 대신
  // fullText(HTML 제거된 전체 본문 평문, 백엔드 message_text/description_text)를 표시 (#34)
  const [openNotice, setOpenNotice] = uS(null);
  const [openAssign, setOpenAssign] = uS(null);
  const [openDisc, setOpenDisc] = uS(null);
  const _toggle = (set) => (id) => set(cur => (String(cur) === String(id) ? null : id));
  const toggleNoticeOpen = _toggle(setOpenNotice);
  const toggleAssignOpen = _toggle(setOpenAssign);
  const toggleDiscOpen = _toggle(setOpenDisc);

  // 강의자료(주차별 모듈) — 실제 /api/courses/{id}/modules 조회
  const [mods, setMods] = uS([]);
  const [modsLoading, setModsLoading] = uS(true);
  uE(() => {
    let alive = true;
    setModsLoading(true);
    Api.fetchModules(courseId)
      .then(m => { if (alive) setMods(m); })
      .catch(() => { if (alive) setMods([]); })
      .finally(() => { if (alive) setModsLoading(false); });
    return () => { alive = false; };
  }, [courseId]);

  // 토론 목록 — 실제 /api/courses/{id}/discussions 조회 (공지와 분리된 일반 토론)
  const [discs, setDiscs] = uS([]);
  const [discsLoading, setDiscsLoading] = uS(true);
  uE(() => {
    let alive = true;
    setDiscsLoading(true);
    Api.fetchDiscussions(courseId)
      .then(d => { if (alive) setDiscs(d); })
      .catch(() => { if (alive) setDiscs([]); })
      .finally(() => { if (alive) setDiscsLoading(false); });
    return () => { alive = false; };
  }, [courseId]);

  const cAssigns = getAssignmentsByCourse(courseId);
  const cNotices = getNoticesByCourse(courseId);
  const dU = (iso) => dUFor(iso, NOW);
  const materialCount = uM(() => mods.reduce((s, m) => s + (m.items || 0), 0), [mods]);

  if (!c) return <div className="px-7 py-6 text-zinc-500">강의를 찾을 수 없습니다.</div>;

  const Tab = ({ id, label, count }) => (
    <button onClick={() => setTab(id)}
      className={`relative h-9 px-3 text-[13px] flex items-center gap-2 ${tab===id ? 'text-zinc-900' : 'text-zinc-500 hover:text-zinc-800'}`}>
      {label}
      {typeof count === 'number' && (
        <span className={`text-[10.5px] mono px-1.5 py-0.5 rounded-md ${tab===id ? 'bg-zinc-900 text-white' : 'bg-zinc-100 text-zinc-600'}`}>{count}</span>
      )}
      {tab===id && <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-zinc-900 rounded-full"/>}
    </button>
  );

  return (
    <div className="px-7 py-6 space-y-5 max-w-[1200px]">
      {/* Header */}
      <div className="ssu-card p-6 relative overflow-hidden">
        <div className="absolute -top-10 -right-10 h-48 w-48 rounded-full opacity-15 stripe-bg"
             style={{ background: c.color }}/>
        <div className="relative flex items-start gap-5">
          <div className="h-12 w-12 rounded-xl flex items-center justify-center text-white text-[14px] font-semibold mono"
               style={{ background: c.color }}>{c.code.slice(0,2)}</div>
          <div className="flex-1">
            <div className="text-[11px] mono text-zinc-500">{c.code} · {c.credits}학점 · {c.professor} 교수</div>
            <h1 className="text-[24px] font-semibold tracking-tight mt-1">{c.name}</h1>
            <div className="flex items-center gap-3 text-[11.5px] text-zinc-500 mt-2 mono">
              <span>{mods.length}개 주차</span>
              <span className="h-1 w-1 rounded-full bg-zinc-300"/>
              <span>{materialCount}개 자료</span>
              <span className="h-1 w-1 rounded-full bg-zinc-300"/>
              <span>{cAssigns.filter(a=>!a.submitted).length}건 미제출</span>
            </div>
          </div>
          <div className="flex flex-col gap-2 items-end">
            <button onClick={openChat}
              className="h-9 px-3.5 rounded-lg accent-bg text-white text-[13px] flex items-center gap-2 hover:opacity-90">
              <I2.Sparkles size={15}/> 이 강의에 대해 질문
            </button>
            <a
              href={`https://canvas.ssu.ac.kr/learningx/dashboard?course_id=${courseId}`}
              target="_blank"
              rel="noopener noreferrer"
              className="h-8 px-3 rounded-lg border border-[var(--line)] bg-white text-[12.5px] flex items-center gap-2 hover:bg-zinc-50"
            >
              <I2.External size={13}/> LMS에서 열기
            </a>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="ssu-card">
        <div className="border-b border-[var(--line)] px-3 flex items-center gap-1">
          <Tab id="materials" label="강의자료" count={mods.length}/>
          <Tab id="notices"   label="공지" count={cNotices.length}/>
          <Tab id="assignments" label="과제" count={cAssigns.length}/>
          <Tab id="discussion" label="토론" count={discs.length}/>
        </div>

        {tab === 'materials' && (
          <div className="divide-y divide-[var(--line-2)]">
            {modsLoading && (
              <div className="px-5 py-8 text-center text-[12.5px] text-zinc-500">강의자료를 불러오는 중…</div>
            )}
            {!modsLoading && mods.length === 0 && (
              <div className="px-5 py-8 text-center text-[12.5px] text-zinc-500">강의자료가 없습니다.</div>
            )}
            {!modsLoading && mods.map(m => (
              <div key={m.week} className="px-5 py-4">
                <div className="flex items-center gap-4">
                  <div className="w-12 text-center shrink-0">
                    <div className="text-[10px] uppercase mono text-zinc-500">Week</div>
                    <div className="text-[18px] font-semibold mono">{m.week}</div>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-[14px] font-medium truncate">{m.title}</div>
                    <div className="text-[11.5px] text-zinc-500 mt-0.5 mono">{m.items}개 항목</div>
                  </div>
                  <a
                    href={`https://canvas.ssu.ac.kr/learningx/dashboard?course_id=${courseId}`}
                    target="_blank" rel="noopener noreferrer"
                    className="h-8 px-2.5 text-[12px] rounded-md border border-[var(--line)] flex items-center gap-1 hover:bg-zinc-50 shrink-0"
                  >
                    <I2.External size={13}/> 열기
                  </a>
                </div>
                {m.list?.length > 0 && (
                  <div className="mt-2.5 pl-16 space-y-1.5">
                    {m.list.map(it => (
                      <div key={it.id} className="flex items-center gap-2 text-[12.5px] text-zinc-700">
                        {it.type === 'Assignment'
                          ? <I2.Check size={12} className="text-[var(--warn)] shrink-0"/>
                          : <I2.File size={12} className="text-zinc-400 shrink-0"/>}
                        {/* 항목별 딥링크(html_url)가 있으면 LMS 새 탭으로, 없으면(LTI 등) 텍스트 유지 */}
                        {it.url ? (
                          <a
                            href={it.url}
                            target="_blank" rel="noopener noreferrer"
                            className="truncate flex-1 hover:underline hover:text-zinc-900"
                          >{it.title}</a>
                        ) : (
                          <span className="truncate flex-1">{it.title}</span>
                        )}
                        <span className="text-[10px] mono text-zinc-400 shrink-0">{_typeLabel(it.type)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {tab === 'notices' && (
          <div className="divide-y divide-[var(--line-2)]">
            {cNotices.length === 0 && (
              <div className="px-5 py-8 text-center text-[12.5px] text-zinc-500">공지가 없습니다.</div>
            )}
            {cNotices.map(n => {
              const opened = String(openNotice) === String(n.id);
              const openRow = () => { markNoticeRead(n.id); toggleNoticeOpen(n.id); };
              return (
                // 펼침 영역에 원문 링크(<a>)를 넣어야 하므로 <button> 대신 div role="button"
                // (button 안의 a 는 invalid HTML)
                <div
                  key={n.id}
                  role="button"
                  tabIndex={0}
                  onClick={openRow}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openRow(); } }}
                  className="w-full text-left px-5 py-3 flex items-start gap-3 hover:bg-[var(--line-2)]/40 cursor-pointer"
                >
                  {n.unread
                    ? <span className="mt-1.5 h-1.5 w-1.5 rounded-full" style={{ background: 'var(--accent)' }}/>
                    : <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-zinc-300"/>}
                  <div className="flex-1 min-w-0">
                    <div className="text-[13.5px] font-medium flex items-center gap-2">
                      {n.pinned && <I2.Pin size={12} className="text-[var(--warn)]"/>}
                      {n.title}
                    </div>
                    {/* 펼치면 전체 본문(fullText, 평문), 접으면 snippet 2줄 미리보기 */}
                    {opened && (n.fullText || n.snippet) ? (
                      <div className="text-[12px] text-zinc-600 mt-1 whitespace-pre-wrap break-words">{n.fullText || n.snippet}</div>
                    ) : n.snippet ? (
                      <div className="text-[12px] text-zinc-600 mt-1 line-clamp-2">{n.snippet}</div>
                    ) : null}
                    {/* 공지 원문 딥링크 — html_url 이 없는 공지(LearningX 폴백)는 미표시 */}
                    {opened && n.url && (
                      <a
                        href={n.url}
                        target="_blank" rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 text-[11.5px] text-zinc-500 hover:text-zinc-800 mt-1.5"
                      >
                        <I2.External size={12}/> LMS에서 열기
                      </a>
                    )}
                    <div className="text-[11px] text-zinc-500 mono mt-0.5">{fmt2(n.date)}{n.author ? ` · ${n.author}` : ''}</div>
                  </div>
                  <span className={`text-zinc-400 transition-transform ${opened ? 'rotate-90' : ''}`}><I2.Chev size={15}/></span>
                </div>
              );
            })}
          </div>
        )}

        {tab === 'assignments' && (
          <div className="divide-y divide-[var(--line-2)]">
            {cAssigns.length === 0 && (
              <div className="px-5 py-8 text-center text-[12.5px] text-zinc-500">과제가 없습니다.</div>
            )}
            {cAssigns.map(a => {
              const d = dU(a.due);
              const opened = String(openAssign) === String(a.id);
              return (
                <div key={a.id} className="px-5 py-3 flex items-start gap-4">
                  <button
                    onClick={() => toggleAssignmentSubmit(a.id)}
                    className={`h-8 w-8 rounded-md flex items-center justify-center transition-colors shrink-0 ${a.submitted ? 'bg-emerald-50 text-[var(--ok)] hover:bg-emerald-100' : 'bg-zinc-50 text-zinc-500 hover:bg-zinc-100'}`}
                    title={a.submitted ? '제출 취소' : '제출 완료로 표시'}
                  >
                    {a.submitted ? <I2.Check size={15}/> : <I2.File size={15}/>}
                  </button>
                  {/* 본문 영역 클릭 → 전체 설명(fullText, 평문) 펼침/접힘 (#34) */}
                  <button
                    type="button"
                    onClick={() => toggleAssignOpen(a.id)}
                    className="flex-1 min-w-0 text-left"
                  >
                    <div className="text-[13.5px] font-medium truncate">{a.title}</div>
                    {opened && (a.fullText || a.snippet) ? (
                      <div className="text-[12px] text-zinc-600 mt-1 whitespace-pre-wrap break-words">{a.fullText || a.snippet}</div>
                    ) : a.snippet ? (
                      <div className="text-[12px] text-zinc-600 mt-1 line-clamp-2">{a.snippet}</div>
                    ) : null}
                    <div className="text-[11px] text-zinc-500 mono mt-0.5">배점 {a.weight}점 · {fmt2(a.due)}</div>
                  </button>
                  <div className="flex flex-col items-end gap-1.5 shrink-0 pt-1.5">
                    <div className={`text-[12px] mono ${a.submitted ? 'text-[var(--ok)]' : d.tone}`}>
                      {a.submitted ? '제출 완료' : d.label}
                    </div>
                    {/* 과제 원문 딥링크 — 본문 토글 버튼 밖에 배치 (button 안의 a 는 invalid HTML) */}
                    {a.url && (
                      <a
                        href={a.url}
                        target="_blank" rel="noopener noreferrer"
                        title="LMS에서 열기"
                        className="text-zinc-400 hover:text-zinc-700"
                      >
                        <I2.External size={13}/>
                      </a>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {tab === 'discussion' && (
          <div className="divide-y divide-[var(--line-2)]">
            {discsLoading && (
              <div className="px-5 py-8 text-center text-[12.5px] text-zinc-500">토론을 불러오는 중…</div>
            )}
            {!discsLoading && discs.length === 0 && (
              <div className="px-5 py-12 text-center text-[12.5px] text-zinc-500">
                이 강의는 토론 기능을 사용하지 않습니다.
              </div>
            )}
            {!discsLoading && discs.map(t => {
              const opened = String(openDisc) === String(t.id);
              // 토론은 공지 전용 읽음 오버레이(localStorage)와 id 충돌 우려가 있어
              // markNoticeRead 를 호출하지 않는다 — 펼침/접힘만 토글한다.
              return (
                <div
                  key={t.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => toggleDiscOpen(t.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleDiscOpen(t.id); } }}
                  className="w-full text-left px-5 py-3 flex items-start gap-3 hover:bg-[var(--line-2)]/40 cursor-pointer"
                >
                  <I2.Book size={14} className="mt-1 text-zinc-400 shrink-0"/>
                  <div className="flex-1 min-w-0">
                    <div className="text-[13.5px] font-medium">{t.title}</div>
                    {opened && (t.fullText || t.snippet) ? (
                      <div className="text-[12px] text-zinc-600 mt-1 whitespace-pre-wrap break-words">{t.fullText || t.snippet}</div>
                    ) : t.snippet ? (
                      <div className="text-[12px] text-zinc-600 mt-1 line-clamp-2">{t.snippet}</div>
                    ) : null}
                    {opened && t.url && (
                      <a
                        href={t.url}
                        target="_blank" rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 text-[11.5px] text-zinc-500 hover:text-zinc-800 mt-1.5"
                      >
                        <I2.External size={12}/> LMS에서 열기
                      </a>
                    )}
                    <div className="text-[11px] text-zinc-500 mono mt-0.5">{fmt2(t.date)}{t.author ? ` · ${t.author}` : ''}</div>
                  </div>
                  <span className={`text-zinc-400 transition-transform ${opened ? 'rotate-90' : ''}`}><I2.Chev size={15}/></span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export { CourseDetail };
