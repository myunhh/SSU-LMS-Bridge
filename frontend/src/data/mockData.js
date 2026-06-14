// src/data/mockData.js
// ──────────────────────────────────────────────────────────────────────────────
// 백엔드 API 응답을 흉내내는 mock 데이터.
//
// ⚠️ 더 이상 기본 초기값이 아니다(#4). DataStore 는 USE_MOCK 일 때만 아래 seed
//    (COURSES/ASSIGNMENTS/NOTICES)를 주입한다. 실연결(USE_MOCK=false)에서는
//    courses/assignments/notices 의 초기값이 빈 배열이라, 로그인은 됐지만 LMS
//    미연결(세션 없음/만료)인 상태에서 가짜 강의·교수·공지가 실데이터처럼 노출되지
//    않는다. 페이지는 lmsConnected/firstFetchDone 으로 빈 상태·스켈레톤을 가른다.
//    이 seed 는 UI 개발용(USE_MOCK=true)으로만 남겨 둔다.
//
// 모든 페이지(dashboard, course-detail, chat, calendar, sidebar 등)가 mock 모드에서
// 참조하는 데이터다. ! 페이지 안에서 따로 mock 데이터를 만들지 말 것.
//
// ! UI 메뉴/문구/페이지 타이틀 같은 정적 콘텐츠는 ./uiConfig.js
//
// ── 환경 변수 ─────────────────────────────────────────────────────────────────
// 브라우저 코드는 Node 의 `require('dotenv')` 를 못 쓴다 (브라우저에는 require 가
// 없음). Vite 는 `frontend/.env` 의 VITE_* 변수를 import.meta.env 로 노출한다.
//
// ⚠️ Vite 의 환경변수는 빌드 시 코드에 박혀 모든 사용자에게 공개된다.
//    LMS_PASSWORD, NOTION_TOKEN 같은 비밀값은 절대 VITE_* 로 두면 안 된다.
//    (그것들은 backend/.env 에 두고 백엔드만 읽어야 함)
// ──────────────────────────────────────────────────────────────────────────────

const env = import.meta.env;

// ── 현재 사용자 ────────────────────────────────────────────────────────────────
// 우선순위: localStorage 회원가입 정보 → .env 데모값 → 하드코딩 fallback
function _getStoredUser() {
  try {
    const studentId = localStorage.getItem('ssu_session');
    if (!studentId) return null;
    const list = JSON.parse(localStorage.getItem('ssu_accounts') || '[]');
    return list.find(a => a.studentId === studentId) || null;
  } catch { return null; }
}
const _stored = _getStoredUser();
const USER = {
  name:      _stored?.name      || env.VITE_DEMO_USER_NAME   || '홍길동',
  studentId: _stored?.studentId || env.VITE_DEMO_STUDENT_ID  || '20260000',
  email:     _stored?.email     || env.VITE_DEMO_USER_EMAIL  || 'student@soongsil.ac.kr',
  major:     _stored?.major     || env.VITE_DEMO_USER_MAJOR  || 'AI소프트웨어학부',
};

// ── 현재 학기 / 시점 ───────────────────────────────────────────────────────────
// NOW 는 SEMESTER 계산과 seed 데이터의 날짜 생성 기준 (모듈 로드 시 1회 고정).
// 실시간 D-day·상대시각 기준 시각은 DataStore.jsx 의 `now` 상태(분 단위 갱신)다 —
// 여기 NOW 를 그 용도로 다시 쓰지 말 것.
const NOW = new Date();

// 한국 대학 학기 기준으로 현재 학기·주차를 NOW 로부터 계산.
//   1학기: 3/2 시작 (3~8월),  2학기: 9/1 시작 (9~익년 2월)
//   16주차 + 방학. 범위를 벗어나면(방학) weekCurrent 를 클램프.
function _computeSemester(now) {
  const y = now.getFullYear();
  const m = now.getMonth() + 1; // 1~12
  let term, startYear, start;
  if (m >= 3 && m <= 8) {
    term = 1; startYear = y; start = new Date(y, 2, 2);          // 3/2
  } else {
    term = 2; startYear = m <= 2 ? y - 1 : y; start = new Date(startYear, 8, 1); // 9/1
  }
  const weekTotal = 16;
  const rawWeek = Math.floor((now - start) / (7 * 86400000)) + 1;
  const weekCurrent = Math.max(1, Math.min(weekTotal, rawWeek));
  const wd = ['일', '월', '화', '수', '목', '금', '토'][now.getDay()];
  return {
    year: startYear,
    term,
    weekCurrent,
    weekTotal,
    label: `${startYear}년 ${term}학기`,
    weekLabel: `${weekCurrent}주차`,
    todayLabel: `${now.getFullYear()}년 ${now.getMonth() + 1}월 ${now.getDate()}일 · ${wd}요일 · ${weekCurrent}주차`,
  };
}
const SEMESTER = _computeSemester(NOW);

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
// ⚠️ 더 이상 seed 가 아니다. 실제 활동 타임라인은 DataStore 가 사용자 동작(동기화/
//    로그인/세션갱신)으로 채워 학번 스코프 localStorage(ssu_activity:{studentId})에
//    영속화한다(#7). 아래는 이벤트 형태만 문서화한 빈 배열 — 가짜 수치(제출 만점 등)를
//    초기 화면에 보이지 않게 비워 둔다.
//    형태: { at: ISO타임스탬프, text, kind: 'sync'|'auth'|'submit'|'cron', meta }
const ACTIVITY = [];

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
// 기본은 미연결 — 백엔드 /api/connectors/status 가 살아 있으면 DataStore 가
// id 병합으로 실상태(status/meta/last)를 덮어쓴다 (컨트랙트 B). 백엔드가 꺼져
// 있으면 이 중립 seed 가 유지돼 '가짜 연결됨' 대신 '미연결'을 보인다.
const CONNECTORS = [
  { id: 'lms',     name: '숭실대 스마트캠퍼스 LMS', kind: 'OAuth · Playwright SSO', host: 'canvas.ssu.ac.kr',
    status: 'disconnected', meta: '상태 미확인', last: '—', icon: 'book' },
  { id: 'notion',  name: 'Notion',                 kind: 'API v1 — Internal Integration', host: 'api.notion.com',
    status: 'disconnected', meta: '상태 미확인', last: '—', icon: 'notion' },
  { id: 'obsidian',name: 'Obsidian (MCP)',         kind: 'MCP · Auth Code', host: 'localhost:27124',
    status: 'disconnected', meta: '상태 미확인', last: '—', icon: 'obsidian' },
  { id: 'llm',     name: 'LLM Provider',           kind: 'litellm · multi-provider', host: 'generativelanguage.googleapis.com',
    status: 'disconnected', meta: '상태 미확인', last: '—', icon: 'spark' },
  { id: 'gmail',   name: 'Gmail (로드맵)',          kind: 'OAuth · 알림 발송용 (예정)', host: 'gmail.googleapis.com',
    status: 'disconnected', meta: '마감 알림 메일 — 로드맵 단계 (미지원)', last: '—', icon: 'mail' },
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

// 캘린더 이벤트 — ASSIGNMENTS / NOTICES 에서 자동 생성.
// 실제 범위는 과제 마감·공지뿐이다 (학사/시험 'event' 데이터 소스 없음).
// 형태: { [day]: [{ c: courseId, t: 제목, kind: 'due'|'submit'|'notice' }, ...] }
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

  // 자료실/공지 성격의 보조 항목 (notice 로 표기 — 'event' 종류는 라이브에 데이터 소스가 없어 쓰지 않는다)
  push(21, { c: 6, t: 'GPU 서버 점검', kind: 'notice' });

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
