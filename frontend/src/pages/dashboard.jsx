/* Dashboard view */
import { useState, useEffect, useRef, useMemo } from 'react';
import { COURSES, ASSIGNMENTS, NOTICES, MODULES, ACTIVITY, USER, SEMESTER, NOW } from '../data/mockData';
import Icon from './icons';

/* ---------- helpers ---------- */
const fmtDateKR = (iso) => {
  const d = new Date(iso);
  const M = d.getMonth() + 1, D = d.getDate();
  const wd = ['일','월','화','수','목','금','토'][d.getDay()];
  const hh = String(d.getHours()).padStart(2,'0'), mm = String(d.getMinutes()).padStart(2,'0');
  return `${M}/${D} (${wd}) ${hh}:${mm}`;
};
const daysUntil = (iso) => {
  const d = new Date(iso);
  const ms = d - NOW;
  if (ms < 0) return { label: '지남', kind: 'past', n: ms/86400000 };
  const days = Math.floor(ms / 86400000);
  const hrs  = Math.floor((ms % 86400000) / 3600000);
  if (days === 0) return { label: `오늘 ${hrs}시간 후`, kind: 'today', n: 0 };
  if (days === 1) return { label: '내일', kind: 'soon', n: 1 };
  if (days <= 3)  return { label: `D-${days}`, kind: 'soon', n: days };
  return { label: `D-${days}`, kind: 'later', n: days };
};
const courseById = (id) => COURSES.find(c => c.id === id);
const typeIcon = (t) => ({ report: Icon.File, code: Icon.Code, quiz: Icon.Quiz, essay: Icon.Essay, problem: Icon.File }[t] || Icon.File);

/* ---------- Dashboard ---------- */
function Dashboard({ openCourse, openChat }) {
  const upcoming = ASSIGNMENTS
    .filter(a => !a.submitted)
    .sort((a,b) => new Date(a.due) - new Date(b.due))
    .slice(0, 5);
  const noticesUnread = NOTICES.filter(n => n.unread).length;
  const totalDue      = ASSIGNMENTS.filter(a => !a.submitted).length;
  const submitted     = ASSIGNMENTS.filter(a => a.submitted).length;
  const totalAssign   = ASSIGNMENTS.length;

  // 이번 주(NOW 기준 7일 이내) 마감 과제 수
  const weekMs = 7 * 86400000;
  const dueThisWeek = ASSIGNMENTS.filter(a => {
    if (a.submitted) return false;
    const diff = new Date(a.due) - NOW;
    return diff >= 0 && diff <= weekMs;
  }).length;

  // 전체 강의 평균 진행률
  const avgProgress = COURSES.length
    ? Math.round((COURSES.reduce((s,c) => s + c.progress, 0) / COURSES.length) * 100)
    : 0;

  return (
    <div className="px-7 py-6 space-y-6 max-w-[1280px]">
      {/* Hero */}
      <div className="ssu-card p-6 relative overflow-hidden">
        <div className="absolute inset-0 grid-bg pointer-events-none opacity-50" />
        <div className="relative flex items-start gap-8">
          <div className="flex-1">
            <div className="text-[11px] mono text-zinc-500 mb-1">{SEMESTER.todayLabel}</div>
            <h1 className="text-[26px] font-semibold tracking-tight leading-tight">
              안녕하세요, {USER.name}님 — <span className="text-zinc-500">이번 주 마감 {dueThisWeek}건이 있어요.</span>
            </h1>
            <div className="flex flex-wrap gap-2 mt-4">
              <button onClick={openChat}
                className="h-9 px-3.5 rounded-lg accent-bg text-white text-[13px] font-medium flex items-center gap-2 hover:opacity-90">
                <Icon.Sparkles size={15}/> 비서에게 정리 받기
              </button>
              <button className="h-9 px-3.5 rounded-lg border border-[var(--line)] bg-white text-[13px] flex items-center gap-2 hover:bg-zinc-50">
                <Icon.Sync size={15}/> 지금 동기화
              </button>
              <button className="h-9 px-3.5 rounded-lg border border-[var(--line)] bg-white text-[13px] flex items-center gap-2 hover:bg-zinc-50">
                <Icon.External size={14}/> Notion에서 열기
              </button>
            </div>
          </div>
          <div className="hidden md:grid grid-cols-3 gap-3 w-[420px]">
            <Stat label="이번 주 마감" value={String(dueThisWeek)} hint="다가오는 과제" />
            <Stat label="안 읽은 공지" value={String(noticesUnread)} hint="LMS 신규" />
            <Stat label="진행률" value={`${avgProgress}%`} hint={`${SEMESTER.weekCurrent}/${SEMESTER.weekTotal}주차`} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-5">
        {/* Upcoming */}
        <section className="col-span-12 lg:col-span-8 ssu-card">
          <header className="flex items-center justify-between px-5 pt-4 pb-3">
            <div>
              <div className="text-[14.5px] font-semibold">다가오는 마감</div>
              <div className="text-[11.5px] text-zinc-500">{totalDue}건 미제출 · 다음 7일 정렬</div>
            </div>
            <div className="flex items-center gap-1.5">
              <Pill active>리스트</Pill>
              <Pill>타임라인</Pill>
            </div>
          </header>
          <div className="border-t border-[var(--line)]">
            {upcoming.map((a, i) => {
              const c = courseById(a.course);
              const d = daysUntil(a.due);
              const TI = typeIcon(a.type);
              const tone = d.kind === 'today' ? 'text-[var(--danger)]'
                        : d.kind === 'soon' ? 'text-[var(--warn)]'
                        : 'text-zinc-500';
              return (
                <div key={a.id}
                     className="grid grid-cols-[80px_1fr_auto_auto] items-center gap-4 px-5 py-3 border-b border-[var(--line-2)] last:border-0 group hover:bg-[var(--line-2)]/40">
                  <div className="text-[11px] mono text-zinc-500 flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-sm" style={{ background: c.color }}/>
                    {c.code}
                  </div>
                  <div className="min-w-0">
                    <div className="text-[13.5px] text-zinc-900 truncate flex items-center gap-2">
                      <TI size={14} className="text-zinc-400 shrink-0"/>
                      {a.title}
                    </div>
                    <div className="text-[11.5px] text-zinc-500 mt-0.5">
                      {c.name} · 비중 {a.weight}%
                    </div>
                  </div>
                  <div className={`text-[12px] mono ${tone} text-right`}>
                    <div className="font-medium">{d.label}</div>
                    <div className="text-zinc-400 text-[11px]">{fmtDateKR(a.due)}</div>
                  </div>
                  <button className="opacity-0 group-hover:opacity-100 text-zinc-400 hover:text-zinc-700">
                    <Icon.Chev size={16}/>
                  </button>
                </div>
              );
            })}
          </div>
          <footer className="px-5 py-2.5 text-[12px] text-zinc-500 flex items-center justify-between border-t border-[var(--line-2)]">
            <span>{submitted}/{totalAssign} 제출 완료 · 평균 제출 시점 마감 -1.4일</span>
            <button className="text-zinc-700 hover:underline flex items-center gap-1">전체 보기 <Icon.Chev size={13}/></button>
          </footer>
        </section>

        {/* Notices + Activity */}
        <section className="col-span-12 lg:col-span-4 space-y-5">
          <div className="ssu-card">
            <header className="flex items-center justify-between px-5 pt-4 pb-3">
              <div>
                <div className="text-[14.5px] font-semibold">최근 공지</div>
                <div className="text-[11.5px] text-zinc-500">{noticesUnread}건 안 읽음</div>
              </div>
              <button className="text-[12px] text-zinc-500 hover:text-zinc-900">모두 읽음</button>
            </header>
            <div className="border-t border-[var(--line)]">
              {NOTICES.slice(0, 5).map(n => {
                const c = courseById(n.course);
                return (
                  <div key={n.id} className="px-5 py-2.5 border-b border-[var(--line-2)] last:border-0 flex items-start gap-3 hover:bg-[var(--line-2)]/40">
                    <div className="pt-1.5">
                      {n.unread
                        ? <span className="h-1.5 w-1.5 rounded-full block" style={{ background: 'var(--accent)' }}/>
                        : <span className="h-1.5 w-1.5 rounded-full block bg-zinc-300"/>}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] text-zinc-900 truncate flex items-center gap-1.5">
                        {n.pinned && <Icon.Pin size={12} className="text-[var(--warn)] shrink-0"/>}
                        {n.title}
                      </div>
                      <div className="text-[11px] text-zinc-500 mt-0.5 mono">
                        {c.code} · {fmtDateKR(n.date)}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="ssu-card">
            <header className="px-5 pt-4 pb-2 flex items-center justify-between">
              <div className="text-[14.5px] font-semibold">동기화 활동</div>
              <span className="text-[11px] mono text-[var(--ok)] flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-[var(--ok)]"/> 정상
              </span>
            </header>
            <div className="px-5 pb-4 pt-1">
              <ul className="relative">
                <span className="absolute left-[5px] top-1.5 bottom-1.5 w-px bg-[var(--line)]"/>
                {ACTIVITY.map((a, i) => (
                  <li key={i} className="pl-5 relative py-1.5">
                    <span className="absolute left-0 top-2.5 h-2.5 w-2.5 rounded-full bg-white border-2"
                      style={{ borderColor: a.kind === 'sync' ? 'var(--accent)' : a.kind === 'auth' ? 'var(--warn)' : a.kind === 'submit' ? 'var(--ok)' : 'var(--muted)' }}/>
                    <div className="text-[12.5px] text-zinc-800">{a.text}</div>
                    <div className="text-[10.5px] mono text-zinc-500">{a.t} · {a.meta}</div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      </div>

      {/* Course grid */}
      <section>
        <header className="flex items-center justify-between mb-3">
          <div>
            <div className="text-[14.5px] font-semibold">강의 그리드</div>
            <div className="text-[11.5px] text-zinc-500">{COURSES.length}개 강의 · 캔버스 동기화 완료</div>
          </div>
          <button className="text-[12px] text-zinc-500 flex items-center gap-1 hover:text-zinc-900">
            <Icon.Filter size={13}/> 학기별
          </button>
        </header>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {COURSES.map(c => (
            <button key={c.id} onClick={() => openCourse(c.id)}
              className="ssu-card p-4 text-left hover:border-zinc-300 hover:shadow-[0_2px_0_rgba(0,0,0,0.02)] transition">
              <div className="flex items-start justify-between gap-2">
                <span className="h-7 w-7 rounded-md flex items-center justify-center text-white text-[11px] font-semibold mono"
                      style={{ background: c.color }}>{c.code.slice(0,2)}</span>
                <div className="flex items-center gap-1.5">
                  {c.unread > 0 && <span className="text-[10.5px] mono px-1.5 py-0.5 rounded-md bg-[var(--accent-soft)] text-[var(--accent)]">공지 {c.unread}</span>}
                  {c.dueSoon > 0 && <span className="text-[10.5px] mono px-1.5 py-0.5 rounded-md bg-orange-50 text-[var(--warn)]">D-{c.dueSoon}</span>}
                </div>
              </div>
              <div className="mt-3 text-[14.5px] font-semibold tracking-tight">{c.name}</div>
              <div className="text-[11.5px] text-zinc-500 mt-0.5">{c.professor} · {c.credits}학점 · {c.code}</div>
              <div className="mt-4">
                <div className="flex items-center justify-between text-[11px] mono text-zinc-500 mb-1.5">
                  <span>주차 {c.weekCurrent}/{c.weekTotal}</span>
                  <span>{Math.round(c.progress*100)}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-zinc-100 overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: (c.progress*100)+'%', background: c.color }}/>
                </div>
              </div>
              <div className="mt-3 flex items-center gap-3 text-[11.5px] text-zinc-500">
                <span className="flex items-center gap-1"><Icon.File size={12}/> {c.materials}</span>
                <span className="flex items-center gap-1"><Icon.Bell size={12}/> {c.unread}</span>
                <span className="flex items-center gap-1"><Icon.Clock size={12}/> {c.dueSoon}</span>
              </div>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

const Stat = ({ label, value, hint }) => (
  <div className="ssu-card !rounded-xl p-3.5 bg-white">
    <div className="text-[10.5px] uppercase tracking-[0.08em] text-zinc-500 font-medium">{label}</div>
    <div className="text-[26px] font-semibold tracking-tight leading-none mt-2">{value}</div>
    <div className="text-[11px] text-zinc-500 mt-1.5 mono">{hint}</div>
  </div>
);

const Pill = ({ children, active }) => (
  <button className={`h-7 px-2.5 text-[11.5px] rounded-md border ${active ? 'bg-zinc-900 text-white border-zinc-900' : 'border-[var(--line)] text-zinc-600 hover:bg-zinc-50'}`}>{children}</button>
);

export { Dashboard };
