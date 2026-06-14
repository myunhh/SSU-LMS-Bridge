"""학습 도우미(study) MCP 서버 오프라인 회귀 테스트 (네트워크 0, 실파일시스템 0).

핵심 보호 지점:
- 도구 목록 노출(8개, 이름에 '__' 없음, 필수 인자 스키마)
- _dump: ensure_ascii=False 한글 유지
- save_quiz → list_quizzes(본문 제외) → get_quiz(본문 포함) 라운드트립 + upsert
- delete_quiz 멱등
- save_deck SRS 초기화 + 덱 갱신 시 SRS 진척 보존
- review_due: due<=now 카드만 결정적 정렬로 반환
- grade_card: SM-2 경량 공식 정확값(now 주입으로 시간 독립)
- deps._build_registry 가 토큰 없이 'study' prefix 를 무조건 등록(setup 마운트 조건과 짝)

실제 디스패치 로직은 모듈 레벨 `_dispatch` 로 분리돼 있어 SSE/Server 내부 구조에
의존하지 않고 직접 호출해 검증한다. 저장소는 autouse fixture 로 tmp_path 격리한다.
"""
import json

import pytest

from app.mcp_client import study_server
from app.mcp_client.study_server import _dispatch, _dump, create_study_mcp_server

NOW = "2026-06-13T00:00:00Z"


# ── 저장소 격리 (실 .cache/study 절대 안 건드림) ──────────────
@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch, tmp_path):
    d = tmp_path / "study"
    monkeypatch.setattr(study_server, "_store_dir", lambda: d)
    return d


def _result_json(result):
    """_dispatch 반환(list[TextContent]) → dict."""
    assert len(result) == 1
    return json.loads(result[0].text)


# ── _dump 순수 함수 ───────────────────────────────────────────
def test_dump_keeps_korean():
    out = _dump({"title": "운영체제 핵심용어"})
    assert "운영체제" in out
    assert "\\uc6b4" not in out  # ensure_ascii=False — 이스케이프 안 됨


# ── 도구 목록 노출 ─────────────────────────────────────────────
async def _list_tools(server):
    import mcp.types as types

    handler = server.request_handlers[types.ListToolsRequest]
    result = await handler(types.ListToolsRequest(method="tools/list"))
    return result.root.tools


async def test_list_tools_exposes_eight_tools():
    server = create_study_mcp_server()
    tools = await _list_tools(server)
    names = {t.name for t in tools}
    assert names == {
        "save_quiz",
        "list_quizzes",
        "get_quiz",
        "delete_quiz",
        "save_deck",
        "list_decks",
        "review_due",
        "grade_card",
    }
    # prefix 는 registry 가 붙이므로 tool 이름 자체엔 '__' 가 없어야 함
    assert all("__" not in n for n in names)


async def test_tool_required_schemas():
    server = create_study_mcp_server()
    tools = {t.name: t for t in await _list_tools(server)}
    assert tools["save_quiz"].inputSchema["required"] == ["title", "questions"]
    assert tools["save_deck"].inputSchema["required"] == ["title", "cards"]
    assert tools["get_quiz"].inputSchema["required"] == ["id"]
    assert tools["delete_quiz"].inputSchema["required"] == ["id"]
    assert tools["grade_card"].inputSchema["required"] == ["deck_id", "card_id", "correct"]
    # 인자 없이도 호출 가능한 목록 도구는 required 없음
    assert "required" not in tools["list_quizzes"].inputSchema
    assert "required" not in tools["list_decks"].inputSchema
    assert "required" not in tools["review_due"].inputSchema


# ── 빈 저장소(처음) ────────────────────────────────────────────
async def test_empty_store_lists_are_empty():
    assert _result_json(await _dispatch("list_quizzes", {})) == {"quizzes": []}
    assert _result_json(await _dispatch("list_decks", {})) == {"decks": []}
    assert _result_json(await _dispatch("review_due", {})) == {"cards": []}


# ── save_quiz → list → get 라운드트립 ─────────────────────────
async def test_save_list_get_quiz_roundtrip():
    saved = _result_json(await _dispatch("save_quiz", {
        "title": "3주차 운영체제 퀴즈",
        "questions": [
            {"q": "페이지 폴트란?", "type": "mcq", "choices": ["A", "B"],
             "answer": "B", "explanation": "해설"},
        ],
        "source": {"kind": "notice", "course": "운영체제", "ref_id": 12345},
    }))
    assert saved["ok"] is True
    assert saved["id"].startswith("q_")
    assert saved["question_count"] == 1

    # list_quizzes 는 본문 questions 제외 + question_count 포함
    listed = _result_json(await _dispatch("list_quizzes", {}))["quizzes"]
    assert len(listed) == 1
    assert listed[0]["id"] == saved["id"]
    assert listed[0]["question_count"] == 1
    assert "questions" not in listed[0]

    # get_quiz 는 본문·정답·해설 보존
    quiz = _result_json(await _dispatch("get_quiz", {"id": saved["id"]}))["quiz"]
    assert quiz["title"] == "3주차 운영체제 퀴즈"
    assert quiz["questions"][0]["answer"] == "B"
    assert quiz["questions"][0]["explanation"] == "해설"
    assert quiz["source"]["course"] == "운영체제"


async def test_list_quizzes_course_filter():
    await _dispatch("save_quiz", {
        "title": "OS", "questions": [{"q": "a", "answer": "b"}],
        "source": {"course": "운영체제"},
    })
    await _dispatch("save_quiz", {
        "title": "DB", "questions": [{"q": "a", "answer": "b"}],
        "source": {"course": "데이터베이스"},
    })
    filtered = _result_json(await _dispatch("list_quizzes", {"course": "운영"}))["quizzes"]
    assert len(filtered) == 1
    assert filtered[0]["title"] == "OS"


# ── save_quiz upsert ──────────────────────────────────────────
async def test_save_quiz_upsert_overwrites_same_id():
    first = _result_json(await _dispatch("save_quiz", {
        "title": "원본", "questions": [{"q": "a", "answer": "b"}],
    }))
    qid = first["id"]
    # 같은 id 로 재저장 → 덮어쓰기(신규 row 안 생김)
    await _dispatch("save_quiz", {
        "id": qid, "title": "수정본",
        "questions": [{"q": "a", "answer": "b"}, {"q": "c", "answer": "d"}],
    })
    listed = _result_json(await _dispatch("list_quizzes", {}))["quizzes"]
    assert len(listed) == 1
    quiz = _result_json(await _dispatch("get_quiz", {"id": qid}))["quiz"]
    assert quiz["title"] == "수정본"
    assert len(quiz["questions"]) == 2
    # created_at 은 보존, updated_at 은 갱신(같거나 이후)
    assert quiz["created_at"] <= quiz["updated_at"]


async def test_save_quiz_empty_questions_raises():
    with pytest.raises(ValueError):
        await _dispatch("save_quiz", {"title": "빈퀴즈", "questions": []})


async def test_get_quiz_missing_raises():
    with pytest.raises(ValueError, match="퀴즈 없음"):
        await _dispatch("get_quiz", {"id": "q_nope"})


# ── delete_quiz 멱등 ──────────────────────────────────────────
async def test_delete_quiz_idempotent():
    saved = _result_json(await _dispatch("save_quiz", {
        "title": "삭제대상", "questions": [{"q": "a", "answer": "b"}],
    }))
    qid = saved["id"]
    out1 = _result_json(await _dispatch("delete_quiz", {"id": qid}))
    assert out1 == {"ok": True, "deleted": qid}
    # 두 번째 삭제 — 예외 없이 ok:false
    out2 = _result_json(await _dispatch("delete_quiz", {"id": qid}))
    assert out2 == {"ok": False, "deleted": None}
    # 없는 id 도 ok:false
    out3 = _result_json(await _dispatch("delete_quiz", {"id": "q_unknown"}))
    assert out3 == {"ok": False, "deleted": None}


# ── save_deck SRS 초기화 ──────────────────────────────────────
async def test_save_deck_initializes_srs():
    saved = _result_json(await _dispatch("save_deck", {
        "title": "운영체제 핵심용어",
        "cards": [{"front": "Thrashing", "back": "과도한 페이지 교체"}],
        "now": NOW,
    }))
    assert saved["ok"] is True
    assert saved["id"].startswith("d_")
    assert saved["card_count"] == 1

    # 신규 카드는 due=now(즉시 복습 대상), ease=2.5, interval=0
    decks = _result_json(await _dispatch("list_decks", {"now": NOW}))["decks"]
    assert decks[0]["card_count"] == 1
    assert decks[0]["due_count"] == 1  # due=now → 지금 복습 대상

    due = _result_json(await _dispatch("review_due", {"now": NOW}))["cards"]
    assert len(due) == 1
    assert due[0]["front"] == "Thrashing"
    assert due[0]["back"] == "과도한 페이지 교체"  # 자가채점용 back 포함
    assert due[0]["card_id"].startswith("c_")
    assert due[0]["interval"] == 0
    assert due[0]["reps"] == 0
    assert due[0]["due"] == NOW


# ── 덱 갱신 시 SRS 진척 보존 ──────────────────────────────────
async def test_save_deck_preserves_srs_on_update():
    saved = _result_json(await _dispatch("save_deck", {
        "title": "OS", "cards": [{"front": "T", "back": "thrash"}], "now": NOW,
    }))
    did = saved["id"]
    card_id = _result_json(await _dispatch("review_due", {"now": NOW}))["cards"][0]["card_id"]

    # 정답 1회 → interval=1, due=now+1d
    graded = _result_json(await _dispatch("grade_card", {
        "deck_id": did, "card_id": card_id, "correct": True, "now": NOW,
    }))
    assert graded["interval"] == 1
    assert graded["due"] == "2026-06-14T00:00:00Z"

    # 같은 덱 재저장(동일 front+back) → SRS 보존(due 안 리셋, 신규 카드 안 생김)
    re_saved = _result_json(await _dispatch("save_deck", {
        "id": did, "title": "OS",
        "cards": [{"front": "T", "back": "thrash"}], "now": NOW,
    }))
    assert re_saved["card_count"] == 1
    decks = _result_json(await _dispatch("list_decks", {"now": NOW}))["decks"]
    # due 가 now+1d 라 now 시점엔 복습 대상 아님(보존된 진척)
    assert decks[0]["due_count"] == 0
    # 카드 id 도 동일 유지(신규 카드로 재생성되지 않음)
    same = _result_json(await _dispatch("review_due", {
        "now": "2026-06-14T00:00:00Z",
    }))["cards"]
    assert same[0]["card_id"] == card_id


# ── #1 동일 front+back 2장 재저장 → card_id 고유 (붕괴 방지) ──
async def test_save_deck_duplicate_front_back_keeps_unique_card_ids():
    """동일 (front,back) 카드 2장이 든 덱을 재저장해도 두 card_id 가 충돌하지 않아야.

    preserved 가 (front,back)→단일값이면 둘째 카드가 첫째와 같은 card_id 로 붕괴해
    SRS 상태머신이 깨진다(둘째는 grade_card 가 절대 못 잡아 영원히 due, review_due
    중복 노출). (front,back)→리스트 1:1 매칭 + 조립 후 중복 id 재발급 가드로 막는다.
    """
    saved = _result_json(await _dispatch("save_deck", {
        "title": "중복카드덱",
        "cards": [
            {"front": "T", "back": "thrash"},
            {"front": "T", "back": "thrash"},  # 동일 front+back 2장
        ],
        "now": NOW,
    }))
    did = saved["id"]
    assert saved["card_count"] == 2

    due = _result_json(await _dispatch("review_due", {"now": NOW}))["cards"]
    assert len(due) == 2
    ids = [c["card_id"] for c in due]
    assert len(set(ids)) == 2, "동일 front+back 라도 card_id 는 카드마다 고유해야 함"

    # 한 장만 정답 처리 → due 가 now+1d 로 밀림. 나머지 한 장은 그대로 due 유지.
    await _dispatch("grade_card", {
        "deck_id": did, "card_id": ids[0], "correct": True, "now": NOW,
    })
    still_due = _result_json(await _dispatch("review_due", {"now": NOW}))["cards"]
    assert [c["card_id"] for c in still_due] == [ids[1]], (
        "둘째 카드가 첫째와 card_id 가 붕괴됐다면 grade_card 가 둘 다 밀어 0건이 됨"
    )

    # 동일 덱(동일 front+back 2장) 재저장 → 카드 2장·card_id 2개 유지(1:1 보존)
    re_saved = _result_json(await _dispatch("save_deck", {
        "id": did, "title": "중복카드덱",
        "cards": [
            {"front": "T", "back": "thrash"},
            {"front": "T", "back": "thrash"},
        ],
        "now": NOW,
    }))
    assert re_saved["card_count"] == 2
    deck = _result_json(await _dispatch("list_decks", {"now": NOW}))["decks"][0]
    assert deck["card_count"] == 2
    # 재저장 후에도 두 카드의 card_id 가 여전히 서로 다름(붕괴 없음)
    after = _result_json(await _dispatch("review_due", {
        "now": "2026-06-14T00:00:00Z",
    }))["cards"]
    assert len({c["card_id"] for c in after}) == 2


async def test_save_deck_duplicate_in_corrupt_deck_reissues_id(_isolated_store):
    """저장소가 과거에 같은 card_id 로 손상돼 있어도 재저장 시 중복 id 를 재발급한다.

    방어선 2(조립 후 중복 검사) 검증 — 디스크에 card_id 가 겹친 카드 2장을 심어두고
    save_deck 으로 같은 카드를 재저장하면, 충돌한 둘째 카드만 새 id 로 갈린다.
    """
    path = study_server._decks_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"decks": [{
        "id": "d_corrupt",
        "title": "손상덱",
        "source": None,
        "created_at": NOW,
        "updated_at": NOW,
        "cards": [
            {"id": "c_dupe", "front": "T", "back": "thrash", "hint": "",
             "ease": 2.5, "interval": 0, "reps": 0, "due": NOW, "last_reviewed": None},
            {"id": "c_dupe", "front": "T", "back": "thrash", "hint": "",
             "ease": 2.5, "interval": 0, "reps": 0, "due": NOW, "last_reviewed": None},
        ],
    }]}, ensure_ascii=False), encoding="utf-8")

    await _dispatch("save_deck", {
        "id": "d_corrupt", "title": "손상덱",
        "cards": [{"front": "T", "back": "thrash"}, {"front": "T", "back": "thrash"}],
        "now": NOW,
    })
    cards = _result_json(await _dispatch("review_due", {"now": NOW}))["cards"]
    assert len(cards) == 2
    assert len({c["card_id"] for c in cards}) == 2, "충돌 card_id 가 재발급돼 고유해야 함"


# ── review_due: 미래 due 제외 + 결정적 정렬 ───────────────────
async def test_review_due_excludes_future_and_sorts():
    # 카드 2장: 둘 다 신규(due=now) → 둘 다 잡힘, card_id 로 결정적 정렬
    await _dispatch("save_deck", {
        "title": "deck",
        "cards": [{"front": "A", "back": "a"}, {"front": "B", "back": "b"}],
        "now": NOW,
    })
    due = _result_json(await _dispatch("review_due", {"now": NOW}))["cards"]
    assert len(due) == 2
    # due 동률이면 card_id 오름차순 (결정적)
    assert [c["card_id"] for c in due] == sorted(c["card_id"] for c in due)

    # 미래 시각 기준 → 모두 제외 (due=now 인 카드는 now 이전엔 안 잡힘)
    past = "2026-06-12T00:00:00Z"
    assert _result_json(await _dispatch("review_due", {"now": past}))["cards"] == []


async def test_review_due_deck_filter():
    d1 = _result_json(await _dispatch("save_deck", {
        "title": "d1", "cards": [{"front": "A", "back": "a"}], "now": NOW,
    }))["id"]
    await _dispatch("save_deck", {
        "title": "d2", "cards": [{"front": "B", "back": "b"}], "now": NOW,
    })
    only_d1 = _result_json(await _dispatch("review_due", {"deck_id": d1, "now": NOW}))["cards"]
    assert len(only_d1) == 1
    assert only_d1[0]["deck_id"] == d1


# ── grade_card 정답 시퀀스 (SM-2 경량 정확값) ─────────────────
async def test_grade_card_correct_sequence():
    did = _result_json(await _dispatch("save_deck", {
        "title": "deck", "cards": [{"front": "A", "back": "a"}], "now": NOW,
    }))["id"]
    cid = _result_json(await _dispatch("review_due", {"now": NOW}))["cards"][0]["card_id"]

    # 1회 정답: reps=1, interval=1, ease=2.6, due=now+1d
    g1 = _result_json(await _dispatch("grade_card", {
        "deck_id": did, "card_id": cid, "correct": True, "now": NOW,
    }))
    assert g1["reps"] == 1
    assert g1["interval"] == 1
    assert g1["ease"] == pytest.approx(2.6)
    assert g1["due"] == "2026-06-14T00:00:00Z"

    # 2회 정답: reps=2, interval=3, ease=2.7, due=now+3d
    g2 = _result_json(await _dispatch("grade_card", {
        "deck_id": did, "card_id": cid, "correct": True, "now": NOW,
    }))
    assert g2["reps"] == 2
    assert g2["interval"] == 3
    assert g2["ease"] == pytest.approx(2.7)
    assert g2["due"] == "2026-06-16T00:00:00Z"

    # 3회 정답: interval = round(3 * 2.7) = 8, ease=2.8, due=now+8d
    g3 = _result_json(await _dispatch("grade_card", {
        "deck_id": did, "card_id": cid, "correct": True, "now": NOW,
    }))
    assert g3["reps"] == 3
    assert g3["interval"] == 8
    assert g3["ease"] == pytest.approx(2.8)
    assert g3["due"] == "2026-06-21T00:00:00Z"


# ── grade_card 오답 리셋 ──────────────────────────────────────
async def test_grade_card_wrong_resets():
    did = _result_json(await _dispatch("save_deck", {
        "title": "deck", "cards": [{"front": "A", "back": "a"}], "now": NOW,
    }))["id"]
    cid = _result_json(await _dispatch("review_due", {"now": NOW}))["cards"][0]["card_id"]

    # 정답 2회로 진척 쌓기
    await _dispatch("grade_card", {"deck_id": did, "card_id": cid, "correct": True, "now": NOW})
    await _dispatch("grade_card", {"deck_id": did, "card_id": cid, "correct": True, "now": NOW})
    # 오답: reps=0, interval=1, ease=max(1.3, 2.7-0.2)=2.5, due=now+1d
    g = _result_json(await _dispatch("grade_card", {
        "deck_id": did, "card_id": cid, "correct": False, "now": NOW,
    }))
    assert g["reps"] == 0
    assert g["interval"] == 1
    assert g["ease"] == pytest.approx(2.5)
    assert g["due"] == "2026-06-14T00:00:00Z"


async def test_grade_card_ease_floor():
    did = _result_json(await _dispatch("save_deck", {
        "title": "deck", "cards": [{"front": "A", "back": "a"}], "now": NOW,
    }))["id"]
    cid = _result_json(await _dispatch("review_due", {"now": NOW}))["cards"][0]["card_id"]
    # 연속 오답 다수 → ease 가 1.3 하한에서 클램프
    last = None
    for _ in range(10):
        last = _result_json(await _dispatch("grade_card", {
            "deck_id": did, "card_id": cid, "correct": False, "now": NOW,
        }))
    assert last["ease"] == pytest.approx(1.3)


async def test_grade_card_missing_deck_or_card_raises():
    with pytest.raises(ValueError, match="덱 없음"):
        await _dispatch("grade_card", {
            "deck_id": "d_nope", "card_id": "c_nope", "correct": True, "now": NOW,
        })
    did = _result_json(await _dispatch("save_deck", {
        "title": "deck", "cards": [{"front": "A", "back": "a"}], "now": NOW,
    }))["id"]
    with pytest.raises(ValueError, match="카드 없음"):
        await _dispatch("grade_card", {
            "deck_id": did, "card_id": "c_nope", "correct": True, "now": NOW,
        })


# ── unknown tool ──────────────────────────────────────────────
async def test_unknown_tool_raises():
    with pytest.raises(ValueError, match="unknown tool"):
        await _dispatch("nope", {})


# ── 손상 JSON 폴백 (예외로 안 죽음) ───────────────────────────
async def test_corrupt_json_falls_back_to_empty(_isolated_store):
    path = study_server._quizzes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not valid json", encoding="utf-8")
    # 손상 파일이어도 빈 목록으로 폴백(예외 없음)
    assert _result_json(await _dispatch("list_quizzes", {})) == {"quizzes": []}


# ── deps._build_registry: study 무조건 등록 (setup 마운트 조건과 짝) ──
def test_build_registry_registers_study_without_tokens():
    from app.api.deps import _build_registry

    _build_registry.cache_clear()
    registry = _build_registry(
        lms_url="http://localhost:8000/mcp/lms/sse",
        study_url="http://localhost:8000/mcp/study/sse",
        notion_url="http://localhost:8000/mcp/notion/sse",
        notion_token="",
        notion_root="",
        obsidian_url="http://localhost:8000/mcp/obsidian/sse",
        obsidian_auth="",
    )
    assert "study" in registry.prefixes
    study_client = registry._clients["study"]
    assert study_client.headers == {}
    assert study_client.server_url == "http://localhost:8000/mcp/study/sse"
