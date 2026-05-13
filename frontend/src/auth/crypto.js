// src/auth/crypto.js
// ──────────────────────────────────────────────────────────────────────────────
// 브라우저 내장 Web Crypto API 로 SHA-256 해시를 만든다.
//
// ⚠️ 클라이언트 측 해싱의 한계:
//   - "평문 비밀번호가 서버로 가지 않게" 하는 정도의 효과만 있다.
//   - localStorage 의 해시값을 누가 가져가도 똑같이 로그인할 수 있다 (pass-the-hash).
//   - 진짜 보안은 백엔드에서 bcrypt/argon2 같은 salted slow hash 필수.
//
// 그래서 이 프로젝트의 SHA-256 은 "데모 단계의 약한 보호막" 정도로만 봐야 한다.
// ──────────────────────────────────────────────────────────────────────────────

const TEXT_ENCODER = new TextEncoder();

// 학번 별로 다른 해시가 나오도록 salt 추가 (rainbow table 방어 한 줄짜리)
function buildSalted(input, salt) {
  return `lms-bridge::${salt}::${input}`;
}

/**
 * 비밀번호를 SHA-256 으로 해시한다.
 * @param {string} password - 평문 비밀번호
 * @param {string} salt - 보통 학번 같은 사용자별 고유값
 * @returns {Promise<string>} 64자 hex 문자열
 */
export async function hashPassword(password, salt = '') {
  const data = TEXT_ENCODER.encode(buildSalted(password, salt));
  const buf = await crypto.subtle.digest('SHA-256', data);
  return bufToHex(buf);
}

/**
 * 평문 비밀번호와 저장된 해시가 일치하는지 검증.
 */
export async function verifyPassword(password, salt, expectedHash) {
  const actual = await hashPassword(password, salt);
  return actual === expectedHash;
}

function bufToHex(buf) {
  const bytes = new Uint8Array(buf);
  let s = '';
  for (let i = 0; i < bytes.length; i++) {
    s += bytes[i].toString(16).padStart(2, '0');
  }
  return s;
}
