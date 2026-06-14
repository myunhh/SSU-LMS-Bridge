// scripts/verify_lms_optin_relogin.mjs
// ──────────────────────────────────────────────────────────────────────────────
// 회귀 방지 가드 (#7) — 자동 재로그인 opt-in 동작 검증.
//
// 프론트는 별도 테스트 러너가 없으므로(npm run build 가 1차 게이트), 이 스크립트는
// 프레임워크 없이 Node 만으로 실행되는 독립 검증기다. 실제 AccountStore 모듈을
// import 해서 다음을 단언한다:
//   1) autoRelogin 미선택 → lms.password 가 localStorage 에 저장되지 않음(평문 잔존 방지),
//      getLmsCredentials() 는 null → settings.jsx 수동 재입력 폴백 사용.
//   2) autoRelogin 선택 → lms.password 보관, getLmsCredentials() 가 자격증명 반환.
//   3) 레거시 계정 호환 — lms:{id,password} 만 있는 예전 계정도 그대로 자격증명 반환
//      (마이그레이션이 평문 비번을 지우지 않음).
//
// 실행:  node scripts/verify_lms_optin_relogin.mjs   (frontend/ 에서)
// ──────────────────────────────────────────────────────────────────────────────

// Vite 식 확장자 없는 상대 import('./crypto')를 Node 가 해석하도록 resolve 훅 등록.
import { register } from 'node:module';
import { pathToFileURL } from 'node:url';
register('./ext-resolve-hook.mjs', pathToFileURL(import.meta.dirname + '/'));

// ── localStorage 폴리필 (Node 환경) ──────────────────────────────────────────
const _mem = new Map();
globalThis.localStorage = {
  getItem: (k) => (_mem.has(k) ? _mem.get(k) : null),
  setItem: (k, v) => { _mem.set(k, String(v)); },
  removeItem: (k) => { _mem.delete(k); },
  clear: () => { _mem.clear(); },
};
// Web Crypto(crypto.subtle) / TextEncoder 는 최신 Node 에 전역으로 존재.
if (!globalThis.crypto?.subtle) {
  throw new Error('이 검증 스크립트는 crypto.subtle 을 지원하는 Node(>=18) 가 필요합니다.');
}

const {
  signup,
  getLmsCredentials,
  resetAllAccounts,
} = await import('../src/auth/AccountStore.js');

let failures = 0;
function assert(cond, msg) {
  if (cond) {
    console.log(`  ok  — ${msg}`);
  } else {
    failures += 1;
    console.error(`  FAIL — ${msg}`);
  }
}

const K_ACCOUNTS = 'ssu_accounts';
const rawAccounts = () => JSON.parse(localStorage.getItem(K_ACCOUNTS) || '[]');

// ── 1) opt-in OFF: 비밀번호 저장 안 함 ────────────────────────────────────────
console.log('[1] autoRelogin=false → 비밀번호 미저장');
resetAllAccounts();
{
  const res = await signup({
    name: '홍길동', studentId: '20231234', email: 'a@ssu.ac.kr', password: 'abcd1234',
    lmsId: '20231234', lmsPassword: 'lms-secret', autoRelogin: false,
  });
  assert(res.ok, 'signup 성공');
  const acc = rawAccounts().find(a => a.studentId === '20231234');
  assert(acc && !('password' in acc.lms), 'lms.password 키가 localStorage 에 저장되지 않음');
  assert(acc && acc.lms.connected === true, 'lms.connected === true (연결 상태는 보존)');
  assert(acc && acc.lms.autoRelogin === false, 'lms.autoRelogin === false 보관');
  assert(getLmsCredentials() === null, 'getLmsCredentials() === null → 수동 재입력 폴백');
}

// ── 2) opt-in ON: 비밀번호 저장 ───────────────────────────────────────────────
console.log('[2] autoRelogin=true → 비밀번호 저장');
resetAllAccounts();
{
  const res = await signup({
    name: '김철수', studentId: '20235678', email: 'b@ssu.ac.kr', password: 'abcd1234',
    lmsId: '20235678', lmsPassword: 'lms-secret', autoRelogin: true,
  });
  assert(res.ok, 'signup 성공');
  const acc = rawAccounts().find(a => a.studentId === '20235678');
  assert(acc && acc.lms.password === 'lms-secret', 'lms.password 보관됨');
  const creds = getLmsCredentials();
  assert(creds && creds.id === '20235678' && creds.password === 'lms-secret',
    'getLmsCredentials() 가 자격증명 반환');
}

// ── 3) 레거시 계정 호환 ───────────────────────────────────────────────────────
console.log('[3] 레거시 계정(평문 password) 호환');
resetAllAccounts();
{
  // 예전 가입 포맷: lms:{id,password} 만 있고 connected/autoRelogin 키 없음
  const legacy = [{
    name: '레거시', studentId: '20239999', email: 'c@ssu.ac.kr',
    passwordHash: 'x', major: 'AI소프트웨어학부', createdAt: new Date().toISOString(),
    lms: { id: '20239999', password: 'old-plain' },
    notion: { connected: false }, obsidian: { connected: false }, claude: { connected: false },
  }];
  localStorage.setItem(K_ACCOUNTS, JSON.stringify(legacy));
  localStorage.setItem('ssu_session', '20239999');
  const creds = getLmsCredentials();
  assert(creds && creds.password === 'old-plain',
    '레거시 평문 비번이 마이그레이션에 지워지지 않고 그대로 반환됨');
}

resetAllAccounts();
if (failures) {
  console.error(`\n❌ ${failures}건 실패`);
  process.exit(1);
}
console.log('\n✅ 모든 검증 통과');
