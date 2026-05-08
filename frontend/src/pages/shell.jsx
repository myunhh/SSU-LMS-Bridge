/* App shell — wires routes + tweaks */

const { useState: aS, useEffect: aE } = React;
const { Sidebar, Topbar } = window.SSUSidebar;
const { Dashboard } = window.SSUDashboard;
const { CourseDetail } = window.SSUCourseDetail;
const { ChatView } = window.SSUChat;
const { ConnectorsView } = window.SSUConnectors;
const { CalendarView } = window.SSUCalendar;
const { SettingsView } = window.SSUSettings;
const Ic = window.Icon;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "#3a4ca8",
  "density": "comfortable",
  "background": "warm",
  "shellRadius": 14
}/*EDITMODE-END*/;

function App() {
  const [route, setRoute] = aS('dashboard');
  const [course, setCourse] = aS(3);
  const tweaks = (window.useTweaks ? window.useTweaks(TWEAK_DEFAULTS) : null);

  // apply tweaks live
  aE(() => {
    const t = tweaks?.tweaks ?? TWEAK_DEFAULTS;
    document.documentElement.style.setProperty('--accent', t.accent);
    // soften alpha for accent-soft
    document.documentElement.style.setProperty('--accent-soft',
      `color-mix(in oklch, ${t.accent} 12%, white)`);
    const bg = t.background === 'cool'   ? '#f4f5f8'
            : t.background === 'mono'    ? '#f5f5f5'
            :                              '#f7f6f3';
    document.documentElement.style.setProperty('--bg', bg);
    document.documentElement.style.setProperty('--line', t.background==='mono' ? '#e4e4e7' : '#e7e5e0');
    document.documentElement.style.setProperty('--line-2', t.background==='mono' ? '#ededed' : '#efece6');
  }, [tweaks?.tweaks]);

  const titles = {
    dashboard:  { t: '대시보드',     s: '2026년 1학기 · 11주차' },
    calendar:   { t: '캘린더',       s: '과제 마감 · 공지 · 학사 이벤트' },
    chat:       { t: '학습 비서',    s: 'RAG · 강의자료 컨텍스트 활성' },
    connectors: { t: '커넥터',       s: 'LMS · Notion · Obsidian · LLM' },
    settings:   { t: '설정',         s: '계정 · 알림 · 동기화 · 외관' },
    course:     null,
  };
  const cur = titles[route];
  const c = window.SSU.COURSES.find(x => x.id === course);
  const top = cur || { t: c.name, s: `${c.code} · ${c.professor} 교수 · ${c.credits}학점` };

  return (
    <div className="h-screen flex bg-[var(--bg)] overflow-hidden">
      <Sidebar route={route} setRoute={setRoute}
               currentCourse={course} setCourse={setCourse}/>
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Topbar
          title={top.t}
          sub={top.s}
          right={
            <>
              <button className="h-8 px-2.5 rounded-md border border-[var(--line)] bg-white text-[12px] flex items-center gap-1.5 hover:bg-zinc-50">
                <Ic.Sync size={13}/> 동기화
              </button>
              <button className="h-8 px-2.5 rounded-md border border-[var(--line)] bg-white text-[12px] flex items-center gap-1.5 hover:bg-zinc-50">
                <Ic.External size={13}/> LMS
              </button>
            </>
          }
        />
        <div className="flex-1 overflow-y-auto">
          {route === 'dashboard'  && <Dashboard openCourse={(id) => { setCourse(id); setRoute('course'); }} openChat={() => setRoute('chat')}/>}
          {route === 'course'     && <CourseDetail courseId={course} openChat={() => setRoute('chat')}/>}
          {route === 'chat'       && <ChatView/>}
          {route === 'connectors' && <ConnectorsView/>}
          {route === 'calendar'   && <CalendarView/>}
          {route === 'settings'   && <SettingsView/>}
        </div>
      </main>

      {/* Tweaks panel */}
      {window.TweaksPanel && tweaks?.editMode && (
        <window.TweaksPanel onClose={tweaks.dismiss} title="Tweaks">
          <window.TweakSection title="브랜드">
            <window.TweakColor label="Accent" options={['#3a4ca8','#1f2937','#0f766e','#9a3412','#7c3aed']}
                               value={tweaks.tweaks.accent}
                               onChange={(v) => tweaks.setTweak('accent', v)}/>
          </window.TweakSection>
          <window.TweakSection title="화면">
            <window.TweakRadio label="배경 톤"
              options={[{value:'warm',label:'Warm'},{value:'cool',label:'Cool'},{value:'mono',label:'Mono'}]}
              value={tweaks.tweaks.background}
              onChange={(v) => tweaks.setTweak('background', v)}/>
            <window.TweakRadio label="밀도"
              options={[{value:'comfortable',label:'Comfort'},{value:'compact',label:'Compact'}]}
              value={tweaks.tweaks.density}
              onChange={(v) => tweaks.setTweak('density', v)}/>
          </window.TweakSection>
          <window.TweakSection title="네비게이션">
            <div className="text-[11.5px] text-zinc-500 leading-relaxed">
              사이드바에서 화면을 전환하거나 강의를 클릭해 상세 페이지를 확인하세요.<br/>
              <span className="mono text-zinc-700">대시보드 · 캘린더 · 학습 비서 · 커넥터</span>
            </div>
          </window.TweakSection>
        </window.TweaksPanel>
      )}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
