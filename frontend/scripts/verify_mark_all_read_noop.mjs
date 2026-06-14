// scripts/verify_mark_all_read_noop.mjs
// ──────────────────────────────────────────────────────────────────────────────
// 회귀 방지 가드 (#15) — '모두 읽음'이 0건일 때 성공 토스트/쓰기 없이 noop.
//
// 프론트는 별도 테스트 러너가 없으므로(npm run build 가 1차 게이트), 이 스크립트는
// 프레임워크 없이 Node 만으로 실행되는 독립 검증기다. DataStore.jsx 는 JSX/React
// 모듈이라 Node 로 직접 import 할 수 없으므로, 두 층위에서 회귀를 막는다:
//   (A) 행동 계약 — markAllNoticesRead 가 쓰는 "unread 0건이면 조기 반환" 로직을
//       동일한 형태로 재현해, 0건일 때 _writeOverrides·setNotices·onToast 가
//       호출되지 않고 1건 이상일 때만 호출됨을 단언한다.
//   (B) 소스 계약 — 실제 소스 파일에 가드가 살아 있는지 정적 검사:
//       · DataStore.jsx  : markAllNoticesRead 안에 length === 0 조기 반환
//       · dashboard.jsx  : '모두 읽음' 버튼에 disabled={noticesUnread === 0}
//       · sidebar.jsx    : '모두 읽음' 버튼에 disabled={unreadCount === 0}
//   (B)는 (A)가 재현한 로직이 실제 소스와 어긋나 "테스트만 통과"하는 상황을 막는다.
//
// 실행:  node scripts/verify_mark_all_read_noop.mjs   (frontend/ 에서)
// ──────────────────────────────────────────────────────────────────────────────
import { readFileSync } from 'node:fs';

let failures = 0;
function assert(cond, msg) {
  if (cond) {
    console.log(`  ok  — ${msg}`);
  } else {
    failures += 1;
    console.error(`  FAIL — ${msg}`);
  }
}

const SRC = new URL('../src/', import.meta.url);
const read = (rel) => readFileSync(new URL(rel, SRC), 'utf8');

// ── (A) 행동 계약: markAllNoticesRead 의 조기-반환 로직 재현 ────────────────────
// DataStore.jsx 의 markAllNoticesRead 와 동일한 형태:
//   read = {각 unread 공지 id: true}; Object.keys(read).length === 0 이면 조기 반환.
function makeMarkAll(notices, deps) {
  return () => {
    const read = {};
    notices.forEach(n => { if (n.unread) read[n.id] = true; });
    if (Object.keys(read).length === 0) return;          // ← #15 조기 반환
    deps.writeOverrides({ noticesRead: read });
    deps.setNotices();
    deps.onToast({ kind: 'success', text: '모든 공지를 읽음으로 표시했습니다.' });
  };
}
function spies() {
  const calls = { writeOverrides: 0, setNotices: 0, onToast: 0 };
  return {
    calls,
    writeOverrides: () => { calls.writeOverrides += 1; },
    setNotices: () => { calls.setNotices += 1; },
    onToast: () => { calls.onToast += 1; },
  };
}

console.log('[1] unread 0건 → 아무 부수효과 없음 (성공 토스트 없음)');
{
  const d = spies();
  makeMarkAll([{ id: 'n1', unread: false }, { id: 'n2', unread: false }], d)();
  assert(d.calls.onToast === 0, '0건일 때 onToast 미호출 (잘못된 성공 토스트 방지)');
  assert(d.calls.writeOverrides === 0, '0건일 때 _writeOverrides 미호출');
  assert(d.calls.setNotices === 0, '0건일 때 setNotices 미호출');
}

console.log('[2] 빈 목록 → 아무 부수효과 없음');
{
  const d = spies();
  makeMarkAll([], d)();
  assert(d.calls.onToast === 0, '빈 목록일 때 onToast 미호출');
}

console.log('[3] unread 1건 이상 → 정상 동작(토스트 1회)');
{
  const d = spies();
  makeMarkAll([{ id: 'n1', unread: true }, { id: 'n2', unread: false }], d)();
  assert(d.calls.onToast === 1, '미열람 있으면 성공 토스트 1회');
  assert(d.calls.writeOverrides === 1, '미열람 있으면 _writeOverrides 1회');
  assert(d.calls.setNotices === 1, '미열람 있으면 setNotices 1회');
}

// ── (B) 소스 계약: 실제 가드가 소스에 살아 있는지 정적 검사 ────────────────────
console.log('[4] 소스 가드 정적 검사');
{
  const dataStore = read('data/DataStore.jsx');
  // markAllNoticesRead 본문에 length === 0 조기 반환이 있는지(공백 변형 허용).
  const fn = dataStore.slice(dataStore.indexOf('const markAllNoticesRead'));
  const body = fn.slice(0, fn.indexOf('}, [notices, onToast]);') + 1);
  assert(/Object\.keys\(read\)\.length\s*===\s*0\)\s*return/.test(body),
    'DataStore.jsx markAllNoticesRead 에 length === 0 조기 반환 존재');

  const dash = read('pages/dashboard.jsx');
  assert(/disabled=\{noticesUnread\s*===\s*0\}/.test(dash),
    'dashboard.jsx 모두읽음 버튼 disabled={noticesUnread === 0}');

  const side = read('pages/sidebar.jsx');
  assert(/disabled=\{unreadCount\s*===\s*0\}/.test(side),
    'sidebar.jsx 알림 모두읽음 버튼 disabled={unreadCount === 0}');
}

if (failures) {
  console.error(`\n❌ ${failures}건 실패`);
  process.exit(1);
}
console.log('\n✅ 모든 검증 통과');
