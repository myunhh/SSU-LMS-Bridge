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

// 어떤 값이든 LMS 인증 실패(세션 만료) 신호인지 판별.
// 두 경로를 모두 잡는다:
//   1) 백엔드가 errors 배열에 담아 보낸 부분 실패 (sync 결과 등)
//   2) request 헬퍼가 throw 한 에러 — err.status(401/403/419) + 메시지 문자열
// (HTTPStatusError → 401/403/419 가 라우트에서 401 로 변환되거나 errors 문자열에 401 포함)
function _isAuthError(input) {
  if (!input) return false;
  // 배열(errors) — 각 항목을 문자열로 검사
  if (Array.isArray(input)) {
    return input.some(e => _isAuthError(e));
  }
  // throw 된 에러 객체 — status 코드 우선, 없으면 message 문자열
  if (typeof input === 'object') {
    if (input.status === 401 || input.status === 403 || input.status === 419) return true;
    return /401|403|419|unauthor|세션/i.test(String(input.message ?? input));
  }
  return /401|403|419|unauthor|세션/i.test(String(input));
}

// ── 읽음/제출 오버레이 (#35) ──────────────────────────────────────────────────
// 공지 읽음·과제 제출 토글은 백엔드(Canvas)에 쓸 수 없으므로 localStorage 에
// 사용자별로 영속화하고, fetch/refetch 결과 위에 병합한다.
//   키:  "ssu_overrides:{studentId}"  (studentId 는 'ssu_session', 없으면 'anon')
//   값:  { noticesRead: { [id]: true }, assignmentsSubmitted: { [id]: true|false } }
//   병합: 공지 unread = (백엔드 unread) && !noticesRead[id]
//         과제 submitted = assignmentsSubmitted[id] ?? (백엔드 submitted)
function _overridesKey() {
  let sid = null;
  try { sid = localStorage.getItem('ssu_session'); } catch { /* noop */ }
  return `ssu_overrides:${sid || 'anon'}`;
}
function _readOverrides() {
  try {
    const raw = localStorage.getItem(_overridesKey());
    const o = raw ? JSON.parse(raw) : {};
    return {
      noticesRead: o.noticesRead || {},
      assignmentsSubmitted: o.assignmentsSubmitted || {},
    };
  } catch {
    return { noticesRead: {}, assignmentsSubmitted: {} };
  }
}
function _writeOverrides(patch) {
  const cur = _readOverrides();
  const next = {
    noticesRead: { ...cur.noticesRead, ...(patch.noticesRead || {}) },
    assignmentsSubmitted: { ...cur.assignmentsSubmitted, ...(patch.assignmentsSubmitted || {}) },
  };
  try { localStorage.setItem(_overridesKey(), JSON.stringify(next)); } catch { /* 저장 실패 무시 */ }
}
function _overlayNotices(list) {
  const read = _readOverrides().noticesRead;
  return list.map(n => (read[n.id] ? { ...n, unread: false } : n));
}
function _overlayAssignments(list) {
  const sub = _readOverrides().assignmentsSubmitted;
  return list.map(a => (a.id in sub ? { ...a, submitted: !!sub[a.id] } : a));
}

// ── 채팅 대화 영속화 ──────────────────────────────────────────────────────────
// 채팅 대화 목록을 학번 스코프로 localStorage 에 보관해 새로고침/재방문 후에도
// 사이드바에서 대화를 전환·복원할 수 있게 한다 (ssu_overrides 와 동일 패턴).
//   키:  "ssu_chats:{studentId}"  (studentId 는 'ssu_session', 없으면 'anon')
//   값:  { conversations: [{ id, title, sub, updatedAt, messages: [...] }], activeId }
//   메시지: chat.jsx 의 Bubble 형식 그대로 — { role, text, t, error?, tool? }
function _chatsKey() {
  let sid = null;
  try { sid = localStorage.getItem('ssu_session'); } catch { /* noop */ }
  return `ssu_chats:${sid || 'anon'}`;
}
function _readChats() {
  try {
    const raw = localStorage.getItem(_chatsKey());
    const o = raw ? JSON.parse(raw) : {};
    return {
      conversations: Array.isArray(o.conversations) ? o.conversations : [],
      activeId: o.activeId || null,
    };
  } catch {
    return { conversations: [], activeId: null };
  }
}
function _writeChats(state) {
  try { localStorage.setItem(_chatsKey(), JSON.stringify(state)); } catch { /* 저장 실패 무시 */ }
}
// 대화 목록 메타(제목/부제) 생성 — 첫 user 메시지로 제목, 갱신 시각으로 부제.
function _convTitle(messages) {
  const firstUser = messages.find(m => m.role === 'user' && m.text);
  if (!firstUser) return '새 대화';
  const t = firstUser.text.trim().replace(/\s+/g, ' ');
  return t.length > 28 ? t.slice(0, 28) + '…' : t;
}
function _convSub(updatedAt, count) {
  const n = count || 0;
  const ms = Date.now() - new Date(updatedAt).getTime();
  let when;
  if (!updatedAt || Number.isNaN(ms)) when = '';
  else if (ms < 60_000) when = '방금';
  else if (ms < 3_600_000) when = `${Math.floor(ms / 60_000)}분 전`;
  else if (ms < 86_400_000) when = `${Math.floor(ms / 3_600_000)}시간 전`;
  else when = `${Math.floor(ms / 86_400_000)}일 전`;
  return [n ? `${n}개 메시지` : null, when].filter(Boolean).join(' · ') || '비어 있음';
}

// ── 동기화 활동 타임라인 영속화 (#7) ─────────────────────────────────────────
// 대시보드 '동기화 활동' 이벤트(동기화/로그인/세션갱신)는 메모리 state 만이라
// 새로고침하면 항상 비어 있었다. ssu_overrides 와 동일하게 학번 스코프
// localStorage 에 영속화하고 초기 effect 에서 복원한다.
//   키:  "ssu_activity:{studentId}"  (studentId 는 'ssu_session', 없으면 'anon')
//   값:  { events: [{ at, text, kind, meta }, ...] }  (최신 순, at = ISO timestamp)
// 표시용 상대시각('방금 전' 등)은 at 으로 렌더 시점에 계산 — 저장된 't' 문자열을
// 그대로 쓰면 새로고침 후 '방금 전'이 영원히 '방금 전'으로 굳는다.
const ACTIVITY_MAX = 30;   // 너무 길게 쌓이지 않게 상한
function _activityKey() {
  let sid = null;
  try { sid = localStorage.getItem('ssu_session'); } catch { /* noop */ }
  return `ssu_activity:${sid || 'anon'}`;
}
function _readActivity() {
  try {
    const raw = localStorage.getItem(_activityKey());
    const o = raw ? JSON.parse(raw) : {};
    return Array.isArray(o.events) ? o.events : [];
  } catch {
    return [];
  }
}
function _writeActivity(events) {
  try {
    localStorage.setItem(_activityKey(), JSON.stringify({ events: events.slice(0, ACTIVITY_MAX) }));
  } catch { /* 저장 실패 무시 */ }
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
  const suggestions = seed.SUGGESTIONS;

  // 현재 시각 — D-day·상대시각('방금 전' 등)·'오늘' 강조의 기준.
  // seed.NOW(모듈 로드 시 1회 고정)를 쓰면 탭을 오래 열어둘수록 전부 어긋나므로
  // (수동 동기화 후 '마지막 동기화'가 영원히 '방금 전', 자정 넘으면 D-day 하루 밀림)
  // 분 단위로 갱신되는 상태로 관리한다.
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const tick = () => setNow(new Date());
    const t = setInterval(tick, 60_000);
    // 브라우저는 백그라운드 탭 타이머를 스로틀하므로, 탭 복귀 시 즉시 갱신
    // (자정 넘긴 뒤 돌아와도 D-day 가 바로 맞도록)
    document.addEventListener('visibilitychange', tick);
    return () => {
      clearInterval(t);
      document.removeEventListener('visibilitychange', tick);
    };
  }, []);

  // 변할 수 있는 것들 (사용자 인터랙션으로 갱신됨)
  // 초기값은 빈 배열 — LMS 세션이 활성화되면 아래 useEffect 가 실데이터로 채운다(#4).
  // seed(가짜 강의·교수·공지)는 USE_MOCK 일 때만 주입한다. 그렇지 않으면 로그인은
  // 됐지만 LMS 미연결(세션 없음/만료)인 상태에서 seed 가 실데이터처럼 노출됐다(#4).
  const [courses,       setCourses]       = useState(Api.USE_MOCK ? seed.COURSES : []);
  const [assignments,   setAssignments]   = useState(Api.USE_MOCK ? seed.ASSIGNMENTS : []);
  const [notices,       setNotices]       = useState(Api.USE_MOCK ? seed.NOTICES : []);
  // 알림은 공지/과제에서 파생 (아래 useMemo).
  // 동기화 활동 타임라인은 학번 스코프 localStorage 에 영속화 — 새로고침 후 복원(#7).
  // 내부 저장 형태는 { at(ISO), text, kind, meta }. 표시용 상대시각은 렌더 시 계산.
  const [activity,      setActivity]      = useState(() => _readActivity());
  // 채팅 대화는 학번 스코프 localStorage 에 영속화 — 새로고침/재방문 후 복원.
  // chatStore = { conversations: [{ id, title, sub, updatedAt, messages }], activeId }
  const [chatStore, setChatStore] = useState(() => _readChats());
  // 다른 페이지(예: MCP)에서 '학습 비서로 실행' 시 예약하는 프롬프트.
  // chat.jsx 가 마운트/감지 시 자동 전송하고 즉시 비운다 (1회성).
  const [pendingChatPrompt, setPendingChatPrompt] = useState(null);
  const [connectors,    setConnectors]    = useState(seed.CONNECTORS);
  // 커넥터 상태 응답 도착 여부 — '확인 중' 표시용 (실패(null)여도 true)
  const [connectorsLoaded, setConnectorsLoaded] = useState(false);
  // in-process MCP 서버 상태 (lms/study/notion/obsidian) — connectors 페이지 표시용
  const [mcpServers, setMcpServers] = useState([]);
  const [mcpLoaded, setMcpLoaded] = useState(false);

  // 데이터 로딩 상태 — 초기 fetch / refetch 중일 때 true
  const [loading, setLoading] = useState(false);
  // 첫 데이터 fetch(성공/실패 무관) 완료 여부 — 페이지가 '빈 상태 vs 스켈레톤'을
  // 구분하는 데 쓴다(#4). USE_MOCK 이면 seed 가 이미 채워져 있으니 처음부터 true.
  const [firstFetchDone, setFirstFetchDone] = useState(Api.USE_MOCK);

  // 동기화 진행 상태 (Topbar 버튼이 사용)
  const [syncing, setSyncing] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState(null);
  // 백엔드 예약 동기화 시각(SYNC_HOUR) — connectors 페이지 안내용 (.env 관리)
  const [syncHour, setSyncHour] = useState(null);

  // ── LMS 세션 상태 ────────────────────────────────────────────────────────
  // { active, userInfo, savedAt, nextRefreshIn } | null
  const [lmsSession, setLmsSession] = useState(null);
  const [lmsBusy, setLmsBusy] = useState(false);   // 로그인 / 갱신 중

  // 커넥터 상태 병합 헬퍼 — 실패(null)면 seed 유지, 성공 시 id 매칭으로
  // status/meta/last 만 병합. gmail 등 백엔드가 모르는 항목은 seed 그대로 둔다.
  const _mergeConnectors = useCallback((list) => {
    if (!list) return;
    setConnectors(cs => cs.map(c => {
      const m = list.find(x => x.id === c.id);
      return m ? { ...c, status: m.status, meta: m.meta || c.meta, last: m.last ?? c.last } : c;
    }));
  }, []);

  // 앱 시작 시 한 번 세션 상태 조회.
  // 데이터 fetch 는 아래 effect 가 lmsSession.active 가 true 가 된 시점에 수행.
  // (세션이 없는 가입 화면에서 503 토스트가 뜨지 않도록 분리)
  useEffect(() => {
    LmsAuthApi.getLmsSessionStatus().then(s => setLmsSession(s));
    // 마지막 동기화 시각/예약 시각도 백엔드에서 받아오면 새로고침 후에도 보존된다.
    Api.fetchSyncStatus()
      .then(s => {
        if (s?.lastSyncAt) setLastSyncAt(new Date(s.lastSyncAt));
        if (typeof s?.syncHour === 'number') setSyncHour(s.syncHour);
      })
      .catch(() => { /* 백엔드 미기동 — 무시 */ });
    // 커넥터 실상태 — fetchConnectorsStatus 는 절대 reject 하지 않으므로(null 반환) 안전.
    Api.fetchConnectorsStatus().then(list => {
      setConnectorsLoaded(true);
      _mergeConnectors(list);
    });
    // in-process MCP 서버 상태 — 실패(null)면 빈 목록 유지(throw 안 함).
    Api.fetchMcpStatus().then(list => {
      setMcpLoaded(true);
      if (list) setMcpServers(list);
    });
  }, [_mergeConnectors]);

  // fetch/refetch 결과 반영 헬퍼 — 읽음/제출 오버레이를 병합하고,
  // 성공한 항목은 빈 배열도 그대로 반영한다 (seed 가 실데이터처럼 남지 않게).
  // 실패한 항목(null)만 기존 상태 유지.
  const applyBundle = useCallback(({ courses: c, assignments: a, notices: n }) => {
    if (c) setCourses(c);
    if (a) setAssignments(_overlayAssignments(a));
    if (n) setNotices(_overlayNotices(n));
  }, []);

  // 동기화 활동 이벤트 1건 추가 — 최신을 맨 앞에 두고 localStorage 에 영속화(#7).
  // text/kind/meta 만 받고 at(타임스탬프)은 여기서 찍는다. 상한(ACTIVITY_MAX) 적용.
  const pushActivity = useCallback(({ text, kind, meta }) => {
    setActivity(prev => {
      const next = [{ at: new Date().toISOString(), text, kind, meta: meta || '' }, ...prev]
        .slice(0, ACTIVITY_MAX);
      _writeActivity(next);
      return next;
    });
  }, []);

  // LMS 세션 만료 시 저장된 자격증명으로 1회 자동 재로그인.
  // 초기 로드 / triggerSync 의 두 인증 실패 경로(errors 배열, throw 된 401)가
  // 동일하게 사용한다. 성공하면 lmsSession 갱신 후 true, 그 외 false.
  //   - 자격증명 없음 → false (호출 측이 "Connectors 에서 재로그인" 안내)
  //   - 재로그인 실패 → false (+ 호출 측이 사유 토스트)
  const _relogin = useCallback(async () => {
    const creds = getLmsCredentials();
    if (!creds?.id || !creds?.password) return { ok: false, noCreds: true };
    onToast?.({ kind: 'info', text: 'LMS 세션 만료 — 자동 재로그인 중…' });
    const r = await LmsAuthApi.lmsLogin(creds.id, creds.password);
    if (r.ok) {
      setLmsSession({ active: true, userInfo: r.userInfo, savedAt: r.savedAt });
      return { ok: true };
    }
    return { ok: false, error: r.error };
  }, [onToast]);

  // 세션이 활성화되면(가입 후 로그인 등으로 ssu_session 이 늦게 설정된 경우 포함)
  // 해당 학번 스코프의 활동 타임라인을 다시 복원한다(#7). Provider 마운트 시점에
  // ssu_session 이 아직 없어 'anon' 키로 초기화됐을 수 있으므로.
  useEffect(() => {
    if (!lmsSession?.active) return;
    setActivity(_readActivity());
  }, [lmsSession?.active]);

  // LMS 세션이 활성화되면 (= 가입 후 loginLms 성공, 또는 앱 재시작 후 캐시 유효) 데이터 fetch.
  useEffect(() => {
    if (!lmsSession?.active) return;
    let alive = true;
    setLoading(true);
    (async () => {
      try {
        let bundle = await Api.fetchInitialBundle();

        // Canvas 쿠키 만료 등 인증 실패면 저장된 자격증명으로 1회 자동 재로그인 후 재시도
        // (triggerSync 의 자동 재로그인 경로와 동일한 _relogin 헬퍼 사용)
        if (bundle.errors?.length && _isAuthError(bundle.errors)) {
          const r = await _relogin();
          if (r.ok) bundle = await Api.fetchInitialBundle();
        }

        if (!alive) return;
        applyBundle(bundle);
        if (bundle.errors?.length) {
          console.warn('[DataStore] 일부 데이터 로드 실패:', bundle.errors);
          onToast?.({ kind: 'error', text: '일부 데이터 로드에 실패했습니다.' });
        }
      } catch (err) {
        if (!alive) return;
        console.warn('[DataStore] 데이터 로드 실패:', err);
        onToast?.({ kind: 'error', text: '데이터 로드에 실패했습니다.' });
      } finally {
        if (alive) {
          setLoading(false);
          setFirstFetchDone(true);   // 성공/실패 무관 — 첫 fetch 완료 표시(#4)
        }
      }
    })();
    return () => { alive = false; };
  // savedAt 변화는 무시 — 같은 세션 갱신엔 refetch 불필요
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lmsSession?.active]);

  // ──────────────────────────────────────────────────────────────────────────
  // 액션: 공지
  // ──────────────────────────────────────────────────────────────────────────
  // id 는 seed(문자열 'n1')와 실데이터(숫자)가 섞일 수 있어 String 비교로 통일.
  const markNoticeRead = useCallback((id) => {
    _writeOverrides({ noticesRead: { [id]: true } });   // 새로고침/refetch 후에도 유지
    setNotices(ns => ns.map(n => String(n.id) === String(id) ? { ...n, unread: false } : n));
  }, []);

  const markAllNoticesRead = useCallback(() => {
    // 미열람 공지가 0건이면 setState·토스트 없이 조기 반환(#15).
    // (UI 버튼은 unread===0 시 비활성화되지만, 알림 '모두 읽음' 등 다른 경로로
    //  호출돼도 "0건인데 성공 토스트"가 뜨지 않도록 여기서도 한 번 더 막는다.)
    const read = {};
    notices.forEach(n => { if (n.unread) read[n.id] = true; });
    if (Object.keys(read).length === 0) return;
    _writeOverrides({ noticesRead: read });
    setNotices(ns => ns.map(n => ({ ...n, unread: false })));
    onToast?.({ kind: 'success', text: '모든 공지를 읽음으로 표시했습니다.' });
  }, [notices, onToast]);

  // ──────────────────────────────────────────────────────────────────────────
  // 액션: 과제
  // 앱이 실제 제출을 못 하므로 "개인 체크" 의미 — 오버레이가 백엔드 값보다 우선.
  // ──────────────────────────────────────────────────────────────────────────
  const toggleAssignmentSubmit = useCallback((id) => {
    const target = assignments.find(a => String(a.id) === String(id));
    if (!target) return;
    const next = !target.submitted;
    _writeOverrides({ assignmentsSubmitted: { [id]: next } });
    setAssignments(as => as.map(a => String(a.id) === String(id) ? { ...a, submitted: next } : a));
    onToast?.({
      kind: next ? 'success' : 'info',
      text: next ? `"${target.title}" 제출 완료로 표시했습니다.` : `"${target.title}" 제출 취소했습니다.`,
    });
  }, [assignments, onToast]);

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
      // sync 의 두 가지 세션-만료 신호를 한 곳에서 통일 처리한다:
      //   ① 백엔드가 부분 실패로 result.errors 에 401 류 메시지를 담아 200 으로 응답
      //   ② 백엔드가 401 ("재로그인 필요") 로 응답 → Api.triggerSync() 가 throw (가장 흔한 경로)
      // 둘 다 _isAuthError 로 잡아 저장된 자격증명으로 1회 재로그인 후 재시도.
      // (load_session 이 lms·canvas 쿠키를 함께 연장하지만 SSO 세션 자체가 죽으면 full 재로그인만 유효)
      let result;
      let authFailed = false;
      try {
        result = await Api.triggerSync();
        if (_isAuthError(result.errors)) authFailed = true;
      } catch (e) {
        if (!_isAuthError(e)) throw e;   // 인증 외 오류는 바깥 catch 로
        authFailed = true;
      }

      if (authFailed) {
        const r = await _relogin();
        if (r.ok) {
          // 재로그인 성공 — sync 재시도. 재시도 throw 는 바깥 catch 로 흘려보낸다.
          result = await Api.triggerSync();
        } else if (r.noCreds) {
          onToast?.({ kind: 'error', text: 'LMS 세션이 만료됐고 저장된 비밀번호가 없습니다. Connectors 에서 재로그인 해주세요.' });
        } else {
          onToast?.({ kind: 'error', text: r.error || '자동 재로그인 실패 — Connectors 페이지에서 다시 시도해주세요.' });
        }
        // 재로그인 불가(noCreds/실패)면 result 가 비어 있을 수 있으니 안전한 빈 결과로.
        if (!result) result = { courses: 0, notices: 0, assignments: 0, materials: 0, errors: ['세션 만료 — 재로그인 필요'], syncedAt: null };
      }

      // 동기화 후 데이터 새로고침 (성공/부분실패 모두 시도 — 일부라도 들어왔을 수 있음)
      // applyBundle 경유 — 읽음/제출 오버레이(#35) 병합 + 빈 배열도 반영 (초기 로드와 동일 정책)
      try {
        applyBundle(await Api.fetchInitialBundle());
      } catch (e) {
        console.warn('[DataStore] 동기화 후 refetch 실패:', e);
      }

      const summary = [
        `${result.courses}개 강의`,
        result.notices ? `공지 ${result.notices}건` : null,
        result.assignments ? `과제 ${result.assignments}건` : null,
        result.materials ? `자료 ${result.materials}건` : null,
      ].filter(Boolean).join(' · ');

      pushActivity({ text: '수동 동기화 완료', kind: 'sync', meta: summary || `${courses.length}개 강의` });
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
  }, [syncing, courses.length, applyBundle, onToast, _relogin, pushActivity]);

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
        pushActivity({ text: 'LMS 로그인 성공', kind: 'auth', meta: `학번 ${studentId}` });
        onToast?.({ kind: 'success', text: 'LMS 세션이 발급되었습니다.' });
      } else {
        onToast?.({ kind: 'error', text: res.error || 'LMS 로그인 실패' });
      }
      return res;
    } finally {
      setLmsBusy(false);
    }
  }, [onToast, pushActivity]);

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
          pushActivity({ text: 'LMS 재로그인 — 세션 재발급', kind: 'auth', meta: '저장된 자격증명 사용' });
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
        pushActivity({ text: '세션 갱신 — 쿠키 재발급', kind: 'auth', meta: 'load_session()' });
        onToast?.({ kind: 'success', text: 'LMS 세션을 갱신했습니다.' });
      } else {
        onToast?.({ kind: 'error', text: res.error || '갱신 실패' });
      }
      return res;
    } finally {
      setLmsBusy(false);
    }
  }, [onToast, pushActivity]);

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
  // 액션: 채팅 — 대화 목록 전환 / 새 대화 / 영속화
  // chat.jsx 가 스트리밍 버퍼(msgs)를 들고, 교환이 끝날 때마다 saveActiveMessages
  // 로 현재 대화에 반영한다. 대화 전환 시 activeMessages 를 다시 버퍼로 로드한다.
  // ──────────────────────────────────────────────────────────────────────────
  // chatStore 변경 시 localStorage 에 영속화 (학번 스코프).
  useEffect(() => { _writeChats(chatStore); }, [chatStore]);

  // 사이드바용 대화 목록 메타 (active 플래그 포함, 최근 갱신 순).
  const conversations = useMemo(() => {
    return chatStore.conversations.map(c => ({
      id: c.id,
      title: c.title || _convTitle(c.messages || []),
      sub: _convSub(c.updatedAt, (c.messages || []).length),
      active: c.id === chatStore.activeId,
    }));
  }, [chatStore]);

  // 현재 활성 대화의 메시지 — chat.jsx 가 마운트/전환 시 로컬 버퍼로 복원한다.
  const activeConversationId = chatStore.activeId;
  const activeMessages = useMemo(() => {
    const conv = chatStore.conversations.find(c => c.id === chatStore.activeId);
    return conv?.messages || [];
  }, [chatStore]);

  // 새 대화 시작. 이미 빈 대화가 활성이면 그걸 재사용해 빈 "새 대화"가 쌓이지 않게.
  const startNewConversation = useCallback(() => {
    setChatStore(s => {
      const active = s.conversations.find(c => c.id === s.activeId);
      if (active && (active.messages || []).length === 0) {
        return s; // 이미 빈 새 대화 — 그대로 둠
      }
      const id = `c${Date.now()}`;
      const conv = { id, title: '새 대화', updatedAt: new Date().toISOString(), messages: [] };
      return { conversations: [conv, ...s.conversations], activeId: id };
    });
    onToast?.({ kind: 'info', text: '새 대화를 시작했습니다.' });
  }, [onToast]);

  const selectConversation = useCallback((id) => {
    setChatStore(s => (s.activeId === id ? s : { ...s, activeId: id }));
  }, []);

  // '학습 비서로 실행' — MCP 페이지 버튼이 호출. 프롬프트를 예약하고 /chat 으로 이동하면
  // chat.jsx 의 effect 가 이를 자동 전송한다(해당 MCP 도구 호출 → 결과 응답). 1회성.
  const askAssistant = useCallback((text) => {
    if (text && text.trim()) setPendingChatPrompt(text.trim());
  }, []);
  const clearPendingChatPrompt = useCallback(() => setPendingChatPrompt(null), []);

  // 현재 활성 대화에 메시지 목록을 저장(덮어쓰기). 활성 대화가 없으면 새로 만든다.
  // chat.jsx 가 스트리밍 도중/완료 시 호출 — 빈 배열이면 저장하지 않는다.
  const saveActiveMessages = useCallback((messages) => {
    if (!messages?.length) return;
    setChatStore(s => {
      let activeId = s.activeId;
      let list = s.conversations;
      // 활성 대화가 없거나 목록에 없으면 새로 만든다.
      if (!activeId || !list.some(c => c.id === activeId)) {
        activeId = `c${Date.now()}`;
        list = [{ id: activeId, title: '새 대화', updatedAt: new Date().toISOString(), messages: [] }, ...list];
      }
      const conversations = list.map(c => c.id === activeId
        ? {
            ...c,
            messages,
            title: _convTitle(messages),
            updatedAt: new Date().toISOString(),
          }
        : c);
      return { conversations, activeId };
    });
  }, []);

  // 대화 삭제 — 사이드바에서 개별 대화를 지울 때 (활성 대화면 가장 최근 것으로 이동).
  const deleteConversation = useCallback((id) => {
    setChatStore(s => {
      const conversations = s.conversations.filter(c => c.id !== id);
      const activeId = s.activeId === id ? (conversations[0]?.id || null) : s.activeId;
      return { conversations, activeId };
    });
  }, []);

  // ──────────────────────────────────────────────────────────────────────────
  // 액션: 커넥터 상태 새로고침 — 백엔드 /api/connectors/status 재조회·병합
  // ──────────────────────────────────────────────────────────────────────────
  // (예전 toggleConnector mock 제거 — status 는 백엔드 실상태로만 결정된다)
  const reloadConnectors = useCallback(async () => {
    // 커넥터 + MCP 서버 상태를 함께 재조회 (둘 다 절대 reject 안 함 — null 반환).
    const [list, mcp] = await Promise.all([
      Api.fetchConnectorsStatus(),
      Api.fetchMcpStatus(),
    ]);
    setConnectorsLoaded(true);
    setMcpLoaded(true);
    if (mcp) setMcpServers(mcp);
    if (!list) {
      onToast?.({ kind: 'error', text: '백엔드에 연결할 수 없어 커넥터 상태를 갱신하지 못했습니다.' });
      return false;
    }
    _mergeConnectors(list);
    onToast?.({ kind: 'success', text: '커넥터 상태를 갱신했습니다.' });
    return true;
  }, [_mergeConnectors, onToast]);

  // ──────────────────────────────────────────────────────────────────────────
  // 액션: 커넥터 키 저장 — Notion/Obsidian/LLM 키를 백엔드 .env 에 upsert
  // ──────────────────────────────────────────────────────────────────────────
  // payload 는 백엔드 키 이름(notion_token / obsidian_base_url / llm_api_key …).
  // 호출 측(connectors 페이지)에서 빈 입력을 미리 추려 보낸다.
  //   - restart_required=true  → 'Notion/Obsidian 은 백엔드 재시작 후 반영' 안내
  //   - restart_required=false → 'LLM 등 즉시 적용됨' 안내
  // 저장 성공 후엔 커넥터 상태를 한 번 다시 받아 status 배지를 갱신한다(토스트 없이 병합).
  const saveConnectorConfig = useCallback(async (payload) => {
    const res = await Api.saveConnectorConfig(payload);   // throw 하지 않음
    if (!res.ok) {
      onToast?.({ kind: 'error', text: res.error || '커넥터 설정 저장에 실패했습니다.' });
      return res;
    }
    if (res.restartRequired) {
      onToast?.({ kind: 'info', text: '키를 저장했습니다 — Notion/Obsidian 연동은 백엔드 재시작 후 반영됩니다.' });
    } else {
      onToast?.({ kind: 'success', text: res.detail || '커넥터 설정을 적용했습니다.' });
    }
    // 상태 배지 갱신 — fetchConnectorsStatus 는 절대 reject 안 함(null 반환).
    const list = await Api.fetchConnectorsStatus();
    if (list) _mergeConnectors(list);
    return res;
  }, [_mergeConnectors, onToast]);

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
  // 슬라이스한 id 를 문자열 그대로 전달 — markNoticeRead 가 String 비교(198행 규약)하므로
  // seed 문자열 id('n1')와 실데이터 숫자 id 모두 동작한다 (Number() 변환 시 'n1' → NaN 실패).
  const markNotificationRead = useCallback((id) => {
    if (typeof id === 'string' && id.startsWith('notice-')) {
      markNoticeRead(id.slice('notice-'.length));
    }
  }, [markNoticeRead]);

  const markAllNotificationsRead = useCallback(() => {
    markAllNoticesRead();
  }, [markAllNoticesRead]);

  // ──────────────────────────────────────────────────────────────────────────
  // 파생 헬퍼 (selector 패턴)
  // ──────────────────────────────────────────────────────────────────────────
  // 강의자료(modules)는 course-detail 이 Api.fetchModules 로 직접 조회하므로
  // 여기서는 더 이상 제공하지 않는다 (seed.MODULES 의존 제거).
  const getCourseById   = useCallback((id) => coursesEnriched.find(c => c.id === id), [coursesEnriched]);
  const getAssignmentsByCourse = useCallback((cid) => assignments.filter(a => a.course === cid), [assignments]);
  const getNoticesByCourse     = useCallback((cid) => notices.filter(n => n.course === cid),     [notices]);

  // ──────────────────────────────────────────────────────────────────────────
  // 파생: LMS 연결 여부 — 페이지가 '실데이터 vs 빈 상태'를 가르는 단일 기준(#4).
  //   - USE_MOCK 이면 seed 로 채워져 있으니 항상 연결됨으로 취급(빈 상태 안 띄움).
  //   - 실연결이면 lmsSession.active 가 true 여야 데이터 fetch 가 돈다.
  // lmsSession 이 아직 null(세션 조회 전)이면 false → 페이지는 firstFetchDone 으로
  // '확인 중(스켈레톤)'을 구분한다.
  // ──────────────────────────────────────────────────────────────────────────
  const lmsConnected = Api.USE_MOCK || !!lmsSession?.active;

  const value = {
    // 정적 데이터
    user, semester, now, suggestions,
    // 동적 데이터 (courses 는 unread/dueSoon 보강본)
    courses: coursesEnriched, assignments, notices, notifications, activity,
    connectors, connectorsLoaded,
    // in-process MCP 서버 상태 (커넥터 페이지 'MCP 서버' 카드)
    mcpServers, mcpLoaded,
    // 채팅 대화 (영속화 — ssu_chats:{studentId})
    conversations, activeConversationId, activeMessages,
    // 다른 페이지 → 학습 비서 자동 질문 (MCP 페이지 '실행' 버튼)
    pendingChatPrompt, askAssistant, clearPendingChatPrompt,
    // 로딩 / 동기화 상태
    loading, firstFetchDone, syncing, lastSyncAt, syncHour,
    // LMS 세션 상태 + 액션 (lmsConnected = 페이지 빈 상태 게이트 기준, #4)
    lmsSession, lmsConnected, lmsBusy,
    loginLms, refreshLms, reloadLmsSession, clearLms,
    // 액션
    markNotificationRead, markAllNotificationsRead,
    markNoticeRead, markAllNoticesRead,
    toggleAssignmentSubmit,
    triggerSync,
    startNewConversation, selectConversation, saveActiveMessages, deleteConversation,
    reloadConnectors, saveConnectorConfig,
    // 셀렉터
    getCourseById, getAssignmentsByCourse, getNoticesByCourse,
  };

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}
