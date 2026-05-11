/* Sidebar + Topbar */
import React from 'react';
import Icon from './icons';
import { COURSES, NOTIFICATIONS } from './data';

/* ---------- Sidebar ---------- */
function Sidebar({ route, setRoute, currentCourse, setCourse, user, onLogout }) {
  const NavBtn = ({ id, label, IconCmp, badge }) => {
    const active = route === id;
    return (
      <button
        onClick={() => setRoute(id)}
        className={`w-full flex items-center gap-2.5 px-3 h-9 rounded-lg text-[13.5px] transition-colors
          ${active ? 'bg-white text-zinc-900 shadow-[0_1px_0_rgba(0,0,0,0.04)] border border-[var(--line)]' : 'text-zinc-600 hover:bg-white/60'}`}
      >
        <IconCmp size={17} className={active ? 'text-zinc-900' : 'text-zinc-500'} />
        <span className="flex-1 text-left">{label}</span>
        {badge ? (
          <span className="text-[11px] mono px-1.5 py-0.5 rounded-md bg-zinc-100 text-zinc-700">{badge}</span>
        ) : null}
      </button>
    );
  };
  return (
    <aside className="w-[244px] shrink-0 h-full flex flex-col bg-[#f1efea] border-r border-[var(--line)]">
      <div className="px-4 pt-5 pb-3 flex items-center gap-2.5">
        <div className="h-8 w-8 rounded-lg accent-bg text-white flex items-center justify-center">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M5 7h7M5 12h14M5 17h10"/>
          </svg>
        </div>
        <div className="leading-tight">
          <div className="text-[13.5px] font-semibold tracking-tight">LMS Bridge</div>
          <div className="text-[11px] text-zinc-500 mono">ssu · 2026 · 1학기</div>
        </div>
      </div>

      <div className="px-3 mt-2">
        <div className="relative">
          <Icon.Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input placeholder="과목 · 자료 · 공지 검색"
                 className="w-full h-8 pl-8 pr-2 text-[12.5px] rounded-md border border-[var(--line)] bg-white/70 placeholder:text-zinc-400 focus:outline-none focus:bg-white focus:ring-2 focus:ring-zinc-200" />
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] mono text-zinc-400 border border-[var(--line)] rounded px-1">⌘K</span>
        </div>
      </div>

      <nav className="px-3 pt-4 space-y-0.5">
        <NavBtn id="dashboard" label="대시보드" IconCmp={Icon.Home} />
        <NavBtn id="calendar"  label="캘린더"  IconCmp={Icon.Calendar} badge="6" />
        <NavBtn id="chat"      label="학습 비서" IconCmp={Icon.Sparkles} />
        <NavBtn id="connectors" label="커넥터"  IconCmp={Icon.Plug} badge="4/5" />
      </nav>

      <div className="px-4 mt-5 mb-2 text-[10.5px] uppercase tracking-[0.08em] text-zinc-500 font-medium">수강 강의</div>
      <div className="px-2 flex-1 overflow-y-auto scroll-hide space-y-0.5">
        {COURSES.map((c) => {
          const active = route === 'course' && currentCourse === c.id;
          return (
            <button key={c.id}
              onClick={() => { setCourse(c.id); setRoute('course'); }}
              className={`w-full flex items-center gap-2.5 px-2.5 h-9 rounded-lg text-left text-[13px]
                ${active ? 'bg-white border border-[var(--line)]' : 'hover:bg-white/60'}`}>
              <span className="h-2 w-2 rounded-sm" style={{ background: c.color }} />
              <span className="flex-1 truncate text-zinc-800">{c.name}</span>
              {c.unread > 0 && <span className="text-[10.5px] mono text-zinc-500">{c.unread}</span>}
            </button>
          );
        })}
      </div>

      <div className="px-3 py-3 border-t border-[var(--line)]">
        <div className="ssu-card px-3 py-2.5 flex items-center gap-2.5">
          <div className="h-7 w-7 rounded-full bg-zinc-200 flex items-center justify-center text-[11px] mono text-zinc-700 shrink-0">
            {user?.studentId?.slice(-2) ?? 'ME'}
          </div>
          <div className="leading-tight flex-1 min-w-0">
            <div className="text-[12.5px] font-medium truncate">학번 {user?.studentId ?? '—'}</div>
            <div className="text-[10.5px] text-zinc-500 mono truncate">{user?.studentId}@soongsil.ac.kr</div>
          </div>
          <button onClick={() => setRoute('settings')} className={`${route==='settings' ? 'text-zinc-900' : 'text-zinc-400 hover:text-zinc-700'}`} title="설정">
            <Icon.Settings size={15} />
          </button>
          {onLogout && (
            <button onClick={onLogout} className="text-zinc-400 hover:text-[var(--danger)] transition-colors" title="로그아웃">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                <polyline points="16 17 21 12 16 7"/>
                <line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}

/* ---------- Notifications popover ---------- */
function NotificationsPopover({ onClose }) {
  const [tab, setTab] = React.useState('all');
  const [items, setItems] = React.useState(NOTIFICATIONS);
  const ref = React.useRef(null);

  React.useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey); };
  }, [onClose]);

  const filtered = tab === 'unread' ? items.filter(n => n.unread)
                  : tab === 'deadline' ? items.filter(n => n.kind === 'deadline')
                  : items;
  const unreadCount = items.filter(n => n.unread).length;

  const markRead = (id) => setItems(items.map(n => n.id === id ? { ...n, unread: false } : n));
  const markAll = () => setItems(items.map(n => ({ ...n, unread: false })));

  const KindBadge = ({ kind }) => {
    const map = {
      deadline: { label: '마감',     bg: 'bg-rose-50',    fg: 'text-rose-600',    Ic: Icon.Clock },
      notice:   { label: '공지',     bg: 'bg-amber-50',   fg: 'text-amber-700',   Ic: Icon.Bell },
      sync:     { label: '동기화',   bg: 'bg-zinc-100',   fg: 'text-zinc-700',    Ic: Icon.Sync },
      graded:   { label: '채점',     bg: 'bg-emerald-50', fg: 'text-emerald-700', Ic: Icon.Check },
    }[kind] || { label: kind, bg: 'bg-zinc-100', fg: 'text-zinc-700', Ic: Icon.Bell };
    const Ic = map.Ic;
    return (
      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10.5px] font-medium ${map.bg} ${map.fg}`}>
        {Ic && <Ic size={10}/>}
        {map.label}
      </span>
    );
  };

  return (
    <div ref={ref}
      className="absolute top-[46px] right-2 w-[380px] max-h-[560px] flex flex-col
                 bg-white rounded-xl border border-[var(--line)] shadow-[0_12px_32px_rgba(20,20,30,0.10)] z-50 overflow-hidden">
      {/* header */}
      <header className="px-4 pt-3.5 pb-2.5 border-b border-[var(--line)]">
        <div className="flex items-center gap-2">
          <div className="text-[14.5px] font-semibold tracking-tight">알림</div>
          <span className="text-[10.5px] mono px-1.5 py-0.5 rounded-md bg-[var(--accent-soft)] text-[var(--accent)]">
            {unreadCount} 읽지 않음
          </span>
          <div className="flex-1"/>
          <button onClick={markAll}
            className="text-[11.5px] text-zinc-500 hover:text-zinc-800">모두 읽음</button>
        </div>
        <div className="mt-2.5 flex gap-1">
          {[['all','전체'],['unread','안읽음'],['deadline','마감']].map(([k,l]) => (
            <button key={k} onClick={() => setTab(k)}
              className={`h-6 px-2 text-[11.5px] rounded-md ${tab===k
                ? 'bg-zinc-900 text-white'
                : 'text-zinc-600 hover:bg-zinc-100'}`}>{l}</button>
          ))}
        </div>
      </header>

      {/* list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 && (
          <div className="px-4 py-10 text-center text-[12px] text-zinc-400">알림이 없습니다</div>
        )}
        {filtered.map(n => (
          <button key={n.id} onClick={() => markRead(n.id)}
            className={`w-full text-left px-4 py-3 border-b border-[var(--line-2)] flex gap-3 transition-colors
              ${n.unread ? 'bg-[var(--accent-soft)]/35 hover:bg-[var(--accent-soft)]/55' : 'hover:bg-zinc-50'}`}>
            <div className="relative shrink-0 mt-0.5">
              <span className="block h-2 w-2 rounded-full" style={{ background: n.courseColor }}/>
              {n.unread && <span className="absolute -top-1 -right-1 h-1.5 w-1.5 rounded-full bg-[var(--danger)]"/>}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5 mb-1">
                <KindBadge kind={n.kind}/>
                {n.course && <span className="text-[10.5px] mono text-zinc-500 truncate">{n.course}</span>}
              </div>
              <div className={`text-[12.5px] leading-snug ${n.unread ? 'font-semibold text-zinc-900' : 'text-zinc-700'}`}>
                {n.title}
              </div>
              <div className="text-[11.5px] text-zinc-500 mt-0.5 leading-snug">{n.body}</div>
              <div className="text-[10.5px] mono text-zinc-400 mt-1">{n.time}</div>
            </div>
          </button>
        ))}
      </div>

      {/* footer */}
      <footer className="px-4 py-2.5 border-t border-[var(--line)] flex items-center gap-2 bg-[var(--line-2)]/30">
        <button className="text-[11.5px] text-zinc-500 hover:text-zinc-800 flex items-center gap-1">
          <Icon.Settings size={12}/> 알림 설정
        </button>
        <div className="flex-1"/>
        <button className="text-[11.5px] text-[var(--accent)] font-medium hover:underline">전체 보기 →</button>
      </footer>
    </div>
  );
}

/* ---------- Topbar ---------- */
function Topbar({ title, sub, right }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="h-[58px] border-b border-[var(--line)] bg-[var(--bg)]/85 backdrop-blur sticky top-0 z-10
                    flex items-center px-7 gap-5 relative">
      <div className="flex-1 min-w-0">
        <div className="text-[15px] font-semibold tracking-tight truncate">{title}</div>
        {sub && <div className="text-[11.5px] text-zinc-500 mt-0.5 truncate">{sub}</div>}
      </div>
      <div className="flex items-center gap-2">{right}</div>
      <button onClick={() => setOpen(o => !o)}
        className={`h-8 w-8 rounded-md flex items-center justify-center relative transition-colors
          ${open ? 'bg-white border border-[var(--line)] text-zinc-900' : 'hover:bg-white/70 text-zinc-500'}`}>
        <Icon.Bell size={17} />
        <span className="absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full bg-[var(--danger)]"></span>
      </button>
      {open && <NotificationsPopover onClose={() => setOpen(false)} />}
    </div>
  );
}

export { Sidebar, Topbar };
