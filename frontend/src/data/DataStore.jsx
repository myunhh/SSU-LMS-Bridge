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
import { createContext, useContext, useState, useCallback, useEffect, useMemo } from 'react';
import * as seed from './mockData';
import * as LmsAuthApi from '../api/lmsAuth';
import * as Api from '../api/index';
import { getLmsCredentials } from '../auth/AccountStore';

// 백엔드가 errors 배열에 담아 보낸 메시지가 LMS 인증 실패인지 판별.
// (HTTPStatusError → 401/403/419 가 라우트에서 401 로 변환되거나 errors 문자열에 401 포함)
function _isAuthError(errors) {
  if (!errors?.length) return false;
  return errors.some(e => /401|403|419|unauthor|세션/i.test(String(e)));
}

const DataContext = createContext(null);

// ── 표시용 헬퍼 ────────────────────────────────────────────────
function _relTime(iso, now = new Date()) {
  if (!iso) return '';
  const ms = now - new Date(iso);
  if (ms < 0) return '예정';
  if (ms < 60_000) return '방금';
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}분 전`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}시간 전`;
  return `${Math.floor(ms / 86_400_000)}일 전`;
}
function _fmtShort(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

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
  // 초기값은 seed — 백엔드에서 받아오면 useEffect 가 덮어쓴다.
  const [courses,       setCourses]       = useState(seed.COURSES);
  const [assignments,   setAssignments]   = useState(seed.ASSIGNMENTS);
  const [notices,       setNotices]       = useState(seed.NOTICES);
  // 알림은 공지/과제에서 파생 (아래 useMemo). 활동·대화는 실제 동작으로 채워지도록 비움.
  const [activity,      setActivity]      = useState([]);
  const [conversations, setConversations] = useState([]);
  const [chatSeed,      setChatSeed]      = useState([]);
  const [connectors,    setConnectors]    = useState(seed.CONNECTORS);

  // 데이터 로딩 상태 — 초기 fetch / refetch 중일 때 true
  const [loading, setLoading] = useState(false);

  // 동기화 진행 상태 (Topbar 버튼이 사용)
  const [syncing, setSyncing] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState(null);

  // ── LMS 세션 상태 ────────────────────────────────────────────────────────
  // { active, userInfo, savedAt, nextRefreshIn } | null
  const [lmsSession, setLmsSession] = useState(null);
  const [lmsBusy, setLmsBusy] = useState(false);   // 로그인 / 갱신 중

  // 앱 시작 시 한 번 세션 상태 조회.
  // 데이터 fetch 는 아래 effect 가 lmsSession.active 가 true 가 된 시점에 수행.
  // (세션이 없는 가입 화면에서 503 토스트가 뜨지 않도록 분리)
  useEffect(() => {
    LmsAuthApi.getLmsSessionStatus().then(s => setLmsSession(s));
    // 마지막 동기화 시각도 백엔드에서 받아오면 페이지 새로고침 후에도 보존된다.
    Api.fetchSyncStatus()
      .then(s => { if (s?.lastSyncAt) setLastSyncAt(new Date(s.lastSyncAt)); })
      .catch(() => { /* 백엔드 미기동 — 무시 */ });
  }, []);

  // LMS 세션이 활성화되면 (= 가입 후 loginLms 성공, 또는 앱 재시작 후 캐시 유효) 데이터 fetch.
  useEffect(() => {
    if (!lmsSession?.active) return;
    setLoading(true);
    Api.fetchInitialBundle()
      .then(({ courses, assignments, notices }) => {
        if (courses?.length)     setCourses(courses);
        if (assignments?.length) setAssignments(assignments);
        if (notices?.length)     setNotices(notices);
      })
      .catch(err => {
        console.warn('[DataStore] 데이터 로드 실패:', err);
        onToast?.({ kind: 'error', text: '데이터 로드에 실패했습니다.' });
      })
      .finally(() => setLoading(false));
  // savedAt 변화는 무시 — 같은 세션 갱신엔 refetch 불필요
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lmsSession?.active]);

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
  // 액션: 동기화
  // mock 모드면 1.5초 대기 후 ACTIVITY만 갱신, 실 모드면 POST /api/sync 호출 후
  // courses/notices/assignments 를 refetch 한다.
  // ──────────────────────────────────────────────────────────────────────────
  const triggerSync = useCallback(async () => {
    if (syncing) return;
    setSyncing(true);
    onToast?.({ kind: 'info', text: '동기화를 시작했습니다…' });
    try {
      let result = await Api.triggerSync();

      // Canvas 쿠키 만료 등으로 sync 가 401 류 오류를 돌려준 경우,
      // 저장된 LMS 자격증명으로 자동 재로그인 후 1회 재시도.
      // (load_session 은 lms.ssu.ac.kr 만 갱신하므로 Canvas 만료엔 무력)
      if (_isAuthError(result.errors)) {
        const creds = getLmsCredentials();
        if (creds?.id && creds?.password) {
          onToast?.({ kind: 'info', text: 'LMS 세션 만료 — 자동 재로그인 중…' });
          const r = await LmsAuthApi.lmsLogin(creds.id, creds.password);
          if (r.ok) {
            setLmsSession({ active: true, userInfo: r.userInfo, savedAt: r.savedAt });
            result = await Api.triggerSync();
          } else {
            onToast?.({ kind: 'error', text: r.error || '자동 재로그인 실패 — Connectors 페이지에서 다시 시도해주세요.' });
          }
        } else {
          onToast?.({ kind: 'error', text: 'LMS 세션이 만료됐고 저장된 비밀번호가 없습니다. Connectors 에서 재로그인 해주세요.' });
        }
      }

      // 동기화 후 데이터 새로고침 (성공/부분실패 모두 시도 — 일부라도 들어왔을 수 있음)
      try {
        const { courses: nc, assignments: na, notices: nn } = await Api.fetchInitialBundle();
        if (nc?.length) setCourses(nc);
        if (na?.length) setAssignments(na);
        if (nn?.length) setNotices(nn);
      } catch (e) {
        console.warn('[DataStore] 동기화 후 refetch 실패:', e);
      }

      const summary = [
        `${result.courses}개 강의`,
        result.notices ? `공지 ${result.notices}건` : null,
        result.assignments ? `과제 ${result.assignments}건` : null,
        result.materials ? `자료 ${result.materials}건` : null,
      ].filter(Boolean).join(' · ');

      setActivity(act => [
        { t: '방금 전', text: '수동 동기화 완료', kind: 'sync', meta: summary || `${courses.length}개 강의 · 0건 변경` },
        ...act,
      ]);
      setLastSyncAt(new Date(result.syncedAt || Date.now()));

      if (result.errors?.length) {
        onToast?.({ kind: 'error', text: `동기화 완료 — 일부 항목 실패 (${result.errors.length}건)` });
      } else {
        onToast?.({ kind: 'success', text: '동기화 완료 ✓' });
      }
    } catch (e) {
      console.error('[DataStore] triggerSync 실패:', e);
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

  /** 세션 즉시 갱신 (사용자가 "재발급" 버튼 클릭).
   * 저장된 LMS 자격증명이 있으면 full Playwright 재로그인 (Canvas 쿠키까지 갱신).
   * 없으면 metadata refresh (load_session) 만. */
  const refreshLms = useCallback(async () => {
    setLmsBusy(true);
    try {
      const creds = getLmsCredentials();
      if (creds?.id && creds?.password) {
        // full SSO 재로그인 — Canvas 쿠키 만료 케이스까지 해결
        const r = await LmsAuthApi.lmsLogin(creds.id, creds.password);
        if (r.ok) {
          setLmsSession({ active: true, userInfo: r.userInfo, savedAt: r.savedAt });
          setActivity(act => [
            { t: '방금 전', text: 'LMS 재로그인 — 세션 재발급', kind: 'auth', meta: '저장된 자격증명 사용' },
            ...act,
          ]);
          onToast?.({ kind: 'success', text: 'LMS 세션을 재발급했습니다.' });
          return { ok: true, savedAt: r.savedAt };
        }
        onToast?.({ kind: 'error', text: r.error || '재로그인 실패 — 비밀번호를 확인해주세요.' });
        return r;
      }

      // 자격증명 없음 — 기존 metadata refresh
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
  // 파생: 강의 지표 보강 (실제 공지/과제 기반)
  //   unread  = 해당 강의 미열람 공지 수
  //   dueSoon = 해당 강의 7일 내 미제출 과제 수
  //   (progress/materials/weekCurrent 는 백엔드/추가 fetch 필요 → 기본값 유지)
  // ──────────────────────────────────────────────────────────────────────────
  const coursesEnriched = useMemo(() => {
    const weekMs = 7 * 86400000;
    return courses.map(c => {
      const unread = notices.filter(n => n.course === c.id && n.unread).length;
      const dueSoon = assignments.filter(a => {
        if (a.course !== c.id || a.submitted || !a.due) return false;
        const diff = new Date(a.due) - now;
        return diff >= 0 && diff <= weekMs;
      }).length;
      return { ...c, unread, dueSoon };
    });
  }, [courses, notices, assignments, now]);

  // ──────────────────────────────────────────────────────────────────────────
  // 파생: 알림 (마감임박 과제 + 미열람 공지)
  // ──────────────────────────────────────────────────────────────────────────
  const notifications = useMemo(() => {
    const weekMs = 7 * 86400000;
    const courseOf = (id) => coursesEnriched.find(c => c.id === id);
    const out = [];

    // 마감 임박 (미제출, 7일 내) — 가까운 순
    assignments
      .filter(a => !a.submitted && a.due && (new Date(a.due) - now) >= 0 && (new Date(a.due) - now) <= weekMs)
      .sort((x, y) => new Date(x.due) - new Date(y.due))
      .forEach(a => {
        const c = courseOf(a.course);
        const days = Math.floor((new Date(a.due) - now) / 86400000);
        out.push({
          id: `assign-${a.id}`, kind: 'deadline',
          course: c?.name || '', courseColor: c?.color || 'var(--muted)',
          title: a.title,
          body: `${_fmtShort(a.due)} 마감${days === 0 ? ' · 오늘' : ` · D-${days}`}`,
          time: _relTime(a.due, now), unread: true,
        });
      });

    // 미열람 공지 — 최신 순
    notices
      .filter(n => n.unread)
      .sort((x, y) => new Date(y.date) - new Date(x.date))
      .forEach(n => {
        const c = courseOf(n.course);
        out.push({
          id: `notice-${n.id}`, kind: 'notice',
          course: c?.name || '', courseColor: c?.color || 'var(--muted)',
          title: n.title, body: n.snippet || '',
          time: _relTime(n.date, now), unread: true,
        });
      });

    return out;
  }, [assignments, notices, coursesEnriched, now]);

  // 알림 읽음 — 공지 알림은 원본 공지를 읽음 처리, 마감 알림은 dismiss 개념 없음
  const markNotificationRead = useCallback((id) => {
    if (typeof id === 'string' && id.startsWith('notice-')) {
      markNoticeRead(Number(id.slice('notice-'.length)));
    }
  }, [markNoticeRead]);

  const markAllNotificationsRead = useCallback(() => {
    markAllNoticesRead();
  }, [markAllNoticesRead]);

  // ──────────────────────────────────────────────────────────────────────────
  // 파생 헬퍼 (selector 패턴)
  // ──────────────────────────────────────────────────────────────────────────
  const getCourseById   = useCallback((id) => coursesEnriched.find(c => c.id === id), [coursesEnriched]);
  const getAssignmentsByCourse = useCallback((cid) => assignments.filter(a => a.course === cid), [assignments]);
  const getNoticesByCourse     = useCallback((cid) => notices.filter(n => n.course === cid),     [notices]);
  const getModulesByCourse     = useCallback((cid) => modules[cid] || modules[3] || [],          [modules]);

  const value = {
    // 정적 데이터
    user, semester, now, suggestions, calendar,
    // 동적 데이터 (courses 는 unread/dueSoon 보강본)
    courses: coursesEnriched, assignments, notices, notifications, activity,
    conversations, chatSeed, connectors,
    // 로딩 / 동기화 상태
    loading, syncing, lastSyncAt,
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
