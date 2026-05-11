// Mock LMS data — based on actual project context (SSU LMS, 7 courses, week-based modules)
// ──────────────────────────────────────────────────────────────────────────────
// 백엔드에서 넘어오는 데이터를 여기서 동기화 시켜야함.
// 모든 페이지(dashboard, course-detail, chat, calendar, sidebar 등)는
// 이 파일의 데이터만 참조한다. 페이지 안에서 따로 mock 데이터를 만들지 말 것.
// ──────────────────────────────────────────────────────────────────────────────

// ── 현재 사용자 ────────────────────────────────────────────────────────────────
const USER = {
  name: '강민',
  studentId: '20231234',
  email: 'kangmin@soongsil.ac.kr',
  major: 'AI융합학부',
};

// ── 현재 학기 / 시점 ───────────────────────────────────────────────────────────
// NOW 는 모든 D-day 계산의 기준 시각. 실서비스 전환 시 `new Date()` 로 교체.
const NOW = new Date('2026-05-09T10:00:00');

const SEMESTER = {
  year: 2026,
  term: 1,                // 1학기
  weekCurrent: 11,
  weekTotal: 16,
  label: '2026년 1학기',
  weekLabel: '11주차',
  todayLabel: '2026년 5월 9일 · 토요일 · 11주차',
};

// ── 강의 ──────────────────────────────────────────────────────────────────────
const COURSES = [
  { id: 1, code: 'AIM3015', name: '고급AI수학', professor: '이성훈', credits: 3, color: 'oklch(58% 0.14 268)',
    progress: 0.62, weekCurrent: 11, weekTotal: 16, materials: 23, unread: 2, dueSoon: 1 },
  { id: 2, code: 'CSE2003', name: '자료구조', professor: '김민재', credits: 3, color: 'oklch(58% 0.13 195)',
    progress: 0.69, weekCurrent: 11, weekTotal: 16, materials: 31, unread: 0, dueSoon: 0 },
  { id: 3, code: 'STA3010', name: '통계적학습이론', professor: '박지현', credits: 3, color: 'oklch(58% 0.13 35)',
    progress: 0.69, weekCurrent: 11, weekTotal: 16, materials: 18, unread: 4, dueSoon: 2 },
  { id: 4, code: 'CSE3022', name: '운영체제', professor: '한경수', credits: 3, color: 'oklch(56% 0.14 145)',
    progress: 0.62, weekCurrent: 11, weekTotal: 16, materials: 27, unread: 1, dueSoon: 0 },
  { id: 5, code: 'GEN1015', name: '학술적글쓰기', professor: '윤서아', credits: 2, color: 'oklch(60% 0.10 90)',
    progress: 0.75, weekCurrent: 12, weekTotal: 16, materials: 12, unread: 0, dueSoon: 1 },
  { id: 6, code: 'AIM4002', name: '딥러닝과응용', professor: '정유나', credits: 3, color: 'oklch(54% 0.14 305)',
    progress: 0.62, weekCurrent: 11, weekTotal: 16, materials: 29, unread: 3, dueSoon: 1 },
  { id: 7, code: 'CSE2010', name: '컴퓨터네트워크', professor: '최도윤', credits: 3, color: 'oklch(58% 0.10 230)',
    progress: 0.62, weekCurrent: 11, weekTotal: 16, materials: 21, unread: 0, dueSoon: 0 },
];

// ── 과제 ──────────────────────────────────────────────────────────────────────
const ASSIGNMENTS = [
  { id: 'a1', course: 3, title: '회귀분석 과제 #4 — Ridge & Lasso 비교', due: '2026-05-09T23:59:00', submitted: false, weight: 15, type: 'report' },
  { id: 'a2', course: 1, title: '벡터미적분 연습문제 6장', due: '2026-05-10T18:00:00', submitted: false, weight: 10, type: 'problem' },
  { id: 'a3', course: 6, title: 'Transformer 구현 실습 (PyTorch)', due: '2026-05-12T23:59:00', submitted: false, weight: 20, type: 'code' },
  { id: 'a4', course: 5, title: '논증 에세이 초안 (1500자)', due: '2026-05-13T17:00:00', submitted: false, weight: 25, type: 'essay' },
  { id: 'a5', course: 3, title: '주차별 퀴즈 #11', due: '2026-05-14T23:59:00', submitted: false, weight: 5, type: 'quiz' },
  { id: 'a6', course: 4, title: '프로세스 스케줄링 시뮬레이션', due: '2026-05-18T23:59:00', submitted: false, weight: 15, type: 'code' },
  { id: 'a7', course: 2, title: 'AVL Tree 구현', due: '2026-05-06T23:59:00', submitted: true, weight: 10, type: 'code' },
  { id: 'a8', course: 1, title: '선형변환 보고서', due: '2026-05-04T23:59:00', submitted: true, weight: 10, type: 'report' },
];

// ── 공지 ──────────────────────────────────────────────────────────────────────
const NOTICES = [
  { id: 'n1', course: 3, title: '5/14 강의 휴강 안내', date: '2026-05-08T09:12:00', unread: true, pinned: true },
  { id: 'n2', course: 6, title: '중간고사 채점 결과 공지', date: '2026-05-08T08:01:00', unread: true, pinned: false },
  { id: 'n3', course: 1, title: '과제 #5 자료 업로드', date: '2026-05-07T22:31:00', unread: true, pinned: false },
  { id: 'n4', course: 6, title: 'GPU 서버 사용 안내', date: '2026-05-07T15:08:00', unread: false, pinned: false },
  { id: 'n5', course: 3, title: 'TA 면담 시간 변경', date: '2026-05-06T11:42:00', unread: false, pinned: false },
  { id: 'n6', course: 4, title: '실습실 출입 카드 신청', date: '2026-05-05T10:00:00', unread: false, pinned: false },
];

// ── 주차별 모듈 ────────────────────────────────────────────────────────────────
const MODULES = {
  1: [
    { week: 9,  title: '고유값과 고유벡터',     items: 4, completed: 4, attended: true },
    { week: 10, title: '특이값분해 (SVD)',     items: 5, completed: 5, attended: true },
    { week: 11, title: '벡터미적분 입문',       items: 4, completed: 2, attended: true, current: true },
    { week: 12, title: '경사하강법 수학',       items: 0, completed: 0, attended: false, locked: true },
    { week: 13, title: '확률분포와 추정',       items: 0, completed: 0, attended: false, locked: true },
  ],
  3: [
    { week: 9,  title: '상관분석(1) — 상관계수의 개요', items: 5, completed: 5, attended: true },
    { week: 10, title: '상관분석(2) — 회귀로의 확장',   items: 4, completed: 4, attended: true },
    { week: 11, title: 'Ridge & Lasso 정규화',         items: 6, completed: 3, attended: true, current: true },
    { week: 12, title: '교차검증',                      items: 0, completed: 0, attended: false, locked: true },
    { week: 13, title: '의사결정 나무',                  items: 0, completed: 0, attended: false, locked: true },
  ],
};

// ── 동기화 활동 로그 ───────────────────────────────────────────────────────────
const ACTIVITY = [
  { t: '방금 전', text: 'Vault에 강의자료 4개 다운로드',     kind: 'sync', meta: '딥러닝과응용 · Week 11' },
  { t: '7분 전',  text: 'Notion DB 동기화 완료',             kind: 'sync', meta: '공지 3건 · 과제 1건 새로 추가' },
  { t: '1시간 전', text: '세션 갱신 — Bearer 토큰 재발급',   kind: 'auth', meta: 'storage_state.json · 0.5s' },
  { t: '오늘 04:00', text: '예약 동기화 실행',                kind: 'cron', meta: 'APScheduler · 23/23 성공' },
  { t: '어제',    text: 'AVL Tree 구현 제출 완료',           kind: 'submit', meta: '자료구조 · 만점' },
];

// ── 채팅 ─────────────────────────────────────────────────────────────────────
const CHAT_SEED = [
  { role: 'user', text: '이번 주에 마감인 과제 정리해줘. 각 과제 핵심 요구사항이랑 추천 시작 시점도.', t: '14:21' },
  { role: 'assistant', t: '14:21', text: 'sample', rich: 'deadlines' },
  { role: 'user', text: 'Ridge랑 Lasso 차이 한 번 더 짚어줄래?', t: '14:23' },
  { role: 'assistant', t: '14:23', text: 'sample', rich: 'ridge' },
];

const SUGGESTIONS = [
  '이번 주 마감 정리해줘',
  '딥러닝과응용 11주차 핵심만 요약',
  'SVD를 5문항짜리 퀴즈로 만들어줘',
  '미제출 과제 알림 켜줘',
];

// 채팅 사이드바 — 과거 대화 목록
const CONVERSATIONS = [
  { id: 'c1', title: '이번 주 마감 정리', sub: '4건 · 방금', active: true },
  { id: 'c2', title: 'SVD 5문항 퀴즈',     sub: '고급AI수학 · 어제' },
  { id: 'c3', title: '회귀분석 보고서 요약', sub: '통계적학습이론 · 5/6' },
  { id: 'c4', title: 'Transformer 구현 개요', sub: '딥러닝과응용 · 5/5' },
  { id: 'c5', title: '운영체제 시험 정리', sub: '운영체제 · 5/3' },
];

// ── 커넥터 ────────────────────────────────────────────────────────────────────
const CONNECTORS = [
  { id: 'lms',     name: '숭실대 스마트캠퍼스 LMS', kind: 'OAuth · Playwright SSO', host: 'canvas.ssu.ac.kr',
    status: 'connected', meta: '학번 20231234 · 7개 강의 동기화', last: '오늘 04:00', icon: 'book' },
  { id: 'notion',  name: 'Notion',                 kind: 'API v1 — Internal Integration', host: 'api.notion.com',
    status: 'connected', meta: '루트 페이지 · 1학기 / 2026', last: '7분 전', icon: 'notion' },
  { id: 'obsidian',name: 'Obsidian (MCP)',         kind: 'MCP · Auth Code', host: 'localhost:27124',
    status: 'connected', meta: 'Vault: LMS_Bridge_Vault · 153 files', last: '방금 전', icon: 'obsidian' },
  { id: 'llm',     name: 'LLM Provider',           kind: 'litellm · multi-provider', host: 'api.anthropic.com',
    status: 'connected', meta: 'claude-haiku-4-5 · 14.2K tok / 24h', last: '실시간', icon: 'spark' },
  { id: 'gmail',   name: 'Gmail (선택)',           kind: 'OAuth · 알림 발송용', host: 'gmail.googleapis.com',
    status: 'disconnected', meta: '연동 시 마감 24h 전 메일 알림', last: '—', icon: 'mail' },
];

// ── 알림 (사이드바 종 아이콘 팝오버) ────────────────────────────────────────────
const NOTIFICATIONS = [
  { id: 1, kind: 'deadline', course: '머신러닝',     courseColor: '#7c3aed',
    title: '과제 #4 — Ridge/Lasso 비교 마감',
    body: '오늘 23:59 마감 · 6시간 남음', time: '17분 전', unread: true },
  { id: 2, kind: 'notice',   course: '운영체제',     courseColor: '#0f766e',
    title: '중간고사 채점 결과 공지',
    body: '평균 72.4점 · 본인 점수: 81점', time: '1시간 전', unread: true },
  { id: 3, kind: 'sync',     course: null,           courseColor: '#3a4ca8',
    title: 'Notion 동기화 완료',
    body: '새 자료 12건 · 공지 3건이 노션에 반영되었습니다', time: '2시간 전', unread: true },
  { id: 4, kind: 'graded',   course: '데이터베이스', courseColor: '#9a3412',
    title: '실습 #3 채점 완료',
    body: '15.5 / 20점 · 피드백 1건', time: '오늘 09:12', unread: false },
  { id: 5, kind: 'notice',   course: '컴퓨터 네트워크', courseColor: '#1f2937',
    title: '오늘 강의 휴강 안내',
    body: '교수 출장으로 11:00 강의 휴강', time: '어제 18:40', unread: false },
  { id: 6, kind: 'deadline', course: '소프트웨어 공학', courseColor: '#0284c7',
    title: '팀 프로젝트 발표 자료 제출',
    body: 'D-3 · 5/12 (화) 23:59', time: '어제 14:02', unread: false },
];

// ── 캘린더 ────────────────────────────────────────────────────────────────────
// 5월 2026 (시작 요일: 금)
const CALENDAR_MONTH = {
  year: 2026,
  month: 5,
  startWeekday: 5, // 5/1 의 요일 (0=일 … 6=토)
  days: 31,
  today: 9,
  label: '2026년 5월',
};

// 캘린더 이벤트 — ASSIGNMENTS / NOTICES 에서 자동 생성 + 수동 이벤트 일부 추가
// 형태: { [day]: [{ c: courseId, t: 제목, kind: 'due'|'submit'|'notice'|'event' }, ...] }
function buildCalendarEvents() {
  const ev = {};
  const push = (day, item) => { (ev[day] ||= []).push(item); };

  // 과제 → due / submit
  for (const a of ASSIGNMENTS) {
    const d = new Date(a.due);
    if (d.getFullYear() !== CALENDAR_MONTH.year || (d.getMonth() + 1) !== CALENDAR_MONTH.month) continue;
    push(d.getDate(), {
      c: a.course,
      t: a.title.length > 18 ? a.title.slice(0, 18) + '…' : a.title,
      kind: a.submitted ? 'submit' : 'due',
    });
  }

  // 공지 → notice (제목에 날짜 정보가 있으면 그 날에 배치하기보단 공지 발행일에 배치)
  for (const n of NOTICES) {
    const d = new Date(n.date);
    if (d.getFullYear() !== CALENDAR_MONTH.year || (d.getMonth() + 1) !== CALENDAR_MONTH.month) continue;
    // 휴강 공지처럼 본문에 날짜가 있는 건 별도 처리하고 싶다면 여기서 분기
    if (n.title.includes('휴강')) {
      // "5/14 강의 휴강" 같은 패턴 추출
      const m = n.title.match(/(\d{1,2})\/(\d{1,2})/);
      if (m) {
        push(Number(m[2]), { c: n.course, t: n.title, kind: 'notice' });
        continue;
      }
    }
  }

  // 추가로 LMS 외부 일정 (학사 이벤트 등)
  push(21, { c: 6, t: 'GPU 서버 점검', kind: 'notice' });
  push(27, { c: 1, t: '중간 발표', kind: 'event' });

  return ev;
}
const CALENDAR_EVENTS = buildCalendarEvents();

export {
  USER,
  NOW,
  SEMESTER,
  COURSES,
  ASSIGNMENTS,
  NOTICES,
  MODULES,
  ACTIVITY,
  CHAT_SEED,
  SUGGESTIONS,
  CONVERSATIONS,
  CONNECTORS,
  NOTIFICATIONS,
  CALENDAR_MONTH,
  CALENDAR_EVENTS,
};
