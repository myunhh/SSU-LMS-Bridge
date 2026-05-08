import { useState, useEffect, createContext, useContext } from 'react';
import { Routes, Route, Navigate, Outlet, useNavigate, useLocation, useParams } from 'react-router-dom';
import { Sidebar, Topbar } from './pages/sidebar';
import { Dashboard } from './pages/dashboard';
import { CourseDetail } from './pages/course-detail';
import { ChatView } from './pages/chat';
import { ConnectorsView } from './pages/connectors';
import { CalendarView } from './pages/calendar';
import { SettingsView } from './pages/settings';
import LandingPage from './pages/landing';
import LoginPage from './pages/login';
import SignupPage from './pages/signup';
import Icon from './pages/icons';
import { COURSES } from './pages/data';

// ── Auth context ─────────────────────────────────────────────────
const AuthContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}

function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const saved = localStorage.getItem('ssu_user');
      return saved ? JSON.parse(saved) : null;
    } catch { return null; }
  });

  const login = (studentId) => {
    const u = { studentId };
    localStorage.setItem('ssu_user', JSON.stringify(u));
    setUser(u);
  };

  const logout = () => {
    localStorage.removeItem('ssu_user');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
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
  const navigate = useNavigate();
  const location = useLocation();
  const [tweaks] = useState(TWEAK_DEFAULTS);

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

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  const pathParts = location.pathname.split('/').filter(Boolean);
  const route = pathParts[0] || 'dashboard';
  const courseId = route === 'course' ? Number(pathParts[1]) || 3 : 3;

  const setRoute = (r) => { if (r !== 'course') navigate(`/${r}`); };
  const setCourse = (id) => navigate(`/course/${id}`);

  const titles = {
    dashboard:  { t: '대시보드',     s: '2026년 1학기 · 11주차' },
    calendar:   { t: '캘린더',       s: '과제 마감 · 공지 · 학사 이벤트' },
    chat:       { t: '학습 비서',    s: 'RAG · 강의자료 컨텍스트 활성' },
    connectors: { t: '커넥터',       s: 'LMS · Notion · Obsidian · LLM' },
    settings:   { t: '설정',         s: '계정 · 알림 · 동기화 · 외관' },
    course:     null,
  };

  const cur = titles[route];
  const c = COURSES.find(x => x.id === courseId);
  const top = cur || { t: c.name, s: `${c.code} · ${c.professor} 교수 · ${c.credits}학점` };

  return (
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
              <button className="h-8 px-2.5 rounded-md border border-[var(--line)] bg-white text-[12px] flex items-center gap-1.5 hover:bg-zinc-50">
                <Icon.Sync size={13} /> 동기화
              </button>
              <button className="h-8 px-2.5 rounded-md border border-[var(--line)] bg-white text-[12px] flex items-center gap-1.5 hover:bg-zinc-50">
                <Icon.External size={13} /> LMS
              </button>
            </>
          }
        />
        <div className="flex-1 overflow-y-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

// ── Route helpers ─────────────────────────────────────────────────
function DashboardRoute() {
  const navigate = useNavigate();
  return (
    <Dashboard
      openCourse={(id) => navigate(`/course/${id}`)}
      openChat={() => navigate('/chat')}
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
        <Route path="/calendar" element={<CalendarView />} />
        <Route path="/settings" element={<SettingsView />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}
