/* Calendar view */
import { useState, useMemo } from 'react';
import { useData } from '../data/DataStore';
import I3c from './icons';

const W = ['일','월','화','수','목','금','토'];

/* ============== Calendar ============== */
function CalendarView() {
  const { courses: C3, assignments, notices, now } = useData();

  // 현재 보고 있는 월 (year, month는 1~12). 초기값은 NOW 의 월.
  const [view, setView] = useState({
    year:  now.getFullYear(),
    month: now.getMonth() + 1,
  });

  // ── 이번 달 셀 + 이벤트 계산 ────────────────────────────────────────────────
  const { cells, eventsByDay, label, isCurrentMonth, today } = useMemo(() => {
    const first = new Date(view.year, view.month - 1, 1);
    const startWeekday = first.getDay();
    const days = new Date(view.year, view.month, 0).getDate();

    const list = [];
    for (let i = 0; i < startWeekday; i++) list.push(null);
    for (let d = 1; d <= days; d++) list.push(d);
    while (list.length % 7) list.push(null);

    // 이번 달의 이벤트 집계: 과제(due/submit) + 공지(휴강 등 본문에 날짜 있는 것)
    const ev = {};
    const push = (day, item) => { (ev[day] ||= []).push(item); };

    for (const a of assignments) {
      const d = new Date(a.due);
      if (d.getFullYear() !== view.year || d.getMonth() + 1 !== view.month) continue;
      push(d.getDate(), {
        c: a.course,
        t: a.title.length > 18 ? a.title.slice(0, 18) + '…' : a.title,
        kind: a.submitted ? 'submit' : 'due',
      });
    }
    for (const n of notices) {
      // "5/14 강의 휴강" 같은 본문 패턴: 그 날짜에 배치
      if (n.title.includes('휴강')) {
        const m = n.title.match(/(\d{1,2})\/(\d{1,2})/);
        if (m) {
          const mm = Number(m[1]);
          const dd = Number(m[2]);
          if (mm === view.month) push(dd, { c: n.course, t: n.title, kind: 'notice' });
        }
      }
    }

    const isCurrent =
      view.year === now.getFullYear() && view.month === now.getMonth() + 1;

    return {
      cells: list,
      eventsByDay: ev,
      label: `${view.year}년 ${view.month}월`,
      isCurrentMonth: isCurrent,
      today: isCurrent ? now.getDate() : -1,
    };
  }, [view, assignments, notices, now]);

  // ── 액션 ────────────────────────────────────────────────────────────────
  const prev = () => setView(v => {
    const m = v.month - 1;
    return m < 1 ? { year: v.year - 1, month: 12 } : { ...v, month: m };
  });
  const next = () => setView(v => {
    const m = v.month + 1;
    return m > 12 ? { year: v.year + 1, month: 1 } : { ...v, month: m };
  });
  const goToday = () => setView({ year: now.getFullYear(), month: now.getMonth() + 1 });

  return (
    <div className="px-7 py-6 max-w-[1280px]">
      <div className="ssu-card overflow-hidden">
        <header className="px-5 py-3 flex items-center justify-between border-b border-[var(--line)]">
          <div className="flex items-center gap-3">
            <div className="text-[15px] font-semibold tracking-tight">{label}</div>
            <div className="flex items-center gap-1">
              <button
                onClick={prev}
                aria-label="이전 달"
                className="h-7 w-7 rounded-md hover:bg-zinc-100 flex items-center justify-center text-zinc-500"
              >
                <I3c.Chev size={14} className="rotate-180"/>
              </button>
              <button
                onClick={next}
                aria-label="다음 달"
                className="h-7 w-7 rounded-md hover:bg-zinc-100 flex items-center justify-center text-zinc-500"
              >
                <I3c.Chev size={14}/>
              </button>
              <button
                onClick={goToday}
                disabled={isCurrentMonth}
                className="h-7 px-2.5 rounded-md hover:bg-zinc-100 text-[12px] text-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                오늘
              </button>
            </div>
          </div>
          <div className="flex items-center gap-3 text-[11px] mono text-zinc-500">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{background:'var(--accent)'}}/>마감</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-[var(--ok)]"/>제출</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-[var(--warn)]"/>공지/이벤트</span>
          </div>
        </header>
        <div className="grid grid-cols-7 border-b border-[var(--line)] bg-[var(--line-2)]/40">
          {W.map((w,i) => (
            <div key={i} className={`text-center text-[10.5px] mono py-2 ${i===0 ? 'text-[var(--danger)]' : i===6 ? 'text-[var(--accent)]' : 'text-zinc-500'}`}>{w}</div>
          ))}
        </div>
        <div className="grid grid-cols-7" style={{ gridAutoRows: 'minmax(108px, 1fr)' }}>
          {cells.map((d, i) => {
            const isToday = d === today;
            const evs = (d && eventsByDay[d]) || [];
            return (
              <div key={i} className={`border-r border-b border-[var(--line-2)] p-2 text-[11px] ${i%7===6 ? 'border-r-0' : ''} ${!d ? 'bg-[var(--line-2)]/20' : ''}`}>
                {d && (
                  <div className={`mono text-[10.5px] mb-1 inline-flex items-center justify-center h-5 min-w-[20px] px-1 rounded-md
                    ${isToday ? 'accent-bg text-white' : 'text-zinc-500'}`}>{d}</div>
                )}
                <div className="space-y-1">
                  {evs.slice(0,3).map((e, j) => {
                    const c = C3.find(x => x.id === e.c);
                    const tone = e.kind === 'due'    ? { bg: c?.color || 'var(--accent)', text: 'white' }
                              : e.kind === 'submit' ? { bg: 'var(--ok)', text: 'white' }
                              : e.kind === 'event'  ? { bg: 'var(--warn)', text: 'white' }
                              : { bg: 'var(--accent-soft)', text: 'var(--accent)' };
                    return (
                      <div key={j} className="text-[10.5px] truncate px-1.5 py-0.5 rounded"
                           style={{ background: tone.bg, color: tone.text }}>
                        {e.kind === 'submit' && '✓ '}
                        {e.t}
                      </div>
                    );
                  })}
                  {evs.length > 3 && (
                    <div className="text-[10px] mono text-zinc-400 px-1">+{evs.length - 3}건 더</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export { CalendarView };
