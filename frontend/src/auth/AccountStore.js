// src/auth/AccountStore.js
// ──────────────────────────────────────────────────────────────────────────────
// 계정 데이터(가입자 목록, 현재 세션) 를 다루는 "순수 함수" 모음.
//
// 지금은 localStorage 에 저장하지만, 백엔드 연결 시 각 함수 내부의 localStorage
// 접근을 fetch 호출로 교체하기만 하면 된다. (각 함수 하단에 백엔드 버전 주석)
//
// 주의:
//   - localStorage 는 동기 API 지만, 백엔드 fetch 대비를 위해 모든 함수를
//     async 로 선언했다. 페이지에서 await 로 호출해두면 백엔드 전환이 매끄럽다.
//   - 비밀번호는 절대 평문 저장하지 않는다 (SHA-256 + salt). crypto.js 참고.
// ──────────────────────────────────────────────────────────────────────────────

import { hashPassword, verifyPassword } from './crypto';

// localStorage 키 이름
const K_ACCOUNTS = 'ssu_accounts';   // 가입한 사용자 전체 목록
const K_SESSION  = 'ssu_session';    // 현재 로그인된 사용자 학번

// 학번 정규식 — "20" + 6자리 숫자
export const STUDENT_ID_REGEX = /^20\d{6}$/;

// ── 내부 헬퍼 ────────────────────────────────────────────────────────────────
function readAccounts() {
  try {
    const raw = localStorage.getItem(K_ACCOUNTS);
    const list = raw ? JSON.parse(raw) : [];
    const { migrated, changed } = migrateLegacySecrets(list);
    if (changed) {
      // 잔존 시크릿 정리본을 다시 저장 (저장 실패해도 메모리상 정리본은 사용)
      try { writeAccounts(migrated); } catch {}
    }
    return migrated;
  } catch {
    return [];
  }
}

/**
 * 레거시 마이그레이션 — 예전 가입 계정에 평문으로 남아 있던
 * notion.token / obsidian.authCode / claude.apiKey 를 읽는 시점에 제거하고
 * 존재 여부(connected) 불리언으로 변환한다.
 * (시크릿 값 자체는 어디에도 쓰이지 않으므로 localStorage 에 영속하지 않는다.
 *  실제 연동은 백엔드 .env 설정으로 이루어짐. lms.password 는
 *  getLmsCredentials 의 자동 재로그인에 실사용되므로 여기서 건드리지 않는다.)
 */
function migrateLegacySecrets(list) {
  let changed = false;
  const migrated = list.map(acc => {
    if (!acc || typeof acc !== 'object') return acc;
    const next = { ...acc };
    if (next.notion && 'token' in next.notion) {
      const { token, ...rest } = next.notion;
      next.notion = { ...rest, connected: !!(rest.connected || token) };
      changed = true;
    }
    if (next.obsidian && 'authCode' in next.obsidian) {
      const { authCode, ...rest } = next.obsidian;
      next.obsidian = { ...rest, connected: !!(rest.connected || authCode) };
      changed = true;
    }
    if (next.claude && 'apiKey' in next.claude) {
      const { apiKey, ...rest } = next.claude;
      next.claude = { ...rest, connected: !!(rest.connected || apiKey) };
      changed = true;
    }
    return next;
  });
  return { migrated, changed };
}

function writeAccounts(list) {
  localStorage.setItem(K_ACCOUNTS, JSON.stringify(list));
}

// ── 공개 API ─────────────────────────────────────────────────────────────────

/**
 * 새 계정을 가입시킨다.
 * @param {object} payload  signup.jsx 의 form 객체 (이름, 학번, 비밀번호, lms*, notion*, claude* …)
 * @returns {Promise<{ ok: true, user } | { ok: false, error }>}
 */
export async function signup(payload) {
  const { name, studentId, email, password } = payload;

  // 1. 학번 형식
  if (!STUDENT_ID_REGEX.test(studentId)) {
    return { ok: false, error: '학번 형식이 올바르지 않습니다. (예: 20231234)' };
  }

  // 2. 이메일 형식 (간단 검증 — UI 에서 한 번 더 검증되지만 직접 호출 대비)
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return { ok: false, error: '이메일 형식이 올바르지 않습니다.' };
  }

  // 3. 중복 가입 차단 (학번 + 이메일)
  const list = readAccounts();
  if (list.some(a => a.studentId === studentId)) {
    return { ok: false, error: '이미 가입된 학번입니다. 로그인 페이지로 이동해주세요.' };
  }
  const lowerEmail = email.toLowerCase();
  if (list.some(a => a.email?.toLowerCase() === lowerEmail)) {
    return { ok: false, error: '이미 가입된 이메일입니다.' };
  }

  // 4. 비밀번호 해시
  const passwordHash = await hashPassword(password, studentId);

  // 5. 저장
  const account = {
    name,
    studentId,
    passwordHash,
    email:  lowerEmail,
    major:  payload.major || 'AI소프트웨어학부',
    createdAt: new Date().toISOString(),
    // 연동 정보 — 시크릿 값(notionToken/obsidianAuthCode/claudeApiKey)은
    // 가입 시 백엔드 .env 로 전송만 하고 localStorage 에는 저장하지 않는다.
    // 여기엔 존재 여부(connected = '백엔드로 제출됨') 와 비밀이 아닌 설정값만 보관.
    // 자동 재로그인은 opt-in (#7) — autoRelogin 을 켰을 때만 LMS 비밀번호를
    // localStorage 에 보관한다. 미선택 시 connected/id 만 저장하고 비밀번호는 생략 →
    // 세션 만료 시 settings.jsx 에서 사용자가 직접 재입력(수동 폴백).
    lms: {
      id: payload.lmsId || '',
      connected: !!payload.lmsId,
      autoRelogin: !!payload.autoRelogin,
      // ⚠️ 데모 단계에선 평문 보관. 진짜 운영에선 백엔드 환경변수 / vault 로 옮겨야 함
      //    (getLmsCredentials 의 자동 재로그인에 실사용되는 유일한 시크릿)
      //    autoRelogin 을 끈 경우엔 password 키 자체를 저장하지 않는다.
      ...(payload.autoRelogin ? { password: payload.lmsPassword || '' } : {}),
    },
    notion: {
      connected: !!payload.notionToken,
      pageId:    payload.notionPageId || '',
    },
    obsidian: {
      connected: !!payload.obsidianAuthCode,
      vault:     payload.obsidianVault    || 'LMS_Bridge_Vault',
      endpoint:  payload.obsidianEndpoint || 'http://localhost:27124/mcp',
    },
    claude: {
      connected: !!payload.claudeApiKey,
      // 모델 기본값은 Gemini 기준 — 실 모델값은 가입 시 백엔드 llm_model 로도 전송된다.
      model:     payload.claudeModel || 'gemini-2.5-flash',
    },
  };
  writeAccounts([...list, account]);

  // 5. 자동 로그인 (세션 설정)
  localStorage.setItem(K_SESSION, studentId);

  return { ok: true, user: stripSecrets(account) };

  // ── 백엔드 연결 후 ─────────────────────────────────────────────────────────
  // const res = await fetch('/api/auth/signup', {
  //   method: 'POST',
  //   headers: { 'Content-Type': 'application/json' },
  //   body: JSON.stringify(payload),
  // });
  // if (!res.ok) {
  //   const err = await res.json().catch(() => ({}));
  //   return { ok: false, error: err.detail || '회원가입에 실패했습니다.' };
  // }
  // const { user, token } = await res.json();
  // localStorage.setItem('ssu_token', token);   // JWT 등
  // return { ok: true, user };
}

/**
 * 학번 + 비밀번호로 로그인 시도.
 * @returns {Promise<{ ok: true, user } | { ok: false, error }>}
 */
export async function login(studentId, password) {
  if (!STUDENT_ID_REGEX.test(studentId)) {
    return { ok: false, error: '학번 형식이 올바르지 않습니다. (예: 20231234)' };
  }

  const list = readAccounts();
  const acc = list.find(a => a.studentId === studentId);
  if (!acc) {
    return { ok: false, error: '가입된 계정이 아닙니다. 회원가입을 먼저 진행해주세요.' };
  }

  const ok = await verifyPassword(password, studentId, acc.passwordHash);
  if (!ok) {
    return { ok: false, error: '비밀번호가 일치하지 않습니다.' };
  }

  localStorage.setItem(K_SESSION, studentId);
  return { ok: true, user: stripSecrets(acc) };

  // ── 백엔드 연결 후 ─────────────────────────────────────────────────────────
  // const res = await fetch('/api/auth/login', {
  //   method: 'POST',
  //   headers: { 'Content-Type': 'application/json' },
  //   body: JSON.stringify({ studentId, password }),
  // });
  // if (res.status === 401) return { ok: false, error: '학번 또는 비밀번호가 일치하지 않습니다.' };
  // if (!res.ok)            return { ok: false, error: '로그인에 실패했습니다.' };
  // const { user, token } = await res.json();
  // localStorage.setItem('ssu_token', token);
  // return { ok: true, user };
}

/**
 * 현재 세션의 LMS 자격증명을 반환. (백엔드 /api/lms/login 자동 재시도용)
 *
 * 자동 재로그인(opt-in, #7)을 켠 계정만 비밀번호를 보관하므로, 끈 계정(또는
 * 비밀번호 키가 없는 계정)에 대해서는 null 을 반환한다 → 호출 측(settings.jsx /
 * DataStore _relogin·refreshLms)이 수동 재입력 폴백을 사용한다.
 *
 * ⚠️ 데모 단계에서 localStorage 평문 저장. 운영 단계에선 서버 측 vault 로 옮겨야 함.
 * @returns {{ id: string, password: string } | null}
 */
export function getLmsCredentials() {
  const studentId = localStorage.getItem(K_SESSION);
  if (!studentId) return null;
  const list = readAccounts();
  const acc = list.find(a => a.studentId === studentId);
  if (!acc?.lms?.id || !acc?.lms?.password) return null;
  return { id: acc.lms.id, password: acc.lms.password };
}

/**
 * 현재 로그인된 사용자 정보를 동기적으로 반환.
 * (앱 시작 시 AuthProvider 의 useState 초기값 — 렌더 전에 동기로 필요)
 * readAccounts 를 거치므로 레거시 시크릿 마이그레이션도 함께 수행된다.
 */
export function getCurrentUserSync() {
  const studentId = localStorage.getItem(K_SESSION);
  if (!studentId) return null;
  const list = readAccounts();
  const acc = list.find(a => a.studentId === studentId);
  return acc ? stripSecrets(acc) : null;
}

/**
 * 현재 로그인된 사용자 정보를 반환. (백엔드 전환 대비 async 버전)
 */
export async function getCurrentUser() {
  return getCurrentUserSync();

  // ── 백엔드 연결 후 ─────────────────────────────────────────────────────────
  // const token = localStorage.getItem('ssu_token');
  // if (!token) return null;
  // const res = await fetch('/api/auth/me', {
  //   headers: { Authorization: `Bearer ${token}` },
  // });
  // if (!res.ok) return null;
  // return await res.json();
}

/**
 * 로그아웃 — 세션만 제거. 가입 정보(ssu_accounts)는 그대로 유지.
 */
export async function logout() {
  localStorage.removeItem(K_SESSION);

  // ── 백엔드 연결 후 ─────────────────────────────────────────────────────────
  // const token = localStorage.getItem('ssu_token');
  // localStorage.removeItem('ssu_token');
  // if (token) {
  //   await fetch('/api/auth/logout', {
  //     method: 'POST',
  //     headers: { Authorization: `Bearer ${token}` },
  //   }).catch(() => {});  // 실패해도 로컬은 제거
  // }
}

/**
 * 현재 로그인 사용자의 프로필(표시 이름·학과 등)을 갱신.
 * @param {{name?: string, major?: string}} patch
 * @returns {Promise<{ ok: boolean, user?, error?: string }>}
 */
export async function updateProfile(patch) {
  const studentId = localStorage.getItem(K_SESSION);
  if (!studentId) return { ok: false, error: '로그인 상태가 아닙니다.' };
  const list = readAccounts();
  const idx = list.findIndex(a => a.studentId === studentId);
  if (idx < 0) return { ok: false, error: '계정을 찾을 수 없습니다.' };

  const allowed = {};
  if (typeof patch.name === 'string' && patch.name.trim()) allowed.name = patch.name.trim();
  if (typeof patch.major === 'string') allowed.major = patch.major.trim();

  list[idx] = { ...list[idx], ...allowed };
  writeAccounts(list);
  return { ok: true, user: stripSecrets(list[idx]) };
}

/**
 * (개발용) 가입된 모든 계정 + 세션 삭제. 데모 초기화 용도.
 */
export function resetAllAccounts() {
  localStorage.removeItem(K_ACCOUNTS);
  localStorage.removeItem(K_SESSION);
}

// 비밀번호 해시 / LMS 자격증명 같은 민감 필드를 제거한 사본 반환
function stripSecrets(account) {
  const { passwordHash, lms, notion, claude, obsidian, ...safe } = account;
  return {
    ...safe,
    // 연동 정보의 존재 여부만 노출
    // (notion/obsidian/claude 시크릿은 저장 자체를 안 하므로 connected 플래그에서 파생)
    // LMS 는 자동 재로그인(opt-in)을 꺼도 연결된 상태이므로 connected/id 로 판단한다.
    // (레거시 계정 호환: connected 키가 없으면 평문 password 잔존 여부로 폴백)
    hasLms:      !!(lms?.connected || lms?.id || lms?.password),
    hasNotion:   !!notion?.connected,
    hasObsidian: !!obsidian?.connected,
    hasClaude:   !!claude?.connected,
  };
}
