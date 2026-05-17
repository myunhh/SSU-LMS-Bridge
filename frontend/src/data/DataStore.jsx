// src/data/DataStore.jsx
// ──────────────────────────────────────────────────────────────────────────────
// 앱의 모든 "동적 데이터"를 한 곳에서 관리한다.
//
// 지금은 mockData.js 의 초기값(seed) 을 useState 로 감싸기만 한 상태.
// 모든 페이지는 `useData()` 훅으로 데이터와 액션 함수를 받는다.
//
// 나중에 백엔드 연결할 때:
//   - 각 액션 함수의 setState(...) 부분을 fetch(...) 호출로 교체
//   - 초기 로드는 useEffect 안에서 GET 요청
//   - 페이지 코드는 한 줄도 바꿀 필요 없음 (인터페이스 동일)
// ──────────────────────────────────────────────────────────────────────────────
import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import * as seed from './mockData';
import * as LmsAuthApi from '../api/lmsAuth';

const DataContext = createContext(null);

// ── 훅 ────────────────────────────────────────────────────────────────────────
export function useData() {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error('useData() 는 <DataProvider> 안에서만 사용 가능합니다.');
  return ctx;
}

// ── Provider ──────────────────────────────────────────────────────────────────
// authUser: AuthProvider 의 user 객체. 있으면 그것을 사용, 없으면 mockData.USER fallback.
export function DataProvider({ children, onToast, authUser }) {
  // 정적인 것들 (구조상 거의 변하지 않음)
  const user      = authUser || seed.USER;
  const semester  = seed.SEMESTER;
  const now       = seed.NOW;
  const modules   = seed.MODULES;
  const calendar  = { month: seed.CALENDAR_MONTH, events: seed.CALENDAR_EVENTS };
  const suggestions = seed.SUGGESTIONS;

  // 변할 수 있는 것들 (사용자 인터랙션으로 갱신됨)
  const [courses,       setCourses]       = useState(seed.COURSES);
  const [assignments,   setAssignments]   = useState(seed.ASSIGNMENTS);
  const [notices,       setNotices]       = useState(seed.NOTICES);
  const [notifications, setNotifications] = useState(seed.NOTIFICATIONS);
  const [activity,      setActivity]      = useState(seed.ACTIVITY);
  const [conversations, setConversations] = useState(seed.CONVERSATIONS);
  const [chatSeed,      setChatSeed]      = useState(seed.CHAT_SEED);
  const [connectors,    setConnectors]    = useState(seed.CONNECTORS);

  // 동기화 진행 상태 (Topbar 버튼이 사용)
  const [syncing, setSyncing] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState(null);

  // ── LMS 세션 상태 ────────────────────────────────────────────────────────
  // { active, userInfo, savedAt, nextRefreshIn } | null
  const [lmsSession, setLmsSession] = useState(null);
  const [lmsBusy, setLmsBusy] = useState(false);   // 로그인 / 갱신 중

  // 앱 시작 시 한 번 세션 상태 조회
  useEffect(() => {
    LmsAuthApi.getLmsSessionStatus().then(s => setLmsSession(s));
  }, []);

  // ──────────────────────────────────────────────────────────────────────────
  // 액션: 알림
  // ──────────────────────────────────────────────────────────────────────────
  const markNotificationRead = useCallback((id) => {
    setNotifications(ns => ns.map(n => n.id === id ? { ...n, unread: false } : n));
  }, []);

  const markAllNotificationsRead = useCallback(() => {
    setNotifications(ns => ns.map(n => ({ ...n, unread: false })));
    onToast?.({ kind: 'success', text: '모든 알림을 읽음으로 표시했습니다.' });
  }, [onToast]);

  // ──────────────────────────────────────────────────────────────────────────
  // 액션: 공지
  // ──────────────────────────────────────────────────────────────────────────
  const markNoticeRead = useCallback((id) => {
    setNotices(ns => ns.map(n => n.id === id ? { ...n, unread: false } : n));
  }, []);

  const markAllNoticesRead = useCallback(() => {
    setNotices(ns => ns.map(n => ({ ...n, unread: false })));
    onToast?.({ kind: 'success', text: '모든 공지를 읽음으로 표시했습니다.' });
  }, [onToast]);

  // ──────────────────────────────────────────────────────────────────────────
  // 액션: 과제
  // ──────────────────────────────────────────────────────────────────────────
  const toggleAssignmentSubmit = useCallback((id) => {
    setAssignments(as => as.map(a => {
      if (a.id !== id) return a;
      const next = !a.submitted;
      onToast?.({
        kind: next ? 'success' : 'info',
        text: next ? `"${a.title}" 제출 완료로 표시했습니다.` : `"${a.title}" 제출 취소했습니다.`,
      });
      return { ...a, submitted: next };
    }));
  }, [onToast]);

  // ──────────────────────────────────────────────────────────────────────────
  // 액션: 동기화 (지금은 fake — 1.5초 대기 후 ACTIVITY 갱신)
  // 백엔드 연결 시 fetch('/api/sync', {method:'POST'}) 로 교체
  // ──────────────────────────────────────────────────────────────────────────
  const triggerSync = useCallback(async () => {
    if (syncing) return;
    setSyncing(true);
    onToast?.({ kind: 'info', text: '동기화를 시작했습니다…' });
    try {
      await new Promise(r => setTimeout(r, 1500));
      setActivity(act => [
        { t: '방금 전', text: '수동 동기화 완료', kind: 'sync', meta: `${courses.length}개 강의 · 0건 변경` },
        ...act,
      ]);
      setLastSyncAt(new Date());
      onToast?.({ kind: 'success', text: '동기화 완료 ✓' });
    } catch (e) {
      onToast?.({ kind: 'error', text: '동기화에 실패했습니다.' });
    } finally {
      setSyncing(false);
    }
  }, [syncing, courses.length, onToast]);

  // ──────────────────────────────────────────────────────────────────────────
  // 액션: LMS 세션 (Playwright SSO)
  // ──────────────────────────────────────────────────────────────────────────

  /** LMS 신규 로그인 (학번 + 비번). 회원가입 / Connectors 페이지에서 호출 */
  const loginLms = useCallback(async (studentId, password) => {
    setLmsBusy(true);
    try {
      const res = await LmsAuthApi.lmsLogin(studentId, password);
      if (res.ok) {
        setLmsSession({
          active: true,
          userInfo: res.userInfo,
          savedAt: res.savedAt,
        });
        setActivity(act => [
          { t: '방금 전', text: 'LMS 로그인 성공', kind: 'auth', meta: `학번 ${studentId}` },
          ...act,
        ]);
        onToast?.({ kind: 'success', text: 'LMS 세션이 발급되었습니다.' });
      } else {
        onToast?.({ kind: 'error', text: res.error || 'LMS 로그인 실패' });
      }
      return res;
    } finally {
      setLmsBusy(false);
    }
  }, [onToast]);

  /** 세션 즉시 갱신 (사용자가 "재발급" 버튼 클릭) */
  const refreshLms = useCallback(async () => {
    setLmsBusy(true);
    try {
      const res = await LmsAuthApi.refreshLmsSession();
      if (res.ok) {
        setLmsSession(s => s ? { ...s, savedAt: res.savedAt } : s);
        setActivity(act => [
          { t: '방금 전', text: '세션 갱신 — 쿠키 재발급', kind: 'auth', meta: 'load_session() · 0.5s' },
          ...act,
        ]);
        onToast?.({ kind: 'success', text: 'LMS 세션을 갱신했습니다.' });
      } else {
        onToast?.({ kind: 'error', text: res.error || '갱신 실패' });
      }
      return res;
    } finally {
      setLmsBusy(false);
    }
  }, [onToast]);

  /** 세션 메타 다시 조회 (다른 탭이 갱신한 경우 등) */
  const reloadLmsSession = useCallback(async () => {
    const s = await LmsAuthApi.getLmsSessionStatus();
    setLmsSession(s);
    return s;
  }, []);

  /** LMS 세션만 끊기 (회원 로그아웃과 별개) */
  const clearLms = useCallback(async () => {
    await LmsAuthApi.clearLmsSession();
    setLmsSession({ active: false });
    onToast?.({ kind: 'info', text: 'LMS 세션을 끊었습니다.' });
  }, [onToast]);

  // ──────────────────────────────────────────────────────────────────────────
  // 액션: 채팅
  // ──────────────────────────────────────────────────────────────────────────
  const appendChatMessage = useCallback((msg) => {
    setChatSeed(m => [...m, msg]);
  }, []);

  const startNewConversation = useCallback(() => {
    const id = `c${Date.now()}`;
    setConversations(cs => [
      { id, title: '새 대화', sub: '방금', active: true },
      ...cs.map(c => ({ ...c, active: false })),
    ]);
    setChatSeed([]);
    onToast?.({ kind: 'info', text: '새 대화를 시작했습니다.' });
  }, [onToast]);

  const selectConversation = useCallback((id) => {
    setConversations(cs => cs.map(c => ({ ...c, active: c.id === id })));
  }, []);

  // ──────────────────────────────────────────────────────────────────────────
  // 액션: 커넥터 (재연결/해제 토글)
  // ──────────────────────────────────────────────────────────────────────────
  const toggleConnector = useCallback((id) => {
    setConnectors(cs => cs.map(c => {
      if (c.id !== id) return c;
      const next = c.status === 'connected' ? 'disconnected' : 'connected';
      onToast?.({
        kind: 'info',
        text: `${c.name} ${next === 'connected' ? '연결되었습니다.' : '연결을 해제했습니다.'}`,
      });
      return { ...c, status: next, last: next === 'connected' ? '방금 전' : '—' };
    }));
  }, [onToast]);

  // ──────────────────────────────────────────────────────────────────────────
  // 파생 헬퍼 (selector 패턴)
  // ──────────────────────────────────────────────────────────────────────────
  const getCourseById   = useCallback((id) => courses.find(c => c.id === id),     [courses]);
  const getAssignmentsByCourse = useCallback((cid) => assignments.filter(a => a.course === cid), [assignments]);
  const getNoticesByCourse     = useCallback((cid) => notices.filter(n => n.course === cid),     [notices]);
  const getModulesByCourse     = useCallback((cid) => modules[cid] || modules[3] || [],          [modules]);

  const value = {
    // 정적 데이터
    user, semester, now, suggestions, calendar,
    // 동적 데이터
    courses, assignments, notices, notifications, activity,
    conversations, chatSeed, connectors,
    // 동기화 상태
    syncing, lastSyncAt,
    // LMS 세션 상태 + 액션
    lmsSession, lmsBusy,
    loginLms, refreshLms, reloadLmsSession, clearLms,
    // 액션
    markNotificationRead, markAllNotificationsRead,
    markNoticeRead, markAllNoticesRead,
    toggleAssignmentSubmit,
    triggerSync,
    appendChatMessage, startNewConversation, selectConversation,
    toggleConnector,
    // 셀렉터
    getCourseById, getAssignmentsByCourse, getNoticesByCourse, getModulesByCourse,
  };

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}
