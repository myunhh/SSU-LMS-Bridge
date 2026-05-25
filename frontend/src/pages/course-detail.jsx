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
          <Tab id="discussion" label="토론" count={0}/>
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
                        <span className="truncate flex-1">{it.title}</span>
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
            {cNotices.map(n => (
              <button
                key={n.id}
                onClick={() => markNoticeRead(n.id)}
                className="w-full text-left px-5 py-3 flex items-start gap-3 hover:bg-[var(--line-2)]/40"
              >
                {n.unread
                  ? <span className="mt-1.5 h-1.5 w-1.5 rounded-full" style={{ background: 'var(--accent)' }}/>
                  : <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-zinc-300"/>}
                <div className="flex-1 min-w-0">
                  <div className="text-[13.5px] font-medium flex items-center gap-2">
                    {n.pinned && <I2.Pin size={12} className="text-[var(--warn)]"/>}
                    {n.title}
                  </div>
                  <div className="text-[11px] text-zinc-500 mono mt-0.5">{fmt2(n.date)}</div>
                </div>
                <span className="text-zinc-400"><I2.Chev size={15}/></span>
              </button>
            ))}
          </div>
        )}

        {tab === 'assignments' && (
          <div className="divide-y divide-[var(--line-2)]">
            {cAssigns.length === 0 && (
              <div className="px-5 py-8 text-center text-[12.5px] text-zinc-500">과제가 없습니다.</div>
            )}
            {cAssigns.map(a => {
              const d = dU(a.due);
              return (
                <div key={a.id} className="px-5 py-3 flex items-center gap-4">
                  <button
                    onClick={() => toggleAssignmentSubmit(a.id)}
                    className={`h-8 w-8 rounded-md flex items-center justify-center transition-colors ${a.submitted ? 'bg-emerald-50 text-[var(--ok)] hover:bg-emerald-100' : 'bg-zinc-50 text-zinc-500 hover:bg-zinc-100'}`}
                    title={a.submitted ? '제출 취소' : '제출 완료로 표시'}
                  >
                    {a.submitted ? <I2.Check size={15}/> : <I2.File size={15}/>}
                  </button>
                  <div className="flex-1 min-w-0">
                    <div className="text-[13.5px] font-medium truncate">{a.title}</div>
                    <div className="text-[11px] text-zinc-500 mono mt-0.5">비중 {a.weight}% · {fmt2(a.due)}</div>
                  </div>
                  <div className={`text-[12px] mono ${a.submitted ? 'text-[var(--ok)]' : d.tone}`}>
                    {a.submitted ? '제출 완료' : d.label}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {tab === 'discussion' && (
          <div className="px-5 py-12 text-center text-[12.5px] text-zinc-500">
            이 강의는 토론 기능을 사용하지 않습니다.
          </div>
        )}
      </div>
    </div>
  );
}

export { CourseDetail };
