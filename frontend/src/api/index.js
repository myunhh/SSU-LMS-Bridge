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
//   GET  /api/courses/{id}/assignments             → Assignment[]
//   GET  /api/courses/{id}/modules                 → Material[]   (module items 펼친 형태)
//   GET  /api/assignments/todos                    → Assignment[] (모든 강의 마감 통합)
//   POST /api/sync                                 → SyncResult
//   GET  /api/sync/status                          → { running, lastSyncAt, ... }
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

// 데이터 조회 라우트(/api/courses 등)는 아직 없음 → mock 유지.
export const USE_MOCK = true;
// 동기화 라우트(/api/sync)는 구현됨 → 실연결.
// 백엔드 없이 UI 만 보고 싶으면 true 로.
export const USE_MOCK_SYNC = false;

// ── 내부 헬퍼 ────────────────────────────────────────────────────────────────
async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText} — ${text}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

// 가짜 지연 — mock 호출이 항상 즉시 끝나면 로딩 상태 검증이 어려워서 약간 늦춤
const fakeDelay = (ms = 250) => new Promise(r => setTimeout(r, ms));

// ── 백엔드 모델 → 프론트 형식 어댑터 ─────────────────────────────────────────
// id 가 number 인 강의는 그대로, 기존 프론트 mock 의 색상/교수/진도는 백엔드에 없으니
// 매칭되는 seed.COURSES 항목이 있으면 그 메타를 덧붙인다. (백엔드 응답이 비면 seed 대체)
function adaptCourse(b) {
  const seedMatch = seed.COURSES.find(c => c.id === b.id || c.code === b.course_code);
  return {
    id: b.id,
    code: b.course_code || seedMatch?.code || '',
    name: b.name || seedMatch?.name || '',
    professor: seedMatch?.professor || '',
    credits:   seedMatch?.credits   || 3,
    color:     seedMatch?.color     || 'oklch(58% 0.14 268)',
    progress:  seedMatch?.progress  || 0,
    weekCurrent: seedMatch?.weekCurrent || 0,
    weekTotal:   seedMatch?.weekTotal   || 16,
    materials:   seedMatch?.materials   || 0,
    unread:      seedMatch?.unread      || 0,
    dueSoon:     seedMatch?.dueSoon     || 0,
    term: b.term || '',
  };
}

function adaptNotice(b) {
  return {
    id:     b.id,
    course: b.course_id,
    title:  b.title,
    date:   b.posted_at,
    author: b.author || '',
    url:    b.html_url || '',
    snippet: b.message_snippet || '',
    // read state / pinned 는 백엔드 모델에 없음 → 일단 false 로
    unread: true,
    pinned: false,
  };
}

function adaptAssignment(b) {
  return {
    id:     b.id,
    course: b.course_id,
    title:  b.title,
    due:    b.due_at,
    weight: b.points_possible || 0,
    type:   (b.submission_types && b.submission_types[0]) || 'report',
    url:    b.html_url || '',
    snippet: b.description_snippet || '',
    // submitted 여부는 별도 submission 엔드포인트가 필요 → 일단 false
    submitted: false,
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
      completed: 0,        // Canvas 모듈 progression 별도 호출 필요
      attended: false,
      raw: items,
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

export async function fetchCourseById(id) {
  if (USE_MOCK) { await fakeDelay(); return seed.COURSES.find(c => c.id === id) || null; }
  const data = await request(`/api/courses/${id}`);
  return adaptCourse(data);
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

// ── 동기화 ──────────────────────────────────────────────────────────────────
/**
 * 수동 동기화 트리거.
 * 백엔드는 LMS 스크래퍼 + sync_notion + sync_vault 를 순차 실행한다.
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
  if (USE_MOCK) {
    await fakeDelay(100);
    return { running: false, lastSyncAt: null };
  }
  return request('/api/sync/status');
}

// ── 모든 페이지가 처음 띄울 때 한 번에 받을 수 있는 헬퍼 ────────────────────
// DataStore.jsx 의 useEffect 에서 호출.
export async function fetchInitialBundle() {
  const [courses, assignments, notices] = await Promise.all([
    fetchCourses(),
    fetchAssignments(),
    fetchNotices(),
  ]);
  return { courses, assignments, notices };
}
