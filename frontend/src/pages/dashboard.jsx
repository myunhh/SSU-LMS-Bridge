/* Dashboard view */
import { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useData } from '../data/DataStore';
import Icon from './icons';

/* ---------- helpers ---------- */
const fmtDateKR = (iso) => {
  const d = new Date(iso);
  const M = d.getMonth() + 1, D = d.getDate();
  const wd = ['일','월','화','수','목','금','토'][d.getDay()];
  const hh = String(d.getHours()).padStart(2,'0'), mm = String(d.getMinutes()).padStart(2,'0');
  return `${M}/${D} (${wd}) ${hh}:${mm}`;
};
const daysUntilFor = (iso, NOW) => {
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
const typeIcon = (t) => ({ report: Icon.File, code: Icon.Code, quiz: Icon.Quiz, essay: Icon.Essay, problem: Icon.File }[t] || Icon.File);
const _relTime = (iso, now) => {
  if (!iso) return '';
  const ms = now - new Date(iso);
  if (ms < 60_000) return '방금 전';
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}분 전`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}시간 전`;
  return `${Math.floor(ms / 86_400_000)}일 전`;
};

/* ---------- LMS 미연결 / 로딩 게이트 (#4) ----------
 * 로그인은 됐지만 LMS 미연결(세션 없음/만료)이면 가짜 seed 대신 안내 빈 상태를,
 * 세션 확인·첫 fetch 중이면 스켈레톤을 보여 준다. mock 모드(USE_MOCK)에서는
 * lmsConnected 가 항상 true 라 이 게이트를 통과한다. */
function GateSkeleton() {
  return (
    <div className="px-7 py-6 space-y-6 max-w-[1280px]" aria-busy="true" aria-label="불러오는 중">
      <div className="ssu-card p-6 h-[148px] animate-pulse bg-zinc-100/60" />
      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-12 lg:col-span-8 ssu-card h-[320px] animate-pulse bg-zinc-100/60" />
        <div className="col-span-12 lg:col-span-4 ssu-card h-[320px] animate-pulse bg-zinc-100/60" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="ssu-card h-[176px] animate-pulse bg-zinc-100/60" />
        ))}
      </div>
    </div>
  );
}

function LmsEmptyState() {
  const navigate = useNavigate();
  return (
    <div className="px-7 py-6 max-w-[1280px]">
      <div className="ssu-card p-10 flex flex-col items-center text-center gap-4">
        <span className="h-12 w-12 rounded-xl flex items-center justify-center bg-[var(--accent-soft)] text-[var(--accent)]">
          <Icon.Book size={22} />
        </span>
        <div>
          <div className="text-[16px] font-semibold tracking-tight">아직 LMS에 연결되지 않았어요</div>
          <p className="text-[13px] text-zinc-500 mt-1.5 leading-relaxed">
            강의·과제·공지를 불러오려면 먼저 Connectors에서 숭실대 스마트캠퍼스 LMS에 로그인하세요.
          </p>
        </div>
        <button
          onClick={() => navigate('/connectors')}
          className="h-9 px-4 rounded-lg accent-bg text-white text-[13px] font-medium flex items-center gap-2 hover:opacity-90"
        >
          <Icon.Book size={15} /> Connectors에서 로그인
        </button>
      </div>
    </div>
  );
}

/* ---------- Dashboard ---------- */
function Dashboard({ openCourse, openChat, openCalendar }) {
  const {
    courses: COURSES, assignments: ASSIGNMENTS, notices: NOTICES, activity: ACTIVITY,
    user: USER, semester: SEMESTER, now: NOW,
    getCourseById, markNoticeRead, markAllNoticesRead, toggleAssignmentSubmit,
    triggerSync, syncing, lastSyncAt,
    lmsConnected, lmsSession, firstFetchDone, loading,
  } = useData();
  const courseById = getCourseById;

  // 게이트(#4):
  //   ① 세션 상태 아직 모름(lmsSession === null, 첫 조회 전) → 스켈레톤(빈 상태 깜빡임 방지)
  //   ② LMS 미연결(세션 없음/만료) 확정 → 안내 빈 상태
  //   ③ 연결됐지만 첫 fetch 전/로딩 중 → 스켈레톤
  // mock 모드(USE_MOCK)에서는 lmsConnected 가 항상 true 라 ①②를 건너뛴다.
  if (!lmsConnected && lmsSession == null) return <GateSkeleton />;
  if (!lmsConnected) return <LmsEmptyState />;
  if (!firstFetchDone || loading) return <GateSkeleton />;
  const daysUntil = (iso) => daysUntilFor(iso, NOW);
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

  // 전체 강의 평균 출석율 (각 과목 progress = 출결현황 출석율)
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
              <button
                onClick={triggerSync}
                disabled={syncing}
                className="h-9 px-3.5 rounded-lg border border-[var(--line)] bg-white text-[13px] flex items-center gap-2 hover:bg-zinc-50 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <Icon.Sync size={15} className={syncing ? 'animate-spin' : ''}/>
                {syncing ? '동기화 중…' : '지금 동기화'}
              </button>
              <a
                href="https://www.notion.so"
                target="_blank"
                rel="noopener noreferrer"
                className="h-9 px-3.5 rounded-lg border border-[var(--line)] bg-white text-[13px] flex items-center gap-2 hover:bg-zinc-50"
              >
                <Icon.External size={14}/> Notion에서 열기
              </a>
            </div>
          </div>
          <div className="hidden md:grid grid-cols-3 gap-3 w-[420px]">
            <Stat label="이번 주 마감" value={String(dueThisWeek)} hint="다가오는 과제" />
            <Stat label="안 읽은 공지" value={String(noticesUnread)} hint="LMS 신규" />
            <Stat label="평균 출석율" value={`${avgProgress}%`} hint="출결현황 기준" />
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
                  {/* 강의 목록 부분 로드 실패 시 c가 undefined일 수 있음 — DataStore.notifications와 동일 방어 */}
                  <div className="text-[11px] mono text-zinc-500 flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-sm" style={{ background: c?.color || 'var(--muted)' }}/>
                    {c?.code ?? ''}
                  </div>
                  <div className="min-w-0">
                    <div className="text-[13.5px] text-zinc-900 truncate flex items-center gap-2">
                      <TI size={14} className="text-zinc-400 shrink-0"/>
                      {a.title}
                    </div>
                    <div className="text-[11.5px] text-zinc-500 mt-0.5">
                      {/* weight = points_possible(배점) — '배점 N점' 표기 통일 (api/index.js 참고) */}
                      {c?.name ?? ''} · 배점 {a.weight}점
                    </div>
                  </div>
                  <div className={`text-[12px] mono ${tone} text-right`}>
                    <div className="font-medium">{d.label}</div>
                    <div className="text-zinc-400 text-[11px]">{fmtDateKR(a.due)}</div>
                  </div>
                  <button
                    onClick={() => toggleAssignmentSubmit(a.id)}
                    className="opacity-0 group-hover:opacity-100 text-[11px] mono px-2 py-1 rounded border border-[var(--line)] hover:bg-white text-zinc-600"
                    title="제출 완료로 표시"
                  >
                    제출
                  </button>
                </div>
              );
            })}
          </div>
          <footer className="px-5 py-2.5 text-[12px] text-zinc-500 flex items-center justify-between border-t border-[var(--line-2)]">
            <span>{submitted}/{totalAssign} 제출 완료</span>
            <button onClick={openCalendar} className="text-zinc-700 hover:underline flex items-center gap-1">캘린더에서 보기 <Icon.Chev size={13}/></button>
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
              <button
                onClick={markAllNoticesRead}
                disabled={noticesUnread === 0}
                className="text-[12px] text-zinc-500 hover:text-zinc-900 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-zinc-500"
              >모두 읽음</button>
            </header>
            <div className="border-t border-[var(--line)]">
              {NOTICES.slice(0, 5).map(n => {
                const c = courseById(n.course);
                return (
                  <button
                    key={n.id}
                    onClick={() => { markNoticeRead(n.id); openCourse(n.course); }}
                    className="w-full text-left px-5 py-2.5 border-b border-[var(--line-2)] last:border-0 flex items-start gap-3 hover:bg-[var(--line-2)]/40"
                  >
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
                        {/* 강의 목록 부분 로드 실패 시 c가 undefined일 수 있음 — DataStore.notifications와 동일 방어 */}
                        {c?.code ?? ''} · {fmtDateKR(n.date)}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="ssu-card">
            <header className="px-5 pt-4 pb-2 flex items-center justify-between">
              <div>
                <div className="text-[14.5px] font-semibold">동기화 활동</div>
                {lastSyncAt && (
                  <div className="text-[11px] mono text-zinc-500 mt-0.5">
                    마지막 동기화 {_relTime(lastSyncAt.toISOString(), NOW)}
                  </div>
                )}
              </div>
              {/* 활동/동기화 기록이 있을 때만 '정상' — 근거 없는 상시 초록 배지 제거 */}
              {(lastSyncAt || ACTIVITY.length > 0) ? (
                <span className="text-[11px] mono text-[var(--ok)] flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-[var(--ok)]"/> 정상
                </span>
              ) : (
                <span className="text-[11px] mono text-zinc-400 flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-zinc-300"/> 대기
                </span>
              )}
            </header>
            <div className="px-5 pb-4 pt-1">
              {ACTIVITY.length === 0 ? (
                <div className="text-[12px] text-zinc-500 py-3">
                  아직 활동 기록이 없습니다. 동기화하거나 LMS에 로그인하면 여기에 쌓입니다.
                </div>
              ) : (
                <ul className="relative">
                  <span className="absolute left-[5px] top-1.5 bottom-1.5 w-px bg-[var(--line)]"/>
                  {ACTIVITY.map((a, i) => (
                    <li key={i} className="pl-5 relative py-1.5">
                      <span className="absolute left-0 top-2.5 h-2.5 w-2.5 rounded-full bg-white border-2"
                        style={{ borderColor: a.kind === 'sync' ? 'var(--accent)' : a.kind === 'auth' ? 'var(--warn)' : a.kind === 'submit' ? 'var(--ok)' : 'var(--muted)' }}/>
                      <div className="text-[12.5px] text-zinc-800">{a.text}</div>
                      {/* 상대시각은 저장된 at(ISO)으로 렌더 시점(NOW)에 계산 — 새로고침해도 정확 */}
                      <div className="text-[10.5px] mono text-zinc-500">
                        {[_relTime(a.at, NOW), a.meta].filter(Boolean).join(' · ')}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </section>
      </div>

      {/* Course grid */}
      <section>
        <header className="flex items-center justify-between mb-3">
          <div>
            <div className="text-[14.5px] font-semibold">강의 그리드</div>
            <div className="text-[11.5px] text-zinc-500">
              {COURSES.length}개 강의
              {lastSyncAt && ` · ${_relTime(lastSyncAt.toISOString(), NOW)} 동기화`}
            </div>
          </div>
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
                  <span>출석율</span>
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

export { Dashboard };
