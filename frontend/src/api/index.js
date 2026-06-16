// frontend/src/api/index.js
// ──────────────────────────────────────────────────────────────────────────────
// FastAPI 백엔드 호출 함수 모음 (강의 / 공지 / 과제 / 자료 / 동기화).
//
// 백엔드 어댑터(이미 구현됨):
//   backend/app/adapter/courses.py        list_courses(client) -> List[Course]
//   backend/app/adapter/notices.py        list_notices(client, course_id) -> List[Notice]
//   backend/app/adapter/assignments.py    list_assignments(client, course_id), list_all_deadlines
//   backend/app/adapter/materials.py      list_materials(client, course_id) -> List[Material]
//
// FastAPI 라우트(예정 / 비어있음 — backend/app/api/routes/*.py 는 헤더 주석만):
//   GET  /api/courses                              → Course[]
//   GET  /api/courses/{id}/notices                 → Notice[]
//   GET  /api/courses/{id}/discussions             → Notice[]     (일반 토론, 공지와 분리)
//   GET  /api/courses/{id}/assignments             → Assignment[]
//   GET  /api/courses/{id}/modules                 → Material[]   (module items 펼친 형태)
//   GET  /api/assignments/todos                    → Assignment[] (모든 강의 마감 통합)
//   POST /api/sync                                 → SyncResult
//   GET  /api/sync/status                          → { running, lastSyncAt, syncHour }
//
// 백엔드 라우트가 아직 없으므로 USE_MOCK=true 인 동안은 mockData.js 의 seed 를 반환.
// 라우트가 생기는 즉시 USE_MOCK=false 로 바꾸면 fetch 호출로 전환.
//
// ⚠️ 백엔드 Pydantic 모델(models.py)과 프론트의 mockData 필드명이 다르다.
//    이 파일 하단의 adapt* 함수들이 그 간극을 흡수한다.
//      Course:     { id, name, course_code, term }
//                  ↔ { id, code, name, professor, credits, color, ... }
//      Notice:     { id, course_id, title, message_snippet, posted_at, ... }
//                  ↔ { id, course, title, date, unread, pinned }
//      Assignment: { id, course_id, title, due_at, points_possible, submission_types, ... }
//                  ↔ { id, course, title, due, submitted, weight, type }
//      Material:   { id, course_id, module_name, title, item_type, url, position }
//                  ↔ MODULES[courseId] = [{ week, title, items, completed, ... }]
// ──────────────────────────────────────────────────────────────────────────────

import { API_BASE } from '../data/uiConfig';
import * as seed from '../data/mockData';

// 데이터 조회 라우트(/api/courses 등) 구현+검증 완료 → 실연결.
// 백엔드 없이 UI 만 보고 싶으면 true 로 바꾸면 mock 으로 돌아간다.
export const USE_MOCK = false;
// 동기화 라우트(/api/sync)도 실연결.
export const USE_MOCK_SYNC = false;

// ── 내부 헬퍼 ────────────────────────────────────────────────────────────────
// 응답 실패 시 던지는 에러에 HTTP 상태코드를 실어 준다(err.status).
// DataStore 의 자동 재로그인 판별(_isAuthError)이 throw 된 401/403/419 를
// 메시지 문자열뿐 아니라 status 로도 잡을 수 있게 하기 위함.
async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    const err = new Error(`${res.status} ${res.statusText} — ${text}`);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

// 가짜 지연 — mock 호출이 항상 즉시 끝나면 로딩 상태 검증이 어려워서 약간 늦춤
const fakeDelay = (ms = 250) => new Promise(r => setTimeout(r, ms));

// ── 백엔드 모델 → 프론트 형식 어댑터 ─────────────────────────────────────────
// SSU Canvas 는 course name/code 에 "과목명 (과목코드)" 형태를 넣고, 색상·주차 같은
// 표시용 메타는 제공하지 않는다. 여기서 이름/코드를 정리하고 id 기반으로 색상을 부여한다.
const COURSE_COLORS = [
  'oklch(58% 0.14 268)', 'oklch(58% 0.13 195)', 'oklch(58% 0.13 35)',
  'oklch(56% 0.14 145)', 'oklch(60% 0.10 90)',  'oklch(54% 0.14 305)',
  'oklch(58% 0.10 230)', 'oklch(56% 0.13 12)',
];
function _courseColor(id) {
  const n = Math.abs(Number(id) || 0);
  return COURSE_COLORS[n % COURSE_COLORS.length];
}
// "고급프로그래밍 (2150164103)" → { name: "고급프로그래밍", code: "2150164103" }
function _cleanName(raw) {
  const m = (raw || '').match(/^(.*?)\s*\((\d+)\)\s*$/);
  return { name: m ? m[1].trim() : (raw || ''), code: m ? m[2] : '' };
}
function adaptCourse(b) {
  const { name, code } = _cleanName(b.name);
  return {
    id: b.id,
    code: code || b.course_code || '',
    name: name || b.name || '',
    professor: b.professor || '',
    credits: b.credits ?? 3,
    color: _courseColor(b.id),
    // 백엔드 progress 는 0~100(%) → 프론트는 0~1 비율 사용
    progress: b.progress != null ? b.progress / 100 : 0,
    // 주차는 학기 시작일 기반 계산값 사용 ("주차 0/16" 표기 방지),
    // materials 는 백엔드 Course.materials (강의 모듈 아이템 총 개수)
    weekCurrent: seed.SEMESTER.weekCurrent,
    weekTotal: 16,
    materials: b.materials ?? 0,
    unread: 0,
    dueSoon: 0,
    term: b.term || '',
  };
}

// 백엔드가 보내는 HTML 을 짧은 평문 미리보기로 정리.
function _htmlPreview(raw, limit = 200) {
  if (!raw) return '';
  // 태그 제거 후 공백 정리, limit 문자에서 자르고 …
  const text = raw.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  return text.length > limit ? text.slice(0, limit) + '…' : text;
}

function adaptNotice(b) {
  return {
    id:     b.id,
    course: b.course_id,
    title:  b.title,
    date:   b.posted_at,
    author: b.author || '',
    url:    b.html_url || '',
    // 백엔드 모델 필드는 `message` (HTML). 짧은 미리보기 + 전체 본문 둘 다 노출.
    snippet: _htmlPreview(b.message, 200),
    body:    b.message || '',
    // HTML 제거된 전체 본문 평문 (백엔드 message_text) — course-detail 펼침 표시용
    fullText: b.message_text || '',
    // 백엔드 is_read / pinned(discussion_topics.pinned) 반영
    unread: !b.is_read,
    pinned: !!b.pinned,
  };
}

// Canvas submission_types → 프론트 표시 타입 (dashboard typeIcon 의 키와 맞춤)
const SUBMISSION_TYPE_MAP = {
  online_upload:     'report',
  online_text_entry: 'essay',
  online_quiz:       'quiz',
  discussion_topic:  'essay',
};

function adaptAssignment(b) {
  const rawType = (b.submission_types && b.submission_types[0]) || '';
  return {
    id:     b.id,
    course: b.course_id,
    title:  b.title,
    due:    b.due_at,
    // ⚠️ points_possible 은 "배점"(예: 100점)이지 성적 비중(%)이 아니다.
    //    표시 문구는 '배점 N점' 으로 통일 (dashboard / course-detail).
    weight: b.points_possible || 0,
    type:   SUBMISSION_TYPE_MAP[rawType] || 'report',
    url:    b.html_url || '',
    // 백엔드 모델 필드는 `description` (HTML).
    snippet: _htmlPreview(b.description, 200),
    body:    b.description || '',
    // HTML 제거된 전체 본문 평문 (백엔드 description_text)
    fullText: b.description_text || '',
    // 백엔드 submitted 반영 (어댑터가 submissions API 로 채움)
    submitted: !!b.submitted,
  };
}

// Material[] 배열을 MODULES[courseId] = [{ week, title, items, ... }] 형태로 묶는다.
// 백엔드 Material 에는 명시적인 week 필드가 없어서 module_name 의 "1주차"/"Week 3" 패턴을 추출.
function adaptMaterialsToModules(materials) {
  const byModule = new Map();
  for (const m of materials) {
    const key = m.module_name || '기타';
    if (!byModule.has(key)) byModule.set(key, []);
    byModule.get(key).push(m);
  }
  const out = [];
  for (const [moduleName, items] of byModule) {
    const wk = moduleName.match(/(\d{1,2})\s*주차|week\s*(\d{1,2})/i);
    const week = wk ? Number(wk[1] || wk[2]) : (out.length + 1);
    out.push({
      week,
      title: moduleName,
      items: items.length,
      // 각 주차의 실제 자료 항목 (제목/타입/링크)
      list: items
        .sort((a, b) => (a.position || 0) - (b.position || 0))
        .map(it => ({ id: it.id, title: it.title, type: it.item_type, url: it.url })),
    });
  }
  return out.sort((a, b) => a.week - b.week);
}

// ── 강의 ────────────────────────────────────────────────────────────────────
export async function fetchCourses() {
  if (USE_MOCK) { await fakeDelay(); return seed.COURSES; }
  const data = await request('/api/courses');
  return (data || []).map(adaptCourse);
}

// ── 공지 ────────────────────────────────────────────────────────────────────
export async function fetchNotices(courseId) {
  if (USE_MOCK) {
    await fakeDelay();
    return courseId == null
      ? seed.NOTICES
      : seed.NOTICES.filter(n => n.course === courseId);
  }
  const path = courseId == null
    ? '/api/notices'                              // 백엔드 통합 라우트가 생긴다면
    : `/api/courses/${courseId}/notices`;
  const data = await request(path);
  return (data || []).map(adaptNotice);
}

// ── 과제 ────────────────────────────────────────────────────────────────────
export async function fetchAssignments(courseId) {
  if (USE_MOCK) {
    await fakeDelay();
    return courseId == null
      ? seed.ASSIGNMENTS
      : seed.ASSIGNMENTS.filter(a => a.course === courseId);
  }
  const path = courseId == null
    ? '/api/assignments/todos'
    : `/api/courses/${courseId}/assignments`;
  const data = await request(path);
  return (data || []).map(adaptAssignment);
}

// ── 강의 자료 (modules) ─────────────────────────────────────────────────────
export async function fetchModules(courseId) {
  if (USE_MOCK) {
    await fakeDelay();
    return seed.MODULES[courseId] || seed.MODULES[3] || [];
  }
  const data = await request(`/api/courses/${courseId}/modules`);
  return adaptMaterialsToModules(data || []);
}

// ── 토론 ────────────────────────────────────────────────────────────────────
// 공지와 동일한 discussion_topics 엔드포인트지만 only_announcements 없이 일반 토론만.
export async function fetchDiscussions(courseId) {
  // mockData 에 토론 seed 가 없으므로 mock 모드에선 빈 목록을 돌려준다.
  if (USE_MOCK) { await fakeDelay(); return []; }
  const data = await request(`/api/courses/${courseId}/discussions`);
  // adaptNotice 가 snippet/fullText(평문)/url/date/unread 를 채운다 (토론도 Notice 형태).
  return (data || []).map(adaptNotice);
}

// ── 동기화 ──────────────────────────────────────────────────────────────────
/**
 * 수동 동기화 트리거.
 * 백엔드는 LMS 수집 후, 설정된 경우에만 Notion push(sync_notion)·Obsidian push(sync_obsidian)를 실행한다.
 * 진행 상황은 별도 WebSocket(/api/sync/progress) 으로 받는 것을 권장 — 현재는 결과만 받음.
 * @returns {Promise<{ success: boolean, syncedAt: string, courses: number,
 *                     notices: number, assignments: number, materials: number,
 *                     errors: string[] }>}
 */
export async function triggerSync() {
  if (USE_MOCK_SYNC) {
    await fakeDelay(1500);
    return {
      success: true,
      syncedAt: new Date().toISOString(),
      courses: seed.COURSES.length,
      notices: 0,
      assignments: 0,
      materials: 0,
      errors: [],
    };
  }
  // 실연결 — POST /api/sync (백엔드가 auth.load_session() + Canvas 수집 수행)
  const data = await request('/api/sync', { method: 'POST' });
  return {
    success: data.success,
    syncedAt: data.synced_at,
    courses: data.courses,
    notices: data.notices,
    assignments: data.assignments,
    materials: data.materials,
    errors: data.errors || [],
  };
}

export async function fetchSyncStatus() {
  // triggerSync 와 같은 플래그 사용 — 둘이 따로 놀면 mock/실연결 혼합 동작이 된다.
  // 응답 스키마: { running, lastSyncAt, syncHour } (백엔드 routes/sync.py 와 일치 유지)
  if (USE_MOCK_SYNC) {
    await fakeDelay(100);
    return { running: false, lastSyncAt: null, syncHour: 4 };
  }
  return request('/api/sync/status');
}

// ── 커넥터 상태 ─────────────────────────────────────────────────────────────
/**
 * GET /api/connectors/status
 * → [ { id: "lms"|"notion"|"obsidian"|"llm", status, meta, last }, ... ]
 * 백엔드가 꺼져 있는 등 실패 시 null 반환 (throw 금지 — 앱은 seed 로 동작해야 함).
 */
export async function fetchConnectorsStatus() {
  if (USE_MOCK) return null;
  try {
    const data = await request('/api/connectors/status');
    return Array.isArray(data) ? data : null;
  } catch {
    return null;
  }
}

/**
 * GET /api/mcp/status — in-process MCP 서버 4종(lms/study/notion/obsidian) 현재 상태.
 * 각 항목: { id, name, status:'connected'|'disconnected', meta, tools,
 *           toolList:[{name, description}], url }
 * 절대 throw 하지 않는다 (실패 시 null → 페이지는 '확인 중'/빈 상태 유지).
 */
export async function fetchMcpStatus() {
  if (USE_MOCK) return null;
  try {
    const data = await request('/api/mcp/status');
    return Array.isArray(data) ? data : null;
  } catch {
    return null;
  }
}

/**
 * POST /api/connectors/config — 가입 마법사가 입력한 키를 백엔드 .env 에 저장.
 * payload 예: { notion_token, notion_root_page_id, obsidian_mcp_auth_code,
 *               obsidian_vault_path, obsidian_base_url, llm_api_key, llm_model }
 * throw 하지 않고 { ok, restartRequired, detail } 또는 { ok:false, error } 반환.
 *
 * ⚠️ 백엔드 connectors.py 의 ConnectorConfigIn 은 extra="forbid" 이므로 화이트리스트에
 *    없는 키를 보내면 422 로 전체 요청이 거부된다. obsidian_vault_path / obsidian_base_url /
 *    llm_model 세 키는 백엔드 화이트리스트 확장(#10)이 반영돼야 수용되는데, 아직 미반영인
 *    백엔드에서도 가입이 완료돼야 하므로 422 가 나면 알려진 키만 추려 1회 재시도한다.
 */
// #10 이전 백엔드도 항상 수용하는 키 — 422 재시도 시 이 집합만 남긴다.
const _LEGACY_CONFIG_KEYS = [
  'notion_token', 'notion_root_page_id', 'obsidian_mcp_auth_code', 'llm_api_key',
];

export async function saveConnectorConfig(payload) {
  if (USE_MOCK) return { ok: true, restartRequired: false };
  try {
    const data = await request('/api/connectors/config', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    return { ok: true, restartRequired: !!data.restart_required, detail: data.detail };
  } catch (e) {
    // 화이트리스트 미반영 백엔드(#10 이전)는 신규 키를 422 로 거부 — 알려진 키만으로 재시도.
    if (e.status === 422) {
      const legacy = {};
      for (const k of _LEGACY_CONFIG_KEYS) {
        if (payload[k] != null) legacy[k] = payload[k];
      }
      if (Object.keys(legacy).length) {
        try {
          const data = await request('/api/connectors/config', {
            method: 'POST',
            body: JSON.stringify(legacy),
          });
          return { ok: true, restartRequired: !!data.restart_required, detail: data.detail };
        } catch (e2) {
          return { ok: false, error: String(e2.message || e2) };
        }
      }
      // 저장할 알려진 키가 없다(신규 키만 보냄) — 모두 선택 설정이므로 가입을 막지 않는다.
      return { ok: true, restartRequired: false, detail: '백엔드가 일부 설정 키를 아직 지원하지 않아 건너뜀.' };
    }
    return { ok: false, error: String(e.message || e) };
  }
}

// ── 모든 페이지가 처음 띄울 때 한 번에 받을 수 있는 헬퍼 ────────────────────
// DataStore.jsx 의 useEffect 에서 호출.
// Promise.allSettled — 셋 중 일부만 실패해도 성공한 데이터는 반영할 수 있게
// 실패 항목은 null, 사유는 errors 배열로 돌려준다.
export async function fetchInitialBundle() {
  const [c, a, n] = await Promise.allSettled([
    fetchCourses(),
    fetchAssignments(),
    fetchNotices(),
  ]);
  const val = (r) => (r.status === 'fulfilled' ? r.value : null);
  const errors = [c, a, n]
    .filter(r => r.status === 'rejected')
    .map(r => String(r.reason?.message || r.reason));
  return { courses: val(c), assignments: val(a), notices: val(n), errors };
}
