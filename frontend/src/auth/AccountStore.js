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
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
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
  const { name, studentId, password } = payload;

  // 1. 학번 형식
  if (!STUDENT_ID_REGEX.test(studentId)) {
    return { ok: false, error: '학번 형식이 올바르지 않습니다. (예: 20231234)' };
  }

  // 2. 중복 가입 차단
  const list = readAccounts();
  if (list.some(a => a.studentId === studentId)) {
    return { ok: false, error: '이미 가입된 학번입니다. 로그인 페이지로 이동해주세요.' };
  }

  // 3. 비밀번호 해시
  const passwordHash = await hashPassword(password, studentId);

  // 4. 저장
  const account = {
    name,
    studentId,
    passwordHash,
    email:  `${studentId}@soongsil.ac.kr`,
    major:  payload.major || 'AI소프트웨어학부',
    createdAt: new Date().toISOString(),
    // 연동 정보 (백엔드 붙으면 별도 secrets 테이블로 옮길 영역)
    lms: {
      id: payload.lmsId || '',
      // ⚠️ 데모 단계에선 평문. 진짜 운영에선 백엔드 환경변수 / vault 로 옮겨야 함
      password: payload.lmsPassword || '',
    },
    notion: {
      token:   payload.notionToken   || '',
      pageId:  payload.notionPageId  || '',
    },
    obsidian: {
      authCode: payload.obsidianAuthCode || '',
      vault:    payload.obsidianVault    || 'LMS_Bridge_Vault',
      endpoint: payload.obsidianEndpoint || 'http://localhost:27124/mcp',
    },
    claude: {
      apiKey: payload.claudeApiKey || '',
      model:  payload.claudeModel  || 'claude-haiku-4-5',
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
 * 현재 로그인된 사용자 정보를 반환. (앱 시작 시 AuthProvider 초기값으로 사용)
 */
export async function getCurrentUser() {
  const studentId = localStorage.getItem(K_SESSION);
  if (!studentId) return null;
  const list = readAccounts();
  const acc = list.find(a => a.studentId === studentId);
  return acc ? stripSecrets(acc) : null;

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
 * (개발용) 가입된 모든 계정 + 세션 삭제. 데모 초기화 용도.
 */
export function resetAllAccounts() {
  localStorage.removeItem(K_ACCOUNTS);
  localStorage.removeItem(K_SESSION);
}

// 비밀번호 해시 / 토큰 같은 민감 필드를 제거한 사본 반환
function stripSecrets(account) {
  const { passwordHash, lms, notion, claude, obsidian, ...safe } = account;
  return {
    ...safe,
    // 연동 정보의 존재 여부만 노출 (실제 값은 숨김)
    hasLms:      !!lms?.password,
    hasNotion:   !!notion?.token,
    hasObsidian: !!obsidian?.authCode,
    hasClaude:   !!claude?.apiKey,
  };
}
