// src/data/uiConfig.js
// ──────────────────────────────────────────────────────────────────────────────
// 정적 UI 구성 — 메뉴, 페이지 타이틀, 랜딩 카피, 가입 단계, 설정 섹션 등.
// 백엔드와 무관한, "디자이너/기획자가 손대는" 영역.
//
// 아이콘은 컴포넌트 참조를 직접 넣지 않고 "이름 문자열" 만 보관한다.
// (각 페이지에서 `pages/icons.jsx` 의 Icon[name] 으로 lookup)
// 이렇게 하면 이 파일이 React/JSX 에 의존하지 않는 순수 데이터가 된다.
//
// ⚠️ 백엔드에서 받아오는 동적 데이터는 ./mockData.js 에 있다.
// ──────────────────────────────────────────────────────────────────────────────

// ── 앱 브랜딩 ────────────────────────────────────────────────────────────────
const env = import.meta.env;
export const APP_BRAND = {
  name:    env.VITE_APP_NAME    || 'LMS Bridge',
  tag:     'ssu',
  subline: 'ssu · 2026 · 1학기',                                // sidebar 상단
  version: `v${env.VITE_APP_VERSION || '0.0.0'} · self-hosted`, // 설정 페이지 푸터
};

// ── API 기본 URL ─────────────────────────────────────────────────────────────
// 모든 fetch 호출이 공유. 빈 문자열이면 vite proxy 가 /api 를 처리.
export const API_BASE = env.VITE_API_BASE_URL || '';
// 빈 문자열이면 chat.js 가 현재 호스트 기준 절대 ws:// URL 로 폴백 (vite proxy ws:true 경유)
export const WS_BASE  = env.VITE_WS_BASE_URL  || '';

// ── 사이드바 네비게이션 ──────────────────────────────────────────────────────
// id = 라우트 경로의 첫 세그먼트, iconName = pages/icons.jsx 의 키
// badge 는 Sidebar 에서 실데이터로 동적 계산 (여기선 정의 안 함)
export const NAV_ITEMS = [
  { id: 'dashboard',  label: '대시보드',   iconName: 'Home' },
  { id: 'calendar',   label: '캘린더',     iconName: 'Calendar' },
  { id: 'chat',       label: '학습 비서',  iconName: 'Sparkles' },
  { id: 'connectors', label: '커넥터',     iconName: 'Plug' },
  { id: 'mcp',        label: 'MCP',        iconName: 'Code' },
];

// ── 페이지별 Topbar 타이틀 ───────────────────────────────────────────────────
// {t: 제목, s: 부제} — 부제에 {{semester.label}} 등 토큰을 쓰면 App.jsx 에서 치환
export const PAGE_TITLES = {
  dashboard:  { t: '대시보드',     s: '{{semester.label}} · {{semester.weekLabel}}' },
  calendar:   { t: '캘린더',       s: '과제 마감 · 공지' },
  chat:       { t: '학습 비서',    s: 'LMS 공지·과제·마감 실시간 조회' },
  connectors: { t: '커넥터',       s: 'LMS · Notion · Obsidian · LLM' },
  mcp:        { t: 'MCP 서버',     s: 'in-process MCP 4종 · 도구 목록·설명' },
  settings:   { t: '설정',         s: '계정 · 알림 · 동기화 · 외관' },
};

// 간단한 토큰 치환 헬퍼 ({{a.b.c}} → obj.a.b.c)
export function renderTitle(template, ctx) {
  return template.replace(/\{\{([\w.]+)\}\}/g, (_, path) => {
    return path.split('.').reduce((acc, k) => (acc == null ? '' : acc[k]), ctx) ?? '';
  });
}

// ── 랜딩 페이지 ──────────────────────────────────────────────────────────────
export const LANDING_FEATURES = [
  { iconName: 'Book',     color: 'var(--accent)',
    title: 'LMS 자동 동기화',
    desc:  '숭실대 스마트캠퍼스에서 공지·과제를 자동으로 수집·동기화합니다. 세션 캐시로 빠른 재동기화.' },
  { iconName: 'Sparkles', color: 'oklch(54% 0.14 305)',
    title: 'AI 학습 비서',
    desc:  'LMS 공지·과제·마감을 실시간으로 조회·정리하고, 동기화된 Notion을 참조하는 AI 비서. 마감 정리, 개념 설명, 퀴즈 생성을 도와드립니다.' },
  { iconName: 'Plug',     color: 'oklch(58% 0.13 195)',
    title: '다중 커넥터',
    desc:  'Notion, Obsidian과 연동해 강의 데이터를 원하는 곳으로 내보냅니다. Gmail 알림은 로드맵 단계입니다.' },
  { iconName: 'Calendar', color: 'oklch(58% 0.13 35)',
    title: '통합 캘린더',
    desc:  '모든 강의의 과제 마감일과 공지를 하나의 캘린더에서 관리합니다.' },
];

export const LANDING_STEPS = [
  { n: '01', title: '로그인',        desc: '숭실대 학번과 LMS 비밀번호로 1분 안에 계정을 연결합니다.' },
  { n: '02', title: '커넥터 연결',   desc: 'Notion, Obsidian, LLM 등 원하는 서비스를 연동합니다.' },
  { n: '03', title: '자동 동기화',   desc: '이후 강의자료·공지·과제가 매일 자동으로 업데이트됩니다.' },
];

// ── 회원가입 마법사 ──────────────────────────────────────────────────────────
export const SIGNUP_STEPS = [
  { id: 1, label: '기본 정보', sub: '이름과 학번을 입력해주세요' },
  { id: 2, label: 'LMS',       sub: '스마트캠퍼스 계정을 연결합니다' },
  { id: 3, label: 'Notion',    sub: 'Integration 토큰을 입력해주세요', optional: true },
  { id: 4, label: 'Obsidian',  sub: 'MCP 연결 정보를 입력해주세요',   optional: true },
  // 입력한 키는 백엔드 .env 로 저장(서버 재시작 후 반영) — 선택 입력이므로 필수로 강제하지 않는다
  { id: 5, label: 'Gemini',    sub: 'Gemini API 키를 입력해주세요', optional: true },
];

export const SIGNUP_INITIAL = {
  name: '', studentId: '', email: '', password: '', passwordConfirm: '',
  lmsId: '', lmsPassword: '',
  // 자동 재로그인(opt-in) — 기본 off. 켜야만 LMS 비밀번호가 localStorage 에 보관된다.
  // (#7) 미선택 시 비밀번호는 저장하지 않고, 세션 만료 때 settings.jsx 에서 수동 재입력.
  autoRelogin: false,
  notionToken: '', notionPageId: '',
  // obsidianEndpoint 는 백엔드 obsidian_base_url(Local REST API 베이스 URL)로 전송된다.
  // 백엔드 _ping_obsidian 이 베이스 URL 에 "/" 만 덧붙여 핑하므로 "/mcp" 같은 경로 접미사 없이
  // 베이스 주소만 둔다 (플러그인 기본값: 27124=HTTPS, 27123=HTTP — 실 환경에 맞게 수정).
  obsidianAuthCode: '', obsidianVault: 'LMS_Bridge_Vault', obsidianEndpoint: 'http://localhost:27124',
  // 필드명 claude* 는 기존 저장 계정(AccountStore) 호환을 위해 유지 — 표시·기본값은 Gemini 기준
  claudeApiKey: '', claudeModel: 'gemini-2.5-flash',
};

// ── 설정 페이지 좌측 메뉴 ────────────────────────────────────────────────────
export const SETTINGS_SECTIONS = [
  { id: 'account',       label: '계정',           iconName: 'Settings' },
  { id: 'notifications', label: '알림',           iconName: 'Bell' },
  { id: 'sync',          label: '동기화',         iconName: 'Sync' },
  { id: 'appearance',    label: '외관',           iconName: 'Eye' },
  { id: 'shortcuts',     label: '단축키',         iconName: 'Code' },
  { id: 'data',          label: '데이터 & 보안',  iconName: 'File' },
  { id: 'about',         label: '정보',           iconName: 'External' },
];

// ── 채팅 페이지 푸터 ─────────────────────────────────────────────────────────
export const CHAT_MODEL_LABEL  = 'gemini-2.5-flash';
// 비서는 강의자료 파일 본문을 읽지 못한다(LTI 뷰어 제약 — 실제 RAG 아님).
// LMS 공지·과제·마감을 실시간 조회(lms__* MCP)하고 동기화된 Notion을 참조한다.
export const CHAT_FOOTER_NOTE  = '비서는 LMS 공지·과제·마감을 실시간 조회하고 동기화된 Notion을 참조합니다 · 응답은 검토 후 활용해 주세요';
// 사이드바 푸터에 노출하는 도구 연결 표시 라벨 (과거 'RAG 켜짐' 자리)
export const CHAT_TOOLS_LABEL  = 'LMS 도구 연결';
