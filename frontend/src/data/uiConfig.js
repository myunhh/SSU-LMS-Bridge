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
export const WS_BASE  = env.VITE_WS_BASE_URL  || '';

// ── 사이드바 네비게이션 ──────────────────────────────────────────────────────
// id = 라우트 경로의 첫 세그먼트, iconName = pages/icons.jsx 의 키
export const NAV_ITEMS = [
  { id: 'dashboard',  label: '대시보드',   iconName: 'Home' },
  { id: 'calendar',   label: '캘린더',     iconName: 'Calendar', badge: '6' },
  { id: 'chat',       label: '학습 비서',  iconName: 'Sparkles' },
  { id: 'connectors', label: '커넥터',     iconName: 'Plug',     badge: '4/5' },
];

// ── 페이지별 Topbar 타이틀 ───────────────────────────────────────────────────
// {t: 제목, s: 부제} — 부제에 {{semester.label}} 등 토큰을 쓰면 App.jsx 에서 치환
export const PAGE_TITLES = {
  dashboard:  { t: '대시보드',     s: '{{semester.label}} · {{semester.weekLabel}}' },
  calendar:   { t: '캘린더',       s: '과제 마감 · 공지 · 학사 이벤트' },
  chat:       { t: '학습 비서',    s: 'RAG · 강의자료 컨텍스트 활성' },
  connectors: { t: '커넥터',       s: 'LMS · Notion · Obsidian · LLM' },
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
    desc:  '숭실대 스마트캠퍼스에서 강의자료, 공지, 과제를 자동으로 수집합니다. 세션 캐시로 12배 빠른 재동기화.' },
  { iconName: 'Sparkles', color: 'oklch(54% 0.14 305)',
    title: 'AI 학습 비서',
    desc:  '강의자료를 컨텍스트로 활용하는 RAG 기반 AI 비서. 마감 정리, 개념 설명, 퀴즈 생성을 도와드립니다.' },
  { iconName: 'Plug',     color: 'oklch(58% 0.13 195)',
    title: '다중 커넥터',
    desc:  'Notion, Obsidian, Gmail 등 사용 중인 서비스와 연동해 강의 데이터를 원하는 곳으로 내보냅니다.' },
  { iconName: 'Calendar', color: 'oklch(58% 0.13 35)',
    title: '통합 캘린더',
    desc:  '모든 강의의 마감일, 공지, 시험 일정을 하나의 캘린더에서 관리합니다.' },
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
  { id: 5, label: 'Claude',    sub: 'Anthropic API 키를 입력해주세요' },
];

export const SIGNUP_INITIAL = {
  name: '', studentId: '', email: '', password: '', passwordConfirm: '',
  lmsId: '', lmsPassword: '',
  notionToken: '', notionPageId: '',
  obsidianAuthCode: '', obsidianVault: 'LMS_Bridge_Vault', obsidianEndpoint: 'http://localhost:27124/mcp',
  claudeApiKey: '', claudeModel: 'claude-haiku-4-5',
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
export const CHAT_MODEL_LABEL  = 'claude-haiku-4-5';
export const CHAT_FOOTER_NOTE  = '비서는 LMS에 동기화된 자료만 컨텍스트로 사용합니다 · 응답은 검토 후 활용해 주세요';
export const CHAT_RAG_ENABLED  = true;
