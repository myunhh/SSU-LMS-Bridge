import { useState, useEffect, useRef, createContext, useContext } from 'react';
import { Routes, Route, Navigate, Outlet, useNavigate, useLocation, useParams } from 'react-router-dom';
import { Sidebar, Topbar } from './pages/sidebar';
import { Dashboard } from './pages/dashboard';
import { CourseDetail } from './pages/course-detail';
import { ChatView } from './pages/chat';
import { ConnectorsView } from './pages/connectors';
import { McpView } from './pages/mcp';
import { CalendarView } from './pages/calendar';
import { SettingsView } from './pages/settings';
import LandingPage from './pages/landing';
import LoginPage from './pages/login';
import SignupPage from './pages/signup';
import NotFoundPage from './pages/not-found';
import Icon from './pages/icons';
import { PAGE_TITLES, renderTitle } from './data/uiConfig';
import { DataProvider, useData } from './data/DataStore';
import { ToastProvider, useToast } from './components/Toast';
import ErrorBoundary from './components/ErrorBoundary';
import * as AccountStore from './auth/AccountStore';

// ── Auth context ─────────────────────────────────────────────────
// user 객체: { name, studentId, email, major, hasLms, hasNotion, ... } | null
//   가입 후 stripSecrets 된 형태로 들어온다 (비밀번호 해시 / 토큰 제외)
const AuthContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}

// ── Tweaks context (외관 설정: 액센트/배경 톤) ────────────────────
// localStorage 'ssu_tweaks' 에 영속. settings 외관 섹션이 useTweaks 로 변경.
const TweaksContext = createContext(null);

export function useTweaks() {
  return useContext(TweaksContext);
}

function AuthProvider({ children }) {
  // 초기값: AccountStore 에서 동기적으로 현재 세션 확인.
  // (localStorage 는 동기 — 새로고침해도 로그인 유지)
  // stripSecrets / 레거시 시크릿 마이그레이션을 AccountStore 한 곳에서 처리하므로
  // 여기서 로직을 중복 구현하지 않는다.
  const [user, setUser] = useState(() => {
    try { return AccountStore.getCurrentUserSync(); } catch { return null; }
  });

  /**
   * 학번 + 비밀번호로 로그인.
   * @returns {Promise<{ ok: boolean, error?: string }>}
   */
  const login = async (studentId, password) => {
    const res = await AccountStore.login(studentId, password);
    if (res.ok) setUser(res.user);
    return res;
  };

  /**
   * 회원가입 + 자동 로그인.
   * @returns {Promise<{ ok: boolean, error?: string }>}
   */
  const signup = async (formData) => {
    const res = await AccountStore.signup(formData);
    if (res.ok) setUser(res.user);
    return res;
  };

  const logout = async () => {
    await AccountStore.logout();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// ── App layout (protected) ────────────────────────────────────────
const TWEAK_DEFAULTS = {
  accent: '#3a4ca8',
  density: 'comfortable',
  background: 'warm',
};

function AppLayout() {
  const { user, logout } = useAuth();
  const data = useData();
  const navigate = useNavigate();
  const location = useLocation();
  // 외관 설정 — localStorage 'ssu_tweaks' 에서 lazy 초기화 (DataStore 오버레이와 동일 try/catch).
  const [tweaks, setTweaks] = useState(() => {
    try { return { ...TWEAK_DEFAULTS, ...JSON.parse(localStorage.getItem('ssu_tweaks') || '{}') }; }
    catch { return TWEAK_DEFAULTS; }
  });
  const updateTweaks = (patch) => {
    setTweaks(prev => {
      const next = { ...prev, ...patch };
      try { localStorage.setItem('ssu_tweaks', JSON.stringify(next)); } catch { /* noop */ }
      return next;
    });
  };

  useEffect(() => {
    const t = tweaks;
    document.documentElement.style.setProperty('--accent', t.accent);
    document.documentElement.style.setProperty('--accent-soft',
      `color-mix(in oklch, ${t.accent} 12%, white)`);
    const bg = t.background === 'cool' ? '#f4f5f8'
             : t.background === 'mono' ? '#f5f5f5'
             : '#f7f6f3';
    document.documentElement.style.setProperty('--bg', bg);
    document.documentElement.style.setProperty('--line', t.background === 'mono' ? '#e4e4e7' : '#e7e5e0');
    document.documentElement.style.setProperty('--line-2', t.background === 'mono' ? '#ededed' : '#efece6');
  }, [tweaks]);

  // ── 전역 키보드 단축키 ────────────────────────────────────────
  // 설정 → 단축키 표(settings.jsx)에 문서화된 동작을 실제로 구현한다.
  const gChordRef = useRef(0);
  useEffect(() => {
    const onKey = (e) => {
      const el = e.target;
      const typing = el && (
        el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' ||
        el.tagName === 'SELECT' || el.isContentEditable
      );
      const mod = e.metaKey || e.ctrlKey;

      // ⌘K / Ctrl+K — 검색 포커스 (입력 중에도 동작, 관례)
      if (mod && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        document.getElementById('ssu-global-search')?.focus();
        return;
      }
      // ⌘R / Ctrl+R (Shift 없음) — 동기화 실행. ⌘⇧R 은 가로채지 않아 새로고침 탈출구 유지.
      if (mod && !e.shiftKey && (e.key === 'r' || e.key === 'R')) {
        e.preventDefault();
        if (!data.syncing) data.triggerSync();
        return;
      }

      if (typing || mod) return;  // 아래는 입력 중·수식키 동반 시 무시

      // ',' — 설정 열기
      if (e.key === ',') { e.preventDefault(); navigate('/settings'); return; }

      // G-chord — g 입력 후 1.5초 내 d/c/a/s 로 이동
      if (e.key === 'g' || e.key === 'G') { gChordRef.current = Date.now(); return; }
      if (Date.now() - gChordRef.current < 1500) {
        const dest = { d: '/dashboard', c: '/calendar', a: '/chat', s: '/connectors' }[e.key.toLowerCase()];
        if (dest) { e.preventDefault(); gChordRef.current = 0; navigate(dest); }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [navigate, data]);

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  const pathParts = location.pathname.split('/').filter(Boolean);
  const route = pathParts[0] || 'dashboard';
  const courseId = route === 'course' ? Number(pathParts[1]) || 3 : 3;

  const setRoute = (r) => { if (r !== 'course') navigate(`/${r}`); };
  const setCourse = (id) => navigate(`/course/${id}`);

  // PAGE_TITLES 의 부제(s)에 {{semester.*}} 같은 토큰이 들어있을 수 있어 renderTitle 로 치환
  const cur = PAGE_TITLES[route]
    ? { t: PAGE_TITLES[route].t, s: renderTitle(PAGE_TITLES[route].s, { semester: data.semester }) }
    : null;
  const c = data.getCourseById(courseId);
  const top = cur || (c ? { t: c.name, s: `${c.code} · ${c.professor} 교수 · ${c.credits}학점` } : { t: '강의', s: '' });

  return (
    <TweaksContext.Provider value={{ tweaks, updateTweaks }}>
    <div className="h-screen flex bg-[var(--bg)] overflow-hidden">
      <Sidebar
        route={route}
        setRoute={setRoute}
        currentCourse={courseId}
        setCourse={setCourse}
        user={user}
        onLogout={() => { logout(); navigate('/'); }}
      />
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Topbar
          title={top.t}
          sub={top.s}
          right={
            <>
              <button
                onClick={data.triggerSync}
                disabled={data.syncing}
                className="h-8 px-2.5 rounded-md border border-[var(--line)] bg-white text-[12px] flex items-center gap-1.5 hover:bg-zinc-50 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <Icon.Sync size={13} className={data.syncing ? 'animate-spin' : ''} />
                {data.syncing ? '동기화 중…' : '동기화'}
              </button>
              <a
                href="https://lms.ssu.ac.kr"
                target="_blank"
                rel="noopener noreferrer"
                className="h-8 px-2.5 rounded-md border border-[var(--line)] bg-white text-[12px] flex items-center gap-1.5 hover:bg-zinc-50"
              >
                <Icon.External size={13} /> LMS
              </a>
            </>
          }
        />
        <div className="flex-1 overflow-y-auto">
          <Outlet />
        </div>
      </main>
    </div>
    </TweaksContext.Provider>
  );
}

// ── Route helpers ─────────────────────────────────────────────────
function DashboardRoute() {
  const navigate = useNavigate();
  return (
    <Dashboard
      openCourse={(id) => navigate(`/course/${id}`)}
      openChat={() => navigate('/chat')}
      openCalendar={() => navigate('/calendar')}
    />
  );
}

function CourseDetailRoute() {
  const { id } = useParams();
  const navigate = useNavigate();
  return <CourseDetail courseId={Number(id)} openChat={() => navigate('/chat')} />;
}

// ── Routes ────────────────────────────────────────────────────────
function AppRoutes() {
  const { user } = useAuth();

  return (
    <Routes>
      {/* Public */}
      <Route path="/" element={user ? <Navigate to="/dashboard" replace /> : <LandingPage />} />
      <Route path="/login" element={user ? <Navigate to="/dashboard" replace /> : <LoginPage />} />
      <Route path="/signup" element={user ? <Navigate to="/dashboard" replace /> : <SignupPage />} />

      {/* Protected — AppLayout checks auth and renders <Outlet> */}
      <Route element={<AppLayout />}>
        <Route path="/dashboard" element={<DashboardRoute />} />
        <Route path="/course/:id" element={<CourseDetailRoute />} />
        <Route path="/chat" element={<ChatView />} />
        <Route path="/connectors" element={<ConnectorsView />} />
        <Route path="/mcp" element={<McpView />} />
        <Route path="/calendar" element={<CalendarView />} />
        <Route path="/settings" element={<SettingsView />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

// AuthProvider 의 user 와 ToastProvider 의 toast 를 모두 DataProvider 에 전달.
// → AuthProvider 가 가장 바깥, ToastProvider 가 그 다음, 그 안에서 DataProvider 생성.
function DataWithDeps({ children }) {
  const toast = useToast();
  const { user } = useAuth();
  return <DataProvider onToast={toast} authUser={user}>{children}</DataProvider>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <ToastProvider>
          <DataWithDeps>
            <AppRoutes />
          </DataWithDeps>
        </ToastProvider>
      </AuthProvider>
    </ErrorBoundary>
  );
}
