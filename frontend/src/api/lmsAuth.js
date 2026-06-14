// src/api/lmsAuth.js
// ──────────────────────────────────────────────────────────────────────────────
// 백엔드 LMS 인증(SSO + Playwright 세션) API 호출 클라이언트.
//
// 백엔드 인터페이스(backend/app/adapter/auth.py 의 SSULMSAuthPlaywright):
//   - await login(student_id, password) -> bool
//   - await load_session() -> bool      (세션 유효성 확인 + 연장)
//   - get_session_data() -> { cookies, storage_state, user_info, saved_at }
//
// 위 메서드들은 FastAPI 라우트로 다음처럼 노출될 예정:
//   POST /api/lms/login           { studentId, password } → { ok, userInfo, savedAt }
//   GET  /api/lms/session         → { active, userInfo, savedAt, nextRefreshIn }
//   POST /api/lms/session/refresh → { ok, savedAt }
//
// 아직 백엔드 라우트가 없으므로 지금은 **mock 모드**로 동작.
// 백엔드 준비되면 USE_MOCK 만 false 로 바꾸면 즉시 실연결.
// ──────────────────────────────────────────────────────────────────────────────

import { API_BASE } from '../data/uiConfig';

// 백엔드 LMS 라우트(/api/lms/*) 가 구현되어 실연결.
// 로컬에서 백엔드를 띄우지 않고 UI 만 보고 싶다면 true 로 바꾸면 mock 으로 돌아간다.
const USE_MOCK = false;

// 백엔드 자동 세션 연장 주기 (백엔드 공용 상수: backend/app/api/session_meta.py 의
// SESSION_REFRESH_INTERVAL 과 동일: 5400초)
export const SESSION_REFRESH_INTERVAL = 5400;
// SSU SSO 쿠키 일반 만료 (관찰값 기준 약 7일 — backend/app/api/session_meta.py 의
// SESSION_MAX_AGE 와 짝. 한쪽을 바꾸면 반드시 같이 바꿀 것)
export const SESSION_MAX_AGE = 7 * 24 * 3600;

// ── localStorage 키 ───────────────────────────────────────────────────────────
const K_SESSION_META = 'ssu_lms_session_meta';

// 백엔드의 get_session_data() 가 반환하는 것 중 프론트가 보일 만한 메타.
// (실제 cookies / storage_state 은 절대 프론트에 노출 X — 백엔드 내부에서만 보유)
function readMeta() {
  try { return JSON.parse(localStorage.getItem(K_SESSION_META) || 'null'); } catch { return null; }
}
function writeMeta(meta) {
  if (!meta) localStorage.removeItem(K_SESSION_META);
  else localStorage.setItem(K_SESSION_META, JSON.stringify(meta));
}

// ── 공개 API ─────────────────────────────────────────────────────────────────

/**
 * LMS SSO 로그인 시도.
 * 백엔드는 Playwright 로 smartid.ssu.ac.kr 로그인 후 세션을 저장.
 * @returns {Promise<{ ok: boolean, error?: string, userInfo?: object, savedAt?: string }>}
 */
export async function lmsLogin(studentId, password) {
  if (USE_MOCK) {
    // mock — 자격증명 형식만 확인, 800ms 가짜 지연
    await new Promise(r => setTimeout(r, 800));
    if (!studentId || !password) return { ok: false, error: '학번과 비밀번호를 모두 입력해주세요.' };

    const meta = {
      userInfo: { name: 'demo', login_time: new Date().toISOString() },
      savedAt:  new Date().toISOString(),
    };
    writeMeta(meta);
    return { ok: true, ...meta };
  }

  // ── 실제 백엔드 호출 ────────────────────────────────────────────────────
  try {
    const res = await fetch(`${API_BASE}/api/lms/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ studentId, password }),
    });
    if (res.status === 401) {
      const d = await res.json().catch(() => ({}));
      return { ok: false, error: d.detail || 'LMS 학번 또는 비밀번호가 일치하지 않습니다.' };
    }
    if (!res.ok) return { ok: false, error: '서버 오류로 로그인하지 못했습니다.' };
    const data = await res.json();
    writeMeta({ userInfo: data.userInfo, savedAt: data.savedAt });
    return { ok: true, userInfo: data.userInfo, savedAt: data.savedAt };
  } catch {
    return { ok: false, error: '백엔드 서버에 연결할 수 없습니다. (uvicorn 실행 확인)' };
  }
}

/**
 * 저장된 LMS 세션의 현재 상태를 조회.
 * (백엔드의 load_session() 은 단순 조회를 넘어 연장까지 하지만,
 *  프론트에서 빈번한 조회를 일으키지 않도록 GET 으로 메타만 가져온다고 가정)
 * @returns {Promise<{ active: boolean, userInfo?, savedAt?, nextRefreshIn?: number }>}
 */
export async function getLmsSessionStatus() {
  if (USE_MOCK) {
    const meta = readMeta();
    if (!meta) return { active: false };

    // saved_at 부터 SESSION_MAX_AGE 가 지났으면 만료로 간주
    const savedAt = new Date(meta.savedAt).getTime();
    const age = (Date.now() - savedAt) / 1000;
    if (age > SESSION_MAX_AGE) {
      writeMeta(null);
      return { active: false };
    }
    return {
      active: true,
      userInfo: meta.userInfo,
      savedAt: meta.savedAt,
      // 다음 자동 갱신까지 남은 시간 (백엔드 스케줄러가 SESSION_REFRESH_INTERVAL 주기로 자동 갱신)
      nextRefreshIn: Math.max(0, SESSION_REFRESH_INTERVAL - (age % SESSION_REFRESH_INTERVAL)),
    };
  }

  try {
    const res = await fetch(`${API_BASE}/api/lms/session`);
    if (!res.ok) return { active: false };
    return await res.json();
  } catch {
    // 백엔드 미기동 — 비활성으로 간주 (앱은 정상 동작)
    return { active: false };
  }
}

/**
 * 세션을 즉시 갱신 (사용자가 "재발급" 버튼을 누른 경우).
 * 백엔드의 load_session() 호출 → 유효하면 쿠키/storage_state 새로 저장.
 * @returns {Promise<{ ok: boolean, error?: string, savedAt?: string }>}
 */
export async function refreshLmsSession() {
  if (USE_MOCK) {
    await new Promise(r => setTimeout(r, 600));
    const meta = readMeta();
    if (!meta) return { ok: false, error: '세션이 없습니다. 다시 로그인해주세요.' };
    const next = { ...meta, savedAt: new Date().toISOString() };
    writeMeta(next);
    return { ok: true, savedAt: next.savedAt };
  }

  try {
    const res = await fetch(`${API_BASE}/api/lms/session/refresh`, { method: 'POST' });
    if (res.status === 401) return { ok: false, error: '세션이 만료되었습니다. 다시 로그인해주세요.' };
    if (!res.ok)            return { ok: false, error: '세션 갱신에 실패했습니다.' };
    const data = await res.json();
    return { ok: true, savedAt: data.savedAt };
  } catch {
    return { ok: false, error: '백엔드 서버에 연결할 수 없습니다. (uvicorn 실행 확인)' };
  }
}

/**
 * 로컬 세션 메타를 지운다. (로그아웃 / 세션 초기화 용)
 * 백엔드 모드에선 추가로 DELETE /api/lms/session 호출.
 */
export async function clearLmsSession() {
  writeMeta(null);
  if (!USE_MOCK) {
    await fetch(`${API_BASE}/api/lms/session`, { method: 'DELETE' }).catch(() => {});
  }
}

// ── 표시용 헬퍼 ──────────────────────────────────────────────────────────────

/**
 * saved_at 부터 SESSION_MAX_AGE 까지 남은 시간을 "X일 X시간" 으로.
 */
export function formatSessionExpiry(savedAtIso) {
  if (!savedAtIso) return '—';
  const savedAt = new Date(savedAtIso).getTime();
  const remainMs = (savedAt + SESSION_MAX_AGE * 1000) - Date.now();
  if (remainMs <= 0) return '만료됨';
  const days = Math.floor(remainMs / 86400000);
  const hours = Math.floor((remainMs % 86400000) / 3600000);
  if (days > 0) return `만료 ${days}일 ${hours}시간 후`;
  return `만료 ${hours}시간 후`;
}

/**
 * saved_at 으로부터 경과 시간을 "방금 전 / 7분 전 / 1시간 전" 으로.
 */
export function formatSessionAge(savedAtIso) {
  if (!savedAtIso) return '—';
  const ms = Date.now() - new Date(savedAtIso).getTime();
  if (ms < 60_000)     return '방금 전';
  if (ms < 3_600_000)  return `${Math.floor(ms / 60_000)}분 전`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}시간 전`;
  return `${Math.floor(ms / 86_400_000)}일 전`;
}
