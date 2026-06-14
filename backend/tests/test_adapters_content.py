"""adapter 본문 평문 추출(#34)·자료 수(#39) 회귀 테스트.

- html_to_text: HTML → 평문 변환 규칙 (태그 제거, script/style 제거, 8000자 제한)
- list_notices / list_assignments: message_text / description_text 채움 (가짜 client, 네트워크 없음)
- list_courses: Course.materials 채움 + 과목당 추가 호출 수가 2(교수+모듈)를 넘지 않음
- canvas_client._headers_for: 이중 호스트 인증 불변 규칙 (Canvas 에 Bearer 금지)
- list_all_deadlines / list_all_notices / list_courses / list_assignments / list_materials:
  세션 만료(401) 시 조용히 삼키지 않고 전파 (per-course try/except 정책 회귀 방지)
- list_materials: 사용자용 딥링크(html_url) 우선 (API url 비우선)
- /announcements: start_date + end_date 윈도우 명시 (기본 14일 윈도우 무력화)
- _to_notice: discussion_topics.pinned → Notice.pinned 매핑 (Notion '중요' 체크박스 원천)
- list_discussions: 토론 목록 조회 (only_announcements 미지정, message_text 평문 채움, 401 전파)
"""
import httpx
import pytest

from app.adapter.assignments import list_all_deadlines, list_assignments
from app.adapter.canvas_client import CanvasClient
from app.adapter.courses import list_courses
from app.adapter.materials import list_materials
from app.adapter.notices import (
    MAX_TEXT_LEN,
    html_to_text,
    list_all_notices,
    list_discussions,
    list_notices,
)

# ── html_to_text ─────────────────────────────────────────────

def test_html_to_text_strips_tags():
    html = "<p>3주차 <b>과제</b> 안내</p><ul><li>마감: 금요일</li></ul>"
    text = html_to_text(html)
    assert "<" not in text and ">" not in text
    assert "3주차 과제 안내" in text
    assert "마감: 금요일" in text


def test_html_to_text_decodes_entities():
    assert html_to_text("A &amp; B &lt;C&gt;") == "A & B <C>"


def test_html_to_text_removes_script_and_style():
    html = "<style>p{color:red}</style><p>본문</p><script>alert('x')</script>"
    assert html_to_text(html) == "본문"


def test_html_to_text_empty_and_none():
    assert html_to_text("") == ""
    assert html_to_text(None) == ""


def test_html_to_text_collapses_whitespace_lines():
    html = "<div>  첫 줄  </div>\n\n<div>\t둘째   줄</div>"
    assert html_to_text(html) == "첫 줄\n둘째 줄"


def test_html_to_text_truncates_to_8000_chars():
    html = "<p>" + "가" * 10000 + "</p>"
    text = html_to_text(html)
    assert len(text) == MAX_TEXT_LEN == 8000


def test_html_to_text_custom_limit():
    assert html_to_text("<p>abcdef</p>", limit=3) == "abc"


# ── 가짜 client ──────────────────────────────────────────────

class FakeClient:
    """CanvasClient 대역: path → 응답 매핑. 네트워크 호출 없음."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, bool]] = []
        self.params_by_path: dict[str, dict] = {}  # 마지막 호출 params 기록 (윈도우 회귀용)

    async def get(self, path: str, params: dict = None, use_canvas: bool = False):
        self.calls.append((path, use_canvas))
        self.params_by_path[path] = params or {}
        result = self.routes.get(path)
        if isinstance(result, Exception):
            raise result
        if result is None:
            raise KeyError(f"라우팅되지 않은 경로: {path}")
        return result

    async def get_all_pages(self, path: str, params: dict = None, use_canvas: bool = False):
        # 실제 클라이언트처럼 페이지네이션도 get 으로 위임 (calls 기록 유지 → N+1 상한 테스트 호환)
        return await self.get(path, params, use_canvas)


def _http_401() -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://canvas.ssu.ac.kr/api/v1/test")
    resp = httpx.Response(401, request=req)
    return httpx.HTTPStatusError("401 Unauthorized", request=req, response=resp)


# ── list_notices → message_text ─────────────────────────────

NOTICE_HTML = "<p>휴강 <b>공지</b>입니다.</p><script>evil()</script>"


async def test_list_notices_fills_message_text():
    client = FakeClient({
        "/announcements": [{
            "id": 1,
            "title": "휴강 공지",
            "message": NOTICE_HTML,
            "posted_at": "2026-06-01T00:00:00Z",
            "author": {"display_name": "김교수"},
            "html_url": "https://canvas.ssu.ac.kr/courses/44176/discussion_topics/1",
            "read_state": "read",
            "pinned": True,
        }],
    })
    notices = await list_notices(client, 44176)
    assert len(notices) == 1
    n = notices[0]
    assert n.message == NOTICE_HTML            # 원문 HTML 은 그대로 유지
    assert n.message_text == "휴강 공지입니다."  # 평문 (script 제거 포함)
    assert n.course_id == 44176
    assert n.is_read is True
    assert n.pinned is True                     # discussion_topics.pinned 매핑


async def test_list_all_notices_fills_message_text_and_course_id():
    client = FakeClient({
        "/announcements": [{
            "id": 2,
            "context_code": "course_44176",
            "title": "중간고사 안내",
            "message": "<div>시험 범위는 <i>1~7장</i></div>",
        }],
    })
    notices = await list_all_notices(client, [44176])
    assert len(notices) == 1
    assert notices[0].course_id == 44176
    assert notices[0].message_text == "시험 범위는 1~7장"
    assert notices[0].pinned is False  # pinned 필드 부재 시 기본 False 회귀


async def test_list_notices_sends_announcement_window():
    """Canvas /announcements 기본 14일 윈도우 무력화 — start_date 와 end_date 둘 다 명시.

    ⚠️ end_date 누락 시 윈도우가 [180일 전, 152일 전]으로 밀려 최근 공지가 빠진다.
    """
    client = FakeClient({"/announcements": []})
    await list_notices(client, 44176)
    params = client.params_by_path["/announcements"]
    assert "start_date" in params
    assert "end_date" in params
    assert params["start_date"] < params["end_date"]


async def test_list_all_notices_sends_announcement_window():
    """통합 공지 조회도 start_date + end_date 윈도우를 명시해야 한다."""
    client = FakeClient({"/announcements": []})
    await list_all_notices(client, [44176])
    params = client.params_by_path["/announcements"]
    assert "start_date" in params
    assert "end_date" in params
    assert params["start_date"] < params["end_date"]


# ── list_assignments → description_text ─────────────────────

async def test_list_assignments_fills_description_text():
    client = FakeClient({
        "/courses/44176/assignments": [{
            "id": 10,
            "name": "과제 3",
            "due_at": "2026-06-15T14:59:59Z",
            "description": "<p>보고서를 <b>PDF</b> 로 제출</p>",
            "submission_types": ["online_upload"],
        }],
        "/courses/44176/students/submissions": [
            {"assignment_id": 10, "workflow_state": "submitted"},
        ],
    })
    assignments = await list_assignments(client, 44176)
    assert len(assignments) == 1
    a = assignments[0]
    assert a.description == "<p>보고서를 <b>PDF</b> 로 제출</p>"
    assert a.description_text == "보고서를 PDF 로 제출"
    assert a.submitted is True


async def test_list_all_deadlines_propagates_session_401():
    """세션 만료(401)는 조용한 빈 결과 대신 전역 핸들러로 전파되어야 한다."""
    client = FakeClient({
        "/courses/44176/assignments": _http_401(),
        "/courses/44176/students/submissions": _http_401(),
    })
    with pytest.raises(httpx.HTTPStatusError):
        await list_all_deadlines(client, [44176])


async def test_list_all_deadlines_skips_non_session_errors():
    """일반 오류(라우팅 안 된 과목 등)는 과목 단위로 건너뛴다."""
    client = FakeClient({
        "/courses/1/assignments": [{"id": 7, "name": "ok", "due_at": None}],
        "/courses/1/students/submissions": [],
        # course 2 는 라우팅 없음 → KeyError → 건너뜀
    })
    result = await list_all_deadlines(client, [1, 2])
    assert [a.id for a in result] == [7]


async def test_list_assignments_propagates_session_401_from_submissions_call():
    """제출 현황 호출(_get_submitted_ids)의 401 도 삼키지 말고 전파해야 한다."""
    client = FakeClient({
        "/courses/1/assignments": [{"id": 7, "name": "ok", "due_at": None}],
        "/courses/1/students/submissions": _http_401(),
    })
    with pytest.raises(httpx.HTTPStatusError):
        await list_assignments(client, 1)


# ── list_all_deadlines 병렬화 회귀 (#2) ──────────────────────

async def test_list_all_deadlines_aggregates_multiple_courses_sorted():
    """과목별 과제를 병렬 조회한 뒤 마감일(due_at) 오름차순으로 정렬·통합한다."""
    client = FakeClient({
        "/courses/1/assignments": [
            {"id": 1, "name": "늦은 과제", "due_at": "2026-06-20T00:00:00Z"},
        ],
        "/courses/1/students/submissions": [],
        "/courses/2/assignments": [
            {"id": 2, "name": "이른 과제", "due_at": "2026-06-10T00:00:00Z"},
            {"id": 3, "name": "마감없음", "due_at": None},
        ],
        "/courses/2/students/submissions": [],
    })
    result = await list_all_deadlines(client, [1, 2])
    # due_at 오름차순(없음은 '9999'로 맨 뒤)
    assert [a.id for a in result] == [2, 1, 3]


async def test_list_all_deadlines_session_401_wins_over_skipped_error():
    """병렬 조회에서 한 과목은 비-401 오류, 다른 과목은 401 이면 401 이 전파돼야 한다.

    return_exceptions=True 로 모두 수집된 뒤 세션 만료(401)만 골라 re-raise 하므로
    수집 순서와 무관하게 401 우선 전파 정책이 보장된다 (재로그인 유도).
    """
    client = FakeClient({
        # 과목 1: 라우팅 없음 → KeyError(비-401) → 건너뛸 후보
        # 과목 2: 401 → 전파돼야 함
        "/courses/2/assignments": _http_401(),
        "/courses/2/students/submissions": _http_401(),
    })
    with pytest.raises(httpx.HTTPStatusError):
        await list_all_deadlines(client, [1, 2])


# ── list_all_notices 401 전파 정책 ───────────────────────────

async def test_list_all_notices_propagates_session_401():
    """통합 공지 401 → 과목별 폴백 루프에서도 401 이면 전역 핸들러로 전파해야 한다.

    FakeClient 는 path 로만 라우팅하므로 /announcements 401 라우트 하나가
    통합 호출과 과목별 폴백의 Canvas 시도를 모두 커버하고, discussion_topics
    401 이 LearningX 폴백까지 막는다 (= 두 호스트 모두 401 → 세션 만료).
    """
    client = FakeClient({
        "/announcements": _http_401(),
        "/courses/44176/discussion_topics": _http_401(),
    })
    with pytest.raises(httpx.HTTPStatusError):
        await list_all_notices(client, [44176])


async def test_list_all_notices_skips_non_session_errors():
    """폴백 루프의 비-401 오류(라우팅 안 된 과목 등)는 과목 단위로 건너뛴다."""
    client = FakeClient({
        "/announcements": _http_401(),  # 통합 호출 + 과목별 Canvas 시도 둘 다 401
        # 과목 1 은 LearningX(discussion_topics) 폴백으로 성공
        "/courses/1/discussion_topics": [{"id": 5, "title": "ok", "message": "<p>x</p>"}],
        # 과목 2 는 라우팅 없음 → KeyError → 건너뜀
    })
    notices = await list_all_notices(client, [1, 2])
    assert [n.id for n in notices] == [5]


async def test_list_all_notices_fallback_aggregates_multiple_courses():
    """폴백 병렬 조회: 여러 과목 공지를 입력 과목 순서대로 통합한다 (#2)."""
    client = FakeClient({
        "/announcements": _http_401(),  # 통합 실패 → 과목별 폴백
        "/courses/1/discussion_topics": [{"id": 11, "title": "a", "message": "<p>x</p>"}],
        "/courses/2/discussion_topics": [{"id": 22, "title": "b", "message": "<p>y</p>"}],
    })
    notices = await list_all_notices(client, [1, 2])
    # zip(course_ids, results) 로 입력 과목 순서가 보존된다
    assert [n.id for n in notices] == [11, 22]


# ── list_discussions (토론 탭) ───────────────────────────────

DISCUSSION_HTML = "<p>토론 <b>주제</b>입니다.</p><script>evil()</script>"


async def test_list_discussions_fills_message_text():
    client = FakeClient({
        "/courses/44176/discussion_topics": [{
            "id": 7,
            "title": "1주차 토론",
            "message": DISCUSSION_HTML,
            "posted_at": "2026-06-01T00:00:00Z",
            "author": {"display_name": "이학생"},
            "html_url": "https://canvas.ssu.ac.kr/courses/44176/discussion_topics/7",
            "read_state": "unread",
        }],
    })
    discussions = await list_discussions(client, 44176)
    assert len(discussions) == 1
    d = discussions[0]
    assert d.message == DISCUSSION_HTML          # 원문 HTML 유지
    assert d.message_text == "토론 주제입니다."   # 평문 (script 제거)
    assert d.course_id == 44176
    assert d.is_read is False


async def test_list_discussions_omits_only_announcements():
    """토론 조회는 only_announcements 를 넣지 않는다 (공지 탭과 내용 중복 방지)."""
    client = FakeClient({"/courses/44176/discussion_topics": []})
    await list_discussions(client, 44176)
    params = client.params_by_path["/courses/44176/discussion_topics"]
    assert "only_announcements" not in params


async def test_list_discussions_propagates_session_401():
    """세션 만료(401)는 빈 결과 대신 전역 핸들러로 전파되어야 한다.

    FakeClient 는 path 로만 라우팅하므로 401 라우트 하나가 Canvas/LearningX
    양쪽 시도를 모두 커버한다 (= 두 호스트 모두 401 → 세션 만료).
    """
    client = FakeClient({"/courses/44176/discussion_topics": _http_401()})
    with pytest.raises(httpx.HTTPStatusError):
        await list_discussions(client, 44176)


async def test_list_discussions_falls_back_to_learningx():
    """Canvas(use_canvas=True) 비-401 실패 시 LearningX(use_canvas=False) 폴백."""

    class _DualHostClient(FakeClient):
        """(path, use_canvas) 튜플로 라우팅 — Canvas/LearningX 분기 검증용."""

        async def get(self, path: str, params: dict = None, use_canvas: bool = False):
            self.calls.append((path, use_canvas))
            self.params_by_path[path] = params or {}
            if use_canvas:
                raise RuntimeError("Canvas 일시 오류 (비-401)")
            return [{"id": 8, "title": "폴백 토론", "message": "<p>x</p>"}]

    client = _DualHostClient({})
    path = "/courses/44176/discussion_topics"
    discussions = await list_discussions(client, 44176)
    assert [d.id for d in discussions] == [8]
    assert client.calls == [(path, True), (path, False)]


# ── list_courses 401 전파 정책 ───────────────────────────────

async def test_list_courses_propagates_session_401_from_professor_call():
    """교수명 N+1 호출(_get_professor)의 401 은 빈 문자열 대신 전파해야 한다."""
    client = FakeClient({
        "/courses": [{"id": 101}],
        "/courses/101/users": _http_401(),
    })
    with pytest.raises(httpx.HTTPStatusError):
        await list_courses(client)


async def test_list_courses_propagates_session_401_from_modules_call():
    """모듈 N+1 호출(_get_progress_and_materials)의 401 도 전파해야 한다.

    교수 호출은 성공시켜 모듈 호출 지점까지 도달하게 한다 (위 테스트와 별개 경로).
    """
    client = FakeClient({
        "/courses": [{"id": 101}],
        "/courses/101/users": [],
        "/courses/101/modules": _http_401(),
    })
    with pytest.raises(httpx.HTTPStatusError):
        await list_courses(client)


# ── list_materials ───────────────────────────────────────────

async def test_list_materials_propagates_session_401():
    """세션 만료(401)는 빈/부분 자료 목록 대신 전역 핸들러로 전파되어야 한다.

    FakeClient 는 use_canvas 를 무시하고 path 로만 라우팅하므로 items 401 라우트
    하나가 Canvas/LearningX 양쪽 시도를 모두 커버한다 (= 두 호스트 모두 401).
    """
    client = FakeClient({
        "/courses/44176/modules": [{"id": 9, "name": "1주차"}],
        "/courses/44176/modules/9/items": _http_401(),
    })
    with pytest.raises(httpx.HTTPStatusError):
        await list_materials(client, 44176)


async def test_list_materials_skips_non_session_errors():
    """비-401 오류(라우팅 안 된 모듈 등)는 모듈 단위로 건너뛴다."""
    client = FakeClient({
        "/courses/44176/modules": [
            {"id": 1, "name": "1주차"},
            {"id": 2, "name": "2주차"},  # items 라우팅 없음 → KeyError → 건너뜀
        ],
        "/courses/44176/modules/1/items": [
            {"id": 11, "title": "강의노트", "type": "File", "position": 1},
        ],
    })
    materials = await list_materials(client, 44176)
    assert [m.id for m in materials] == [11]


async def test_list_materials_prefers_html_url_over_api_url():
    """Material.url 은 사용자용 딥링크(html_url → external_url)를 우선해야 한다.

    Canvas 모듈 아이템의 `url` 은 API 엔드포인트(JSON)라 브라우저 링크로 부적합.
    """
    client = FakeClient({
        "/courses/44176/modules": [{"id": 9, "name": "1주차"}],
        "/courses/44176/modules/9/items": [
            {
                "id": 1, "title": "강의노트", "type": "File",
                "url": "https://canvas.ssu.ac.kr/api/v1/courses/44176/files/1",
                "html_url": "https://canvas.ssu.ac.kr/courses/44176/modules/items/1",
            },
            {
                "id": 2, "title": "외부 자료", "type": "ExternalUrl",
                "url": "https://canvas.ssu.ac.kr/api/v1/courses/44176/module_items/2",
                "external_url": "https://example.com/lecture",
            },
        ],
    })
    materials = await list_materials(client, 44176)
    assert materials[0].url == "https://canvas.ssu.ac.kr/courses/44176/modules/items/1"
    assert materials[1].url == "https://example.com/lecture"


# ── list_courses → materials (#39) ───────────────────────────

MODULES = [
    {"items": [
        {"completion_requirement": {"completed": True}},
        {"completion_requirement": {"completed": False}},
        {},
    ]},
    {"items": [
        {"completion_requirement": {"completed": True}},
        {},
    ]},
]  # 아이템 총 5개, 완료 2개 → 진도 40.0


async def test_list_courses_fills_materials_with_course_progress():
    """course_progress 가 있어도 materials 는 modules 호출로 채운다."""
    client = FakeClient({
        "/courses": [{
            "id": 101,
            "name": "고급프로그래밍 (2150164103)",
            "course_code": "CSE4001",
            "term": {"name": "2026-1"},
            "course_progress": {"requirement_count": 10, "requirement_completed_count": 4},
        }],
        "/courses/101/users": [{"name": "김교수"}],
        "/courses/101/modules": MODULES,
    })
    courses = await list_courses(client)
    assert len(courses) == 1
    c = courses[0]
    assert c.progress == 40.0      # course_progress(4/10) 우선
    assert c.materials == 5        # modules 아이템 총수
    assert c.professor == "김교수"


async def test_list_courses_fills_materials_and_progress_from_modules():
    """course_progress 가 없으면 진도율도 같은 modules 응답에서 계산."""
    client = FakeClient({
        "/courses": [{"id": 102, "name": "운영체제"}],
        "/courses/102/users": [],
        "/courses/102/modules": MODULES,
    })
    courses = await list_courses(client)
    assert courses[0].progress == 40.0   # 2/5 완료
    assert courses[0].materials == 5


async def test_list_courses_extra_calls_capped_at_two_per_course():
    """N+1 상한 회귀 방지: 과목당 추가 호출은 교수 1 + 모듈 1 = 2 를 넘지 않는다."""
    client = FakeClient({
        "/courses": [{"id": 1}, {"id": 2}],
        "/courses/1/users": [], "/courses/1/modules": [],
        "/courses/2/users": [], "/courses/2/modules": [],
    })
    courses = await list_courses(client)
    assert len(courses) == 2
    assert all(c.materials == 0 for c in courses)
    # 목록 1 + 과목당 2 = 5 (병렬화해도 콜 개수는 동일해야 함)
    assert len(client.calls) == 5


async def test_list_courses_preserves_input_order_when_parallelized():
    """과목 루프를 asyncio.gather 로 병렬화해도 결과는 입력(/courses) 순서를 유지한다 (#2)."""
    client = FakeClient({
        "/courses": [{"id": 10, "name": "A"}, {"id": 20, "name": "B"}, {"id": 30, "name": "C"}],
        "/courses/10/users": [], "/courses/10/modules": [],
        "/courses/20/users": [], "/courses/20/modules": [],
        "/courses/30/users": [], "/courses/30/modules": [],
    })
    courses = await list_courses(client)
    assert [c.id for c in courses] == [10, 20, 30]


# ── canvas_client._headers_for 불변 규칙 ─────────────────────

def _client_with_auth() -> CanvasClient:
    c = CanvasClient(session_file="/tmp/_nonexistent_session.json")
    c._token = "xn-token-123"
    c._csrf = "csrf-456"
    return c


def test_headers_for_canvas_never_includes_bearer():
    """⚠️ 불변 규칙: Canvas(쿠키 인증)에 Authorization 을 실으면 세션이 죽는다."""
    h = _client_with_auth()._headers_for(use_canvas=True)
    assert "Authorization" not in h
    assert h["X-CSRF-Token"] == "csrf-456"
    assert h["Referer"].startswith("https://canvas.ssu.ac.kr")


def test_headers_for_learningx_includes_bearer():
    h = _client_with_auth()._headers_for(use_canvas=False)
    assert h["Authorization"] == "Bearer xn-token-123"
    assert h["Referer"].startswith("https://lms.ssu.ac.kr")


def test_headers_for_learningx_without_token_omits_authorization():
    c = CanvasClient(session_file="/tmp/_nonexistent_session.json")
    assert "Authorization" not in c._headers_for(use_canvas=False)


# ── CanvasClient._next_link (Link 헤더 파싱) ─────────────────
# rel="next" URL 추출 단위 테스트 (#11). 순수 staticmethod 라 인스턴스 불필요.

def test_next_link_empty_header_returns_none():
    """빈 Link 헤더 → 다음 페이지 없음(None)."""
    assert CanvasClient._next_link("") is None


def test_next_link_only_prev_returns_none():
    """rel=\"prev\" 만 있으면 다음 페이지가 없으므로 None."""
    header = '<https://canvas.ssu.ac.kr/api/v1/courses?page=1&per_page=100>; rel="prev"'
    assert CanvasClient._next_link(header) is None


def test_next_link_extracts_next_url():
    """rel=\"next\" 가 있으면 <...> 안의 URL 을 추출한다."""
    url = "https://canvas.ssu.ac.kr/api/v1/courses?page=3&per_page=100"
    header = f"<{url}>; rel=\"next\""
    assert CanvasClient._next_link(header) == url


def test_next_link_picks_next_among_mixed_rels():
    """current/prev/next/last 가 섞여 있어도 rel=\"next\" 만 골라낸다 (Canvas 표준 Link)."""
    next_url = "https://canvas.ssu.ac.kr/api/v1/courses?page=3&per_page=100"
    header = ", ".join([
        '<https://canvas.ssu.ac.kr/api/v1/courses?page=2&per_page=100>; rel="current"',
        '<https://canvas.ssu.ac.kr/api/v1/courses?page=1&per_page=100>; rel="prev"',
        f'<{next_url}>; rel="next"',
        '<https://canvas.ssu.ac.kr/api/v1/courses?page=9&per_page=100>; rel="last"',
    ])
    assert CanvasClient._next_link(header) == next_url


# ── CanvasClient.get_all_pages (페이지네이션 루프) ───────────
# _client.get 을 가짜로 갈아끼워 네트워크 없이 누적·params 전환·종료를 검증 (#11).

class _FakeResponse:
    """httpx.Response 대역: json() 과 headers(Link) 만 흉내낸다."""

    def __init__(self, payload: list, link: str = ""):
        self._payload = payload
        self.headers = {"Link": link} if link else {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeHttpClient:
    """CanvasClient._client 대역: get() 호출마다 url/params/headers 를 기록하고
    미리 준비한 응답을 순서대로 반환한다 (네트워크 없음)."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self._responses.pop(0)


def _client_with_fake_http(responses: list) -> CanvasClient:
    c = CanvasClient(session_file="/tmp/_nonexistent_session.json")
    c._client = _FakeHttpClient(responses)
    return c


async def test_get_all_pages_accumulates_until_no_next_link():
    """2페이지(1페이지에 next Link, 2페이지는 Link 없음)를 누적하고 종료한다."""
    page1_url = "https://canvas.ssu.ac.kr/api/v1/courses?page=2&per_page=100"
    responses = [
        _FakeResponse([{"id": 1}, {"id": 2}], link=f'<{page1_url}>; rel="next"'),
        _FakeResponse([{"id": 3}], link=""),  # next 없음 → 루프 종료
    ]
    client = _client_with_fake_http(responses)

    result = await client.get_all_pages("/courses")

    # 두 페이지가 순서대로 누적된다
    assert [r["id"] for r in result] == [1, 2, 3]
    # 정확히 2번 호출하고 멈춘다 (3번째 페이지를 요청하지 않음)
    assert len(client._client.calls) == 2


async def test_get_all_pages_sets_per_page_default_then_clears_params():
    """첫 호출엔 per_page=100 기본값을, 두 번째 호출부턴 params=None(이미 URL 에 쿼리 포함)."""
    page1_url = "https://canvas.ssu.ac.kr/api/v1/courses?page=2&per_page=100"
    responses = [
        _FakeResponse([{"id": 1}], link=f'<{page1_url}>; rel="next"'),
        _FakeResponse([{"id": 2}], link=""),
    ]
    client = _client_with_fake_http(responses)

    await client.get_all_pages("/courses")

    calls = client._client.calls
    # 첫 호출: per_page 기본값 적용, next URL 로 두 번째 호출
    assert calls[0]["params"]["per_page"] == 100
    assert calls[0]["url"] == f"{client.BASE}/courses"
    # 두 번째 호출: params 는 None, url 은 Link 의 next URL
    assert calls[1]["params"] is None
    assert calls[1]["url"] == page1_url


async def test_get_all_pages_does_not_mutate_caller_params():
    """호출자가 넘긴 params dict 를 변형하지 않는다 (복사 후 per_page 주입)."""
    responses = [_FakeResponse([{"id": 1}], link="")]
    client = _client_with_fake_http(responses)
    caller_params = {"include[]": "term"}

    await client.get_all_pages("/courses", params=caller_params)

    # 원본 dict 에는 per_page 가 새지 않았다
    assert "per_page" not in caller_params
    # 실제 전송 params 에는 per_page 가 주입됐다
    assert client._client.calls[0]["params"]["per_page"] == 100
    assert client._client.calls[0]["params"]["include[]"] == "term"
