/* Calendar view */
import { COURSES as C3 } from './data';
import I3c from './icons';

/* ============== Calendar ============== */
function CalendarView() {
  // May 2026: starts on Friday (5월 1일 = 금)
  const start = 5; // index of 5/1 in week starting Sun
  const days = 31;
  const cells = [];
  for (let i = 0; i < start; i++) cells.push(null);
  for (let d = 1; d <= days; d++) cells.push(d);
  while (cells.length % 7) cells.push(null);

  const events = {
    4:  [{ c: 1, t: '선형변환 보고서', kind: 'submit' }],
    6:  [{ c: 2, t: 'AVL Tree 구현', kind: 'submit' }],
    9:  [{ c: 3, t: 'Ridge & Lasso 비교', kind: 'due' }],
    10: [{ c: 1, t: '벡터미적분 6장', kind: 'due' }],
    12: [{ c: 6, t: 'Transformer 실습', kind: 'due' }],
    13: [{ c: 5, t: '에세이 초안', kind: 'due' }],
    14: [{ c: 3, t: '주차별 퀴즈 #11', kind: 'due' }, { c: 3, t: '5/14 휴강', kind: 'notice' }],
    18: [{ c: 4, t: '스케줄링 시뮬', kind: 'due' }],
    21: [{ c: 6, t: 'GPU 서버 점검', kind: 'notice' }],
    27: [{ c: 1, t: '중간 발표', kind: 'event' }],
  };
  const today = 9;
  const W = ['일','월','화','수','목','금','토'];
  return (
    <div className="px-7 py-6 max-w-[1280px]">
      <div className="ssu-card overflow-hidden">
        <header className="px-5 py-3 flex items-center justify-between border-b border-[var(--line)]">
          <div className="flex items-center gap-3">
            <div className="text-[15px] font-semibold tracking-tight">2026년 5월</div>
            <div className="flex items-center gap-1">
              <button className="h-7 w-7 rounded-md hover:bg-zinc-100 flex items-center justify-center text-zinc-500"><I3c.Chev size={14} className="rotate-180"/></button>
              <button className="h-7 w-7 rounded-md hover:bg-zinc-100 flex items-center justify-center text-zinc-500"><I3c.Chev size={14}/></button>
              <button className="h-7 px-2.5 rounded-md hover:bg-zinc-100 text-[12px] text-zinc-700">오늘</button>
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
            const evs = (d && events[d]) || [];
            return (
              <div key={i} className={`border-r border-b border-[var(--line-2)] p-2 text-[11px] ${i%7===6 ? 'border-r-0' : ''} ${!d ? 'bg-[var(--line-2)]/20' : ''}`}>
                {d && (
                  <div className={`mono text-[10.5px] mb-1 inline-flex items-center justify-center h-5 min-w-[20px] px-1 rounded-md
                    ${isToday ? 'accent-bg text-white' : 'text-zinc-500'}`}>{d}</div>
                )}
                <div className="space-y-1">
                  {evs.slice(0,3).map((e, j) => {
                    const c = C3.find(x=>x.id===e.c);
                    const tone = e.kind === 'due'    ? { bg: c.color, text: 'white' }
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
